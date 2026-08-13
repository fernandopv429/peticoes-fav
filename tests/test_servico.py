"""A API é pública no Coolify. Estes testes guardam a porta.

Cada POST atendido gasta uma requisição Opus e grava dados de cliente no
PocketBase, então "esqueci de configurar a chave" não pode virar API aberta.
"""
import pytest
from fastapi.testclient import TestClient

from app import servico

CORPO = {"codigo": "TESTE", "caso": {}}


@pytest.fixture
def cliente():
    return TestClient(servico.app)


def test_health_dispensa_chave(cliente):
    """É o que o Coolify chama para decidir se o deploy subiu."""
    r = cliente.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_health_nao_vaza_credencial(cliente, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-segredo")
    corpo = cliente.get("/health").json()
    assert corpo["ia"] is True                      # diz que TEM
    assert "sk-ant-segredo" not in str(corpo)       # mas não qual é


@pytest.mark.parametrize("rota", ["/peca/gerar", "/peca/previa"])
def test_sem_api_key_no_ambiente_o_servico_falha_fechado(cliente, monkeypatch, rota):
    """Variável ausente = 503, nunca "passa livre"."""
    monkeypatch.setattr(servico, "API_KEY", "")
    assert cliente.post(rota, json=CORPO).status_code == 503


@pytest.mark.parametrize("rota", ["/peca/gerar", "/peca/previa"])
@pytest.mark.parametrize("enviada", [None, "", "errada", "chave-certa-mais"])
def test_chave_ausente_ou_errada_e_401(cliente, monkeypatch, rota, enviada):
    monkeypatch.setattr(servico, "API_KEY", "chave-certa")
    cabecalhos = {} if enviada is None else {"X-API-Key": enviada}
    assert cliente.post(rota, json=CORPO, headers=cabecalhos).status_code == 401


def test_chave_certa_passa_da_autenticacao(cliente, monkeypatch):
    """422 (corpo inválido) já prova que passou do guarda — é o que interessa
    aqui; gerar peça de verdade é assunto do test_pipeline."""
    monkeypatch.setattr(servico, "API_KEY", "chave-certa")
    r = cliente.post("/peca/gerar", json=CORPO, headers={"X-API-Key": "chave-certa"})
    assert r.status_code == 422


def test_redigir_ia_vem_ligado_por_padrao():
    """O ponto do serviço é a IA redigir. Já saiu peça sem os capítulos
    narrativos porque o campo nem existia no PedidoGerar."""
    assert servico.PedidoGerar.model_fields["redigir_ia"].default is True


# --- entrega do PDF ---------------------------------------------------------
# Base64 dentro do JSON obriga o n8n a decodificar num nó Code e infla o corpo
# em ~33%. Com `Accept: application/pdf` o nó HTTP já recebe binário.

def _resp(pdf=b"%PDF-1.4 fake", **extra):
    from unittest.mock import Mock
    from app.servico import _entregar
    corpo = {"status": "redigido", "valor_causa": "68794.75", "rito": "ordinário",
             "registro_id": "abc123",
             "campos_ausentes": [{"campo": "SALARIO", "efeito": "x"}], **extra}
    req = Mock(); req.headers = {"accept": "application/pdf"}
    return _entregar(req, corpo, pdf, "MARCOS")


def test_sem_accept_pdf_continua_json():
    from unittest.mock import Mock
    from app.servico import _entregar
    req = Mock(); req.headers = {"accept": "application/json"}
    saida = _entregar(req, {"status": "redigido"}, b"%PDF", "X")
    assert isinstance(saida, dict) and saida["status"] == "redigido"


def test_accept_pdf_devolve_binario():
    r = _resp()
    assert r.media_type == "application/pdf"
    assert r.body.startswith(b"%PDF")


def test_metadados_vao_nos_cabecalhos():
    """Trocar JSON por PDF não pode perder valor da causa nem o gate."""
    h = _resp().headers
    assert h["x-valor-causa"] == "68794.75"
    assert h["x-status"] == "redigido"
    assert h["x-registro-id"] == "abc123"
    assert "SALARIO" in h["x-campos-ausentes"]
    assert 'filename="MARCOS.pdf"' in h["content-disposition"]


def test_cabecalho_aceita_nome_com_acento():
    """Cabeçalho HTTP é latin-1; 'JOSÉ' cru derruba a resposta inteira."""
    from app.servico import _cabecalho_seguro
    assert _cabecalho_seguro("JOSÉ CARLOS").encode("latin-1")


def test_sem_pdf_com_accept_pdf_e_409_e_nao_200_vazio():
    import pytest as _pt
    from fastapi import HTTPException
    with _pt.raises(HTTPException) as e:
        _resp(pdf=None)
    assert e.value.status_code == 409
    assert e.value.detail["erro"] == "PDF não gerado"


def test_cabecalho_translitera_em_vez_de_trocar_por_interrogacao():
    """"ordinário" virava "ordin?rio" com errors='replace'."""
    from app.servico import _cabecalho_seguro
    assert _cabecalho_seguro("ordinário") == "ordinario"
    assert _cabecalho_seguro("JOSÉ CARLOS") == "JOSE CARLOS"
