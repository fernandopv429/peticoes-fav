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


# --- caminho direto no Gotenberg -------------------------------------------
# O n8n no meio existia só para guardar a Basic auth. Como cada peça faz TRÊS
# renderizações, eram seis saltos de rede por peça para esconder uma senha que
# a variável de ambiente esconde igual.

def test_a4_explicito_no_corpo_enviado():
    """O padrão do Gotenberg é LETTER. Sem paperWidth/Height a peça saía com
    18 páginas em vez de 16 — medido contra o caminho pelo n8n."""
    from app.pdf import PAPEL_A4
    assert PAPEL_A4 == ("8.27", "11.7")


def test_escolhe_o_caminho_pela_credencial(monkeypatch):
    """Sem credencial do Gotenberg, cai no webhook do n8n — a migração não pode
    quebrar produção antes de a variável existir lá."""
    import importlib
    import app.pdf as pdf
    chamou = {}
    monkeypatch.setattr(pdf, "GOTENBERG_URL", "")
    monkeypatch.setattr(pdf, "GOTENBERG_USER", "")
    monkeypatch.setattr(pdf, "_render_n8n", lambda *a, **k: chamou.setdefault("n8n", True) or b"%PDF")
    monkeypatch.setattr(pdf, "_render_gotenberg", lambda *a, **k: chamou.setdefault("direto", True) or b"%PDF")
    pdf._render("<p>x</p>", "", "", "x.pdf", 5)
    assert chamou == {"n8n": True}

    monkeypatch.setattr(pdf, "GOTENBERG_URL", "http://g:3000")
    monkeypatch.setattr(pdf, "GOTENBERG_USER", "u")
    chamou.clear()
    pdf._render("<p>x</p>", "", "", "x.pdf", 5)
    assert chamou == {"direto": True}


def test_401_do_gotenberg_diz_o_que_conferir(monkeypatch):
    """Erro legível é metade do motivo de tirar o n8n do caminho: pelo webhook,
    a falha chegava como "resposta não é PDF" e não dizia o porquê."""
    import httpx
    import pytest as _pt
    import app.pdf as pdf
    monkeypatch.setattr(pdf, "GOTENBERG_URL", "http://g:3000")
    monkeypatch.setattr(pdf, "GOTENBERG_USER", "u")
    monkeypatch.setattr(httpx, "post",
                        lambda *a, **k: httpx.Response(401, text="Unauthorized"))
    with _pt.raises(pdf.PdfIndisponivel) as e:
        pdf._render_gotenberg("<p>x</p>", "", "", 5, pdf.MARGEM)
    assert "GOTENBERG_USER" in str(e.value)


def test_erro_do_gotenberg_e_repassado(monkeypatch):
    import httpx
    import pytest as _pt
    import app.pdf as pdf
    monkeypatch.setattr(httpx, "post",
                        lambda *a, **k: httpx.Response(400, text="malformed HTML"))
    with _pt.raises(pdf.PdfIndisponivel) as e:
        pdf._render_gotenberg("<p>x</p>", "", "", 5, pdf.MARGEM)
    assert "malformed HTML" in str(e.value)
