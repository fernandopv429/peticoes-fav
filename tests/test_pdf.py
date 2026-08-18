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


# --- Gotenberg direto ------------------------------------------------------
# O backend fala com o Gotenberg direto. Não há caminho alternativo: sem a
# credencial, gerar PDF falha com erro claro.

def test_a4_explicito_no_corpo_enviado():
    """O padrão do Gotenberg é LETTER. Sem paperWidth/Height a peça saía com
    18 páginas em vez de 16."""
    from app.pdf import PAPEL_A4
    assert PAPEL_A4 == ("8.27", "11.7")


def test_sem_credencial_falha_claro(monkeypatch):
    """Sem Gotenberg configurado, o erro diz exatamente o que falta — não há
    fallback silencioso para mascarar a configuração ausente."""
    import pytest as _pt
    import app.pdf as pdf
    monkeypatch.setattr(pdf, "GOTENBERG_URL", "")
    monkeypatch.setattr(pdf, "GOTENBERG_USER", "")
    with _pt.raises(pdf.PdfIndisponivel) as e:
        pdf._render("<p>x</p>", "", "", "x.pdf", 5)
    assert "GOTENBERG_URL" in str(e.value)


def test_401_do_gotenberg_diz_o_que_conferir(monkeypatch):
    """Erro acionável: o 401 aponta qual variável conferir, em vez de um
    "resposta não é PDF" genérico."""
    import httpx
    import pytest as _pt
    import app.pdf as pdf
    monkeypatch.setattr(pdf, "GOTENBERG_URL", "http://g:3000")
    monkeypatch.setattr(pdf, "GOTENBERG_USER", "u")
    monkeypatch.setattr(httpx, "post",
                        lambda *a, **k: httpx.Response(401, text="Unauthorized"))
    with _pt.raises(pdf.PdfIndisponivel) as e:
        pdf._render("<p>x</p>", "", "", "x.pdf", 5, margens=pdf.MARGEM)
    assert "GOTENBERG_USER" in str(e.value)


def test_erro_do_gotenberg_e_repassado(monkeypatch):
    import httpx
    import pytest as _pt
    import app.pdf as pdf
    monkeypatch.setattr(pdf, "GOTENBERG_URL", "http://g:3000")
    monkeypatch.setattr(pdf, "GOTENBERG_USER", "u")
    monkeypatch.setattr(httpx, "post",
                        lambda *a, **k: httpx.Response(400, text="malformed HTML"))
    with _pt.raises(pdf.PdfIndisponivel) as e:
        pdf._render("<p>x</p>", "", "", "x.pdf", 5, margens=pdf.MARGEM)
    assert "malformed HTML" in str(e.value)


def test_credencial_aceita_os_nomes_do_coolify(monkeypatch):
    """O Coolify gera SERVICE_USER/PASSWORD_GOTENBERG sozinho. Aceitar esses
    nomes evita ter que duplicar as variáveis à mão — foi o que fez o PDF
    falhar mesmo com tudo preenchido no painel."""
    import importlib
    for k in ("GOTENBERG_URL", "GOTENBERG_USER", "GOTENBERG_PASSWORD"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SERVICE_URL_GOTENBERG", "http://gotenberg:3000")
    monkeypatch.setenv("SERVICE_USER_GOTENBERG", "u123")
    monkeypatch.setenv("SERVICE_PASSWORD_GOTENBERG", "p456")
    import app.pdf as pdf
    importlib.reload(pdf)
    assert pdf.GOTENBERG_URL == "http://gotenberg:3000"
    assert pdf.GOTENBERG_USER == "u123"
    assert pdf.GOTENBERG_SENHA == "p456"


def test_nome_do_projeto_tem_precedencia(monkeypatch):
    """Se ambos existirem, GOTENBERG_USER ganha de SERVICE_USER_GOTENBERG."""
    import importlib
    monkeypatch.setenv("GOTENBERG_USER", "projeto")
    monkeypatch.setenv("SERVICE_USER_GOTENBERG", "coolify")
    import app.pdf as pdf
    importlib.reload(pdf)
    assert pdf.GOTENBERG_USER == "projeto"
