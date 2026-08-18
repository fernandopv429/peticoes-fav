"""HTML -> PDF pelo Gotenberg.

O backend fala com o Gotenberg direto, com a Basic auth em variável de ambiente
(`GOTENBERG_URL`, `GOTENBERG_USER`, `GOTENBERG_PASSWORD`). Sem elas, gerar PDF
falha com erro claro — não há caminho alternativo escondido.

TIMBRADO — medido no `.docx` da especialista (`Feita pela especialista.docx`):

  página 1  : logo largo CENTRALIZADO (82,4 x 16,4 mm) + faixa institucional no
              rodapé (217,8 x 13,0 mm)
  páginas 2+: marca compacta À DIREITA (17,4 x 15,4 mm), SEM rodapé

O Word compõe essas variantes recortando e posicionando a mesma imagem-fonte
(`a:srcRect` + VML), o que é trabalhoso de reproduzir em CSS. Em vez disso, os
assets foram **extraídos do PDF da peça real a 600 dpi** — são pixel-a-pixel o
que a banca protocola:

  logo_primeira.png   (1940x379)  logo largo da 1ª página
  marca_demais.png    (403x357)   marca compacta das páginas 2+
  rodape_primeira.png (4961x305)  faixa institucional da 1ª página

Chromium aplica um único header/footer a TODAS as páginas — não existe
"primeira página diferente". A solução é renderizar duas vezes com o mesmo corpo
e as mesmas margens (logo, mesma paginação) e montar: página 1 do primeiro
render, restante do segundo.

Três regras do Chromium descobertas medindo PDF, não lendo documentação:
  1. cabeçalho/rodapé só desenham na margem via header/footer template — um
     `position: fixed` no corpo é recortado;
  2. dentro desses templates **só estilo inline funciona**; bloco <style> é
     ignorado e a imagem vai ao tamanho natural (o logo saiu gigante e cortado);
  3. o `@page` que o LibreOffice exporta usa a distância do cabeçalho como
     margem da página — sem removê-lo o corpo colide com o timbrado.
"""
from __future__ import annotations

import base64
import io
import os
import pathlib

import httpx

# O backend fala com o Gotenberg direto. Gotenberg é infraestrutura — um
# conversor HTML->PDF —, não orquestração: é dependência de mesma natureza que o
# PocketBase ou a API de CCT. Cada peça faz TRÊS renderizações (capa, miolo,
# faixa do rodapé), montadas num documento só.
GOTENBERG_URL = os.environ.get("GOTENBERG_URL", "").rstrip("/")
GOTENBERG_USER = os.environ.get("GOTENBERG_USER", "")
GOTENBERG_SENHA = os.environ.get("GOTENBERG_PASSWORD", "")
ASSETS = pathlib.Path(__file__).resolve().parent.parent / "templates" / "assets"

# Margens do documento da especialista (pgMar em twips / 1440 = polegada)
# A4 em polegadas, que é a unidade do Gotenberg.
PAPEL_A4 = ("8.27", "11.7")

MARGEM = {"top": "1.378", "bottom": "0.709", "left": "1.181", "right": "1.181"}

class PdfIndisponivel(RuntimeError):
    pass


def _b64(nome: str) -> str:
    return base64.b64encode((ASSETS / nome).read_bytes()).decode()


def _img(nome: str, estilo: str) -> str:
    return f'<img src="data:image/png;base64,{_b64(nome)}" style="{estilo}">'


def cabecalho_primeira() -> str:
    """Logo largo centralizado — 82,44 x 16,37 mm, medido no `wp:extent` do docx."""
    # padding-top de 3,5mm: sem ele o Chromium encosta o logo no topo e ele sai
    # 3,4mm acima da posição do documento da banca (medido a 600dpi).
    return ('<div style="width:100%;text-align:center;font-size:8px;margin:0;'
            'padding:3.5mm 0 0 0;">'
            + _img("logo_primeira.png", "width:82.44mm;height:auto;") + '</div>')


def cabecalho_demais() -> str:
    """Marca compacta alinhada à DIREITA, 15,4 mm — como nas páginas 2+ do modelo."""
    return ('<div style="width:100%;text-align:right;font-size:8px;margin:0;'
            'padding:3.5mm 30mm 0 0;">'
            + _img("marca_demais.png", "height:15.36mm;width:auto;") + '</div>')


def overlay_rodape_html() -> str:
    """Página A4 de margem ZERO com a faixa institucional na posição exata.

    Nem o `footerTemplate` nem o corpo alcançam os últimos ~5 mm da página no
    Chromium: o template é escalado e ancorado com folga fixa na base, e o corpo
    é recortado na margem inferior. A faixa da peça real fica a 0,1 mm da borda.
    Por isso ela vem numa página própria, com `@page{margin:0}` — aí `top` é
    medido a partir da borda do papel — e é estampada sobre a página 1.

    Medido no PDF da peça: faixa em y 284,0–296,9 mm, x 0–210 mm (sangra até as
    bordas laterais, além das margens de texto).
    """
    return ('<!DOCTYPE html><html><head><style>'
            '@page{size:A4;margin:0}html,body{margin:0;padding:0}'
            '</style></head><body>'
            '<div style="position:absolute;top:284mm;left:0;width:210mm;height:12.9mm;">'
            + _img("rodape_primeira.png",
                   "width:210mm;height:12.9mm;display:block;")
            + '</div></body></html>')


VAZIO = '<div style="font-size:8px;"></div>'


def _render(html: str, cabecalho: str, rodape: str, nome: str, timeout: float,
            *, margens: dict[str, str] | None = None) -> bytes:
    """Uma renderização no Gotenberg.

    Os NOMES dos arquivos são o contrato do Gotenberg: ele só reconhece o corpo
    como `index.html` e o timbrado como `header.html`/`footer.html`.
    """
    if not (GOTENBERG_URL and GOTENBERG_USER):
        raise PdfIndisponivel(
            "Gotenberg não configurado — defina GOTENBERG_URL, GOTENBERG_USER e "
            "GOTENBERG_PASSWORD no ambiente do serviço")
    margens = margens or MARGEM
    arquivos = [
        ("files", ("index.html", html.encode(), "text/html")),
        ("files", ("header.html", cabecalho.encode(), "text/html")),
        ("files", ("footer.html", rodape.encode(), "text/html")),
    ]
    dados = {
        # A4 EXPLÍCITO: o padrão do Gotenberg é Letter (215,9 x 279,4 mm). Sem
        # isto a peça saía com 18 páginas em vez de 16, e toda a paginação
        # medida contra o documento da banca ia por água abaixo.
        "paperWidth": PAPEL_A4[0], "paperHeight": PAPEL_A4[1],
        "marginTop": margens["top"], "marginBottom": margens["bottom"],
        "marginLeft": margens["left"], "marginRight": margens["right"],
        # sem isto o Chromium descarta os fundos e o timbrado perde a faixa
        "printBackground": "true",
    }
    try:
        r = httpx.post(f"{GOTENBERG_URL}/forms/chromium/convert/html",
                       files=arquivos, data=dados, timeout=timeout,
                       auth=(GOTENBERG_USER, GOTENBERG_SENHA))
    except httpx.HTTPError as e:
        raise PdfIndisponivel(f"falha ao chamar o Gotenberg: {e}") from e
    if r.status_code == 401:
        raise PdfIndisponivel("Gotenberg recusou a credencial (401) — confira "
                              "GOTENBERG_USER e GOTENBERG_PASSWORD")
    if r.status_code != 200:
        # O Gotenberg explica a falha em texto puro — repassar é o que torna o
        # erro acionável, em vez de um "resposta não é PDF" genérico.
        raise PdfIndisponivel(f"Gotenberg respondeu {r.status_code}: {r.text[:300]}")
    if r.content[:4] != b"%PDF":
        raise PdfIndisponivel(f"resposta não é PDF: {r.content[:200]!r}")
    return r.content


def gerar_pdf(html: str, *, nome: str = "peticao.pdf", timeout: float = 180) -> bytes:
    """Dois renders + junção, para reproduzir o `titlePg` do Word.

    Corpo e margens idênticos nos dois, então a paginação é a mesma e a junção
    é só troca de página — nada de conteúdo se desloca.
    """
    primeira = _render(html, cabecalho_primeira(), VAZIO, nome, timeout)
    demais = _render(html, cabecalho_demais(), VAZIO, nome, timeout)

    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError:      # sem pypdf, entrega o render da primeira página
        return primeira

    r1, r2 = PdfReader(io.BytesIO(primeira)), PdfReader(io.BytesIO(demais))
    if len(r1.pages) != len(r2.pages):
        # não deveria acontecer (mesmo corpo e margens); se acontecer, não
        # arrisca embaralhar o documento
        return primeira

    pagina1 = r1.pages[0]
    try:
        faixa = _render(overlay_rodape_html(), VAZIO, VAZIO, "rodape.pdf", timeout,
                        margens={"top": "0", "bottom": "0", "left": "0", "right": "0"})
        pagina1.merge_page(PdfReader(io.BytesIO(faixa)).pages[0])
    except (PdfIndisponivel, IndexError):
        pass                 # sem a faixa a peça ainda sai; só perde o rodapé

    saida = PdfWriter()
    saida.add_page(pagina1)
    for pagina in r2.pages[1:]:
        saida.add_page(pagina)
    buffer = io.BytesIO()
    saida.write(buffer)
    return buffer.getvalue()
