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
