"""API que o n8n chama. Uma chamada = uma peça.

O n8n fica com as pontas (webhook da entrevista, aprovação humana, entrega,
credencial do Gotenberg); o miolo — que precisa de teste — mora aqui.

    uvicorn app.servico:app --host 0.0.0.0 --port 8100
"""
from __future__ import annotations

import base64
import logging
import os
import secrets
from typing import Any, Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from app import pdf as pdf_mod
from app import pocketbase
from app.modelos import Caso
from app.pipeline import gerar

logger = logging.getLogger(__name__)
app = FastAPI(title="FAV — Gerador de Petições", version="0.4.0")

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


@app.post("/peca/gerar", dependencies=[Depends(autorizar)])
def peca_gerar(p: PedidoGerar) -> dict[str, Any]:
    try:
        r = gerar(p.caso, codigo=p.codigo, municipio=p.municipio,
                  consultar_cct=p.consultar_cct, redigir_ia=p.redigir_ia,
                  blocos=p.blocos)
    except FileNotFoundError as e:
        raise HTTPException(500, str(e)) from e

    resposta = r.resumo()

    # PDF só se o gate aprovou — não se protocola peça com problema bloqueante.
    if p.gerar_pdf and r.validacao.aprovado:
        try:
            pdf_bytes = pdf_mod.gerar_pdf(r.html, nome=f"{p.codigo}.pdf")
            resposta["pdf_bytes"] = len(pdf_bytes)
            if p.incluir_pdf_base64:
                resposta["pdf_base64"] = base64.b64encode(pdf_bytes).decode()
        except pdf_mod.PdfIndisponivel as e:
            logger.warning("PDF indisponível: %s", e)
            resposta["pdf_erro"] = str(e)
            pdf_bytes = None
    else:
        pdf_bytes = None

    if p.persistir:
        try:
            reg = pocketbase.salvar(p.codigo, {
                "status": r.status,
                "reclamante": p.caso.nome,
                "caso": p.caso.model_dump(mode="json"),
                "peca_html": r.html,
                "valor_causa": float(r.valor_causa),
                "validacao": r.validacao.como_dict(),
            })
            resposta["registro_id"] = reg.get("id")
            if pdf_bytes:
                pocketbase.anexar_pdf(reg["id"], pdf_bytes, f"{p.codigo}.pdf")
        except Exception as e:                       # noqa: BLE001
            logger.warning("PocketBase indisponível: %s", e)
            resposta["persistencia_erro"] = str(e)

    return resposta


@app.post("/peca/previa", response_class=HTMLResponse,
          dependencies=[Depends(autorizar)])
def peca_previa(p: PedidoGerar) -> str:
    """Só o HTML, para inspeção rápida sem gravar nem gerar PDF."""
    return gerar(p.caso, codigo=p.codigo, municipio=p.municipio,
                 consultar_cct=p.consultar_cct, redigir_ia=p.redigir_ia,
                 blocos=p.blocos).html
