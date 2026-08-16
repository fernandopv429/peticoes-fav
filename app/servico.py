"""A API do gerador. Uma chamada = uma peça.

Quem chama hoje é o n8n, mas nada aqui depende disso: o Base44 ou qualquer
cliente HTTP serve. O n8n fica com as PONTAS — webhook da entrevista, aprovação
humana, entrega — e o miolo, que precisa de teste, mora aqui. A credencial do
Gotenberg saiu de lá: ver `app/pdf.py`.

    uvicorn app.servico:app --host 0.0.0.0 --port 8100
"""
from __future__ import annotations

import base64
import logging
import os
import secrets
import unicodedata
from typing import Any, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field

from app import pdf as pdf_mod
from app import pocketbase
from app.entrevista import valor_brl, campos_ausentes, de_entrevista
from app.modelos import Caso
from app.pipeline import gerar

logger = logging.getLogger(__name__)
# Suba a cada mudança de contrato da API: é por `/health` que se sabe qual
# build está no ar. Com a versão parada, um deploy que não aconteceu é
# indistinguível de um que aconteceu.
app = FastAPI(title="FAV — Gerador de Petições", version="0.7.0")

# Chave compartilhada com o n8n. O serviço fica numa URL pública do Coolify e
# cada chamada gasta uma requisição Opus e grava dados de cliente no
# PocketBase — sem isso, qualquer um na internet dispara as duas coisas.
API_KEY = os.environ.get("API_KEY", "")


def autorizar(x_api_key: str = Header(default="")) -> None:
    if not API_KEY:
        # Falha FECHADO: esquecer a variável em produção não pode abrir a API.
        raise HTTPException(503, "API_KEY não configurada no ambiente do serviço")
    if not secrets.compare_digest(x_api_key, API_KEY):
        raise HTTPException(401, "X-API-Key inválida ou ausente")


class PedidoGerar(BaseModel):
    codigo: str = Field(..., description="Id do caso — único, garante idempotência")
    caso: Caso
    municipio: Optional[str] = None
    consultar_cct: bool = True
    consultar_cnpj: bool = Field(
        True, description="Consulta o CNAE da empregadora na BrasilAPI. É o que "
                          "decide a categoria (SEEVISSP x SINDEEPRES x SIEMACO); "
                          "desligado, cai para a função, menos confiável.")
    redigir_ia: bool = Field(
        True, description="Chama o Claude para os capítulos narrativos. False "
                          "devolve a peça só com a estrutura determinística.")
    gerar_pdf: bool = True
    persistir: bool = True
    incluir_pdf_base64: bool = Field(
        False, description="Devolve o PDF no corpo da resposta. Sem isso ele vai "
                           "só para o PocketBase, e o n8n o busca de lá.")
    blocos: Optional[dict[str, str]] = Field(
        None, description="Capítulos narrativos prontos. Sobrepõem os da IA — "
                          "é por aqui que a revisão da especialista volta.")


@app.get("/health")
def health() -> dict[str, Any]:
    """Sem autenticação: é o que o Coolify usa para saber se o container subiu.

    Reporta quais integrações têm credencial, nunca o valor delas — é o
    diagnóstico que responde "por que a peça saiu sem CCT?" sem abrir shell."""
    return {"status": "ok", "versao": app.version,
            "ia": bool(os.environ.get("ANTHROPIC_API_KEY")),
            "cct": bool(os.environ.get("CCT_API_KEY")),
            "pocketbase": bool(os.environ.get("POCKETBASE_TOKEN")),
            "autenticado": bool(API_KEY)}


def _cabecalho_seguro(valor: Any) -> str:
    """Cabeçalho HTTP só aceita latin-1, e alguns proxies só ASCII.

    Transliterar em vez de substituir: com `errors="replace"`, "ordinário"
    virava "ordin?rio". Sem tratamento nenhum, o UnicodeEncodeError derruba a
    resposta inteira — some o PDF junto com o acento.
    """
    texto = unicodedata.normalize("NFKD", str(valor))
    return "".join(c for c in texto if not unicodedata.combining(c)) \
        .encode("ascii", "ignore").decode("ascii")


def _entregar(request: Request, resposta: dict[str, Any],
              pdf_bytes: Optional[bytes], codigo: str):
    """JSON por padrão; o PDF cru quando o cliente pede `Accept: application/pdf`.

    Devolver o PDF em base64 dentro do JSON obriga o n8n a decodificar num nó
    Code e infla o corpo em ~33%. Com o binário, o nó HTTP já entrega um item
    binário pronto para anexar ou salvar.

    Os metadados que importam vão em cabeçalhos `X-`, senão trocar JSON por PDF
    perderia o valor da causa, o gate e o id do registro.
    """
    if "application/pdf" not in request.headers.get("accept", ""):
        return resposta

    if not pdf_bytes:
        # Sem PDF não há o que entregar: o gate barrou ou o Gotenberg falhou.
        # 409 com o JSON explicando é mais útil que um 200 vazio.
        raise HTTPException(409, {"erro": "PDF não gerado", **resposta})

    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{_cabecalho_seguro(codigo)}.pdf"',
            "X-Status": _cabecalho_seguro(resposta.get("status", "")),
            "X-Valor-Causa": _cabecalho_seguro(resposta.get("valor_causa", "")),
            "X-Rito": _cabecalho_seguro(resposta.get("rito", "")),
            "X-Registro-Id": _cabecalho_seguro(resposta.get("registro_id", "")),
            "X-Campos-Ausentes": _cabecalho_seguro(
                ",".join(f["campo"] for f in resposta.get("campos_ausentes", []))),
        })


class PedidoEntrevista(BaseModel):
    """O formulário do app Base44, cru, como o webhook o recebe.

    Existe para o n8n NÃO precisar traduzir formulário -> Caso: essa tradução
    tem regra jurídica dentro (desvio x acúmulo, noturno por sobreposição de
    horário, extremo conservador das faixas) e mora em `app/entrevista.py`,
    onde tem teste. Repetida em expressão de nó, ela desanda em silêncio.
    """
    entrevista: dict[str, Any] = Field(
        ..., description="Registro da entidade `Entrevista` (RECL_NOME, FUNCAO, "
                         "DATA_ADMISSAO, tipo_dispensa, ...), sem transformação.")
    codigo: Optional[str] = Field(
        None, description="Id do caso. Vazio, usa o `id` do registro do Base44 — "
                          "é o que dá idempotência ao reenvio do webhook.")
    salario: Optional[str] = Field(
        None, description="Sobrepõe o SALARIO do formulário (ex.: 'R$ 2.148,22'). "
                          "Sem nenhum dos dois, usa o piso da CCT da categoria.")
    municipio: Optional[str] = None
    consultar_cct: bool = True
    consultar_cnpj: bool = True
    redigir_ia: bool = True
    gerar_pdf: bool = True
    persistir: bool = True
    incluir_pdf_base64: bool = False
    blocos: Optional[dict[str, str]] = None


@app.post("/peca/da-entrevista", dependencies=[Depends(autorizar)])
def peca_da_entrevista(p: PedidoEntrevista, request: Request):
    """Formulário do Base44 -> peça. É este que o webhook do n8n deve chamar."""
    e = p.entrevista
    if not e.get("RECL_NOME"):
        raise HTTPException(422, "entrevista sem RECL_NOME")

    salario = valor_brl(p.salario) if p.salario else None
    try:
        caso = de_entrevista(e, salario=salario)
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(422, f"entrevista não convertível: {exc}") from exc

    # Sem `codigo` explícito, o id do registro — reenviar o mesmo webhook
    # atualiza a peça em vez de criar uma segunda.
    codigo = p.codigo or e.get("id") or f"{e.get('RECL_CPF', 'SEM-CPF')}-{caso.rescisao}"

    resposta, pdf_bytes = _gerar_e_entregar(
        caso, codigo=codigo, municipio=p.municipio or caso.municipio_prestacao,
        consultar_cct=p.consultar_cct, consultar_cnpj=p.consultar_cnpj,
        redigir_ia=p.redigir_ia, blocos=p.blocos,
        gerar_pdf=p.gerar_pdf, persistir=p.persistir,
        incluir_pdf_base64=p.incluir_pdf_base64)

    # Devolve o que faltou no formulário — a especialista lê isto antes de
    # protocolar, em vez de descobrir procurando na peça.
    resposta["campos_ausentes"] = campos_ausentes(e)
    return _entregar(request, resposta, pdf_bytes, codigo)


@app.post("/peca/gerar", dependencies=[Depends(autorizar)])
def peca_gerar(p: PedidoGerar, request: Request):
    resposta, pdf_bytes = _gerar_e_entregar(
        p.caso, codigo=p.codigo, municipio=p.municipio,
        consultar_cct=p.consultar_cct, consultar_cnpj=p.consultar_cnpj,
        redigir_ia=p.redigir_ia, blocos=p.blocos,
        gerar_pdf=p.gerar_pdf, persistir=p.persistir,
        incluir_pdf_base64=p.incluir_pdf_base64)
    return _entregar(request, resposta, pdf_bytes, p.codigo)


def _gerar_e_entregar(caso: Caso, *, codigo: str, municipio: Optional[str],
                      consultar_cct: bool, consultar_cnpj: bool, redigir_ia: bool,
                      blocos: Optional[dict[str, str]], gerar_pdf: bool,
                      persistir: bool, incluir_pdf_base64: bool
                      ) -> tuple[dict[str, Any], Optional[bytes]]:
    """Gerar + PDF + persistir. Um só caminho para os dois endpoints, para não
    haver rota que grava diferente da outra."""
    try:
        r = gerar(caso, codigo=codigo, municipio=municipio,
                  consultar_cct=consultar_cct, consultar_cnpj=consultar_cnpj,
                  redigir_ia=redigir_ia, blocos=blocos)
    except FileNotFoundError as e:
        raise HTTPException(500, str(e)) from e

    resposta = r.resumo()
    pdf_bytes: Optional[bytes] = None

    # PDF só se o gate aprovou — não se protocola peça com problema bloqueante.
    if gerar_pdf and r.validacao.aprovado:
        try:
            pdf_bytes = pdf_mod.gerar_pdf(r.html, nome=f"{codigo}.pdf")
            resposta["pdf_bytes"] = len(pdf_bytes)
            if incluir_pdf_base64:
                resposta["pdf_base64"] = base64.b64encode(pdf_bytes).decode()
        except pdf_mod.PdfIndisponivel as e:
            logger.warning("PDF indisponível: %s", e)
            resposta["pdf_erro"] = str(e)

    if persistir:
        try:
            reg = pocketbase.salvar(codigo, {
                "status": r.status,
                "reclamante": caso.nome,
                "caso": caso.model_dump(mode="json"),
                "peca_html": r.html,
                "valor_causa": float(r.valor_causa),
                "validacao": r.validacao.como_dict(),
            })
            resposta["registro_id"] = reg.get("id")
            if pdf_bytes:
                pocketbase.anexar_pdf(reg["id"], pdf_bytes, f"{codigo}.pdf")
        except Exception as e:                       # noqa: BLE001
            logger.warning("PocketBase indisponível: %s", e)
            resposta["persistencia_erro"] = str(e)

    return resposta, pdf_bytes


@app.post("/peca/previa", response_class=HTMLResponse,
          dependencies=[Depends(autorizar)])
def peca_previa(p: PedidoGerar) -> str:
    """Só o HTML, para inspeção rápida sem gravar nem gerar PDF."""
    return gerar(p.caso, codigo=p.codigo, municipio=p.municipio,
                 consultar_cct=p.consultar_cct, redigir_ia=p.redigir_ia,
                 blocos=p.blocos).html
