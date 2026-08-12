"""Timbrado — medido no .docx da especialista, não inventado.

Página 1: logo largo centralizado + faixa institucional no rodapé.
Páginas 2+: marca compacta à direita, sem rodapé.
"""
import re

from app import pdf


def test_primeira_pagina_tem_logo_largo_centralizado():
    h = pdf.cabecalho_primeira()
    assert "text-align:center" in h
    assert h.count("<img") == 1          # logo largo, extraído da peça real
    assert "82.44mm" in h                # largura medida no wp:extent do docx


def test_demais_paginas_tem_marca_compacta_a_direita():
    h = pdf.cabecalho_demais()
    assert "text-align:right" in h
    assert h.count("<img") == 1
    assert "15.36mm" in h


def test_rodape_so_na_primeira_pagina():
    """A faixa vem por SOBREPOSIÇÃO: nem footerTemplate nem corpo alcançam os
    últimos ~5mm da página no Chromium."""
    assert "<img" in pdf.overlay_rodape_html()
    assert "margin:0" in pdf.overlay_rodape_html()
    assert "top:284mm" in pdf.overlay_rodape_html()
    assert "<img" not in pdf.VAZIO


def test_templates_usam_so_estilo_inline():
    """Chromium ignora <style> dentro de header/footer template — a imagem vai
    ao tamanho natural e sai gigante e cortada."""
    for t in (pdf.cabecalho_primeira(), pdf.cabecalho_demais()):
        assert "<style" not in t
        assert re.search(r'style="[^"]+"', t)


def test_margens_sao_as_do_documento_da_especialista():
    """pgMar do .docx: topo 1985 twips (35,0mm), inferior 1021 (18,0mm)."""
    assert abs(float(pdf.MARGEM["top"]) * 25.4 - 35.0) < 0.2
    assert abs(float(pdf.MARGEM["bottom"]) * 25.4 - 18.0) < 0.2
