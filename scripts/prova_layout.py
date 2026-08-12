#!/usr/bin/env python3
"""Fase 1 — prova de layout: .docx -> HTML -> PDF, comparado com .docx -> PDF direto.

Renderiza o mesmo modelo pelos dois caminhos para medir o custo de fidelidade da
rota HTML. O PDF do LibreOffice é a referência (mesmo motor que abre o Word);
o PDF do Chromium é a rota de produção (mesmo motor que o Gotenberg roda dentro).

    python scripts/prova_layout.py [caminho/para/modelo.docx]

Saída em data/saida/: referencia.pdf e rota_html.pdf
"""
import base64
import pathlib
import re
import shutil
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
ASSETS = RAIZ / "templates" / "assets"
SAIDA = RAIZ / "data" / "saida"

PADRAO_DOCX = (RAIZ.parent / "Agente 1.0" / "templates" / "MODELO_PRINCIPAL_template.docx")

# Extraídas do sectPr do .docx (twips/1440 pol). Fonte de verdade do layout.
MARGENS = {"top": "43mm", "bottom": "22.5mm", "left": "30mm", "right": "30mm"}
ALTURA_LOGO_TOPO = "16.3mm"


def b64(nome: str) -> str:
    return base64.b64encode((ASSETS / nome).read_bytes()).decode()


def soffice(entrada: pathlib.Path, formato: str, destino: pathlib.Path) -> pathlib.Path:
    subprocess.run(
        ["soffice", "--headless", "--convert-to", formato, "--outdir", str(destino), str(entrada)],
        check=True, capture_output=True, timeout=300,
    )
    return destino / f"{entrada.stem}.{formato}"


def preparar_html(caminho_html: pathlib.Path) -> pathlib.Path:
    """Corrige os dois defeitos da conversão do LibreOffice.

    1. O `@page` exportado usa a DISTÂNCIA DO CABEÇALHO (0,42cm) como margem
       superior da página, não a margem de texto (4,3cm). Sem remover, o corpo
       sobe para o topo e colide com o cabeçalho corrente.
    2. A justificação dos parágrafos se perde na conversão.
    """
    html = caminho_html.read_text(encoding="utf-8", errors="replace")
    html = re.sub(r"@page[^{]*\{[^}]*\}", "", html)
    html = html.replace("<body", "<style>p{text-align:justify;}</style><body", 1)
    destino = caminho_html.with_name("preparado.html")
    destino.write_text(html, encoding="utf-8")
    return destino


def render_pdf(html: pathlib.Path, saida: pathlib.Path) -> None:
    """Cabeçalho/rodapé vão por headerTemplate — é o ÚNICO jeito de desenhar na
    margem no Chromium. `position: fixed` no corpo é recortado (testado)."""
    from playwright.sync_api import sync_playwright

    # Chromium zera o font-size dentro dos templates; declarar sempre.
    cabecalho = (
        f'<div style="width:100%;text-align:center;font-size:8px;margin:0;padding:0;">'
        f'<img src="data:image/png;base64,{b64("image1.png")}" '
        f'style="height:{ALTURA_LOGO_TOPO};"></div>'
    )
    rodape = (
        f'<div style="width:100%;font-size:8px;margin:0;padding:0;">'
        f'<img src="data:image/png;base64,{b64("image2.png")}" style="width:100%;"></div>'
    )
    with sync_playwright() as p:
        navegador = p.chromium.launch(channel="chrome")
        pagina = navegador.new_page()
        pagina.goto(f"file://{html.resolve()}", wait_until="networkidle")
        pagina.pdf(path=str(saida), format="A4", print_background=True,
                   display_header_footer=True, header_template=cabecalho,
                   footer_template=rodape, margin=MARGENS)
        navegador.close()


def paginas(pdf: pathlib.Path) -> str:
    saida = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True).stdout
    achado = re.search(r"^Pages:\s+(\d+)", saida, re.M)
    return achado.group(1) if achado else "?"


def main() -> None:
    docx = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else PADRAO_DOCX
    if not docx.exists():
        sys.exit(f"modelo não encontrado: {docx}")
    SAIDA.mkdir(parents=True, exist_ok=True)
    trabalho = SAIDA / "_tmp"
    trabalho.mkdir(exist_ok=True)
    shutil.copy(docx, trabalho / docx.name)
    copia = trabalho / docx.name

    referencia = SAIDA / "referencia.pdf"
    shutil.move(str(soffice(copia, "pdf", trabalho)), referencia)

    html = preparar_html(soffice(copia, "html", trabalho))
    rota = SAIDA / "rota_html.pdf"
    render_pdf(html, rota)

    print(f"referência (docx→pdf):   {paginas(referencia):>3} páginas  {referencia}")
    print(f"rota HTML (docx→html→pdf): {paginas(rota):>3} páginas  {rota}")


if __name__ == "__main__":
    main()
