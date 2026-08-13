"""O endpoint que recebe o formulário do Base44 cru.

Existe para o n8n não reimplementar o adaptador em expressão de nó. Estes
testes garantem que ele não passe a exigir tradução por fora.
"""
import pytest
from fastapi.testclient import TestClient

from app import servico
from app.entrevista import campos_ausentes

# Registro real do app 6a734d6c72c1f853994b8733 (id 6a74c2e6fe062ba4292e786b),
# o único dos seis do Marcos que bate com a ENTREVISTA ASSINADA.
MARCOS = {
    "id": "6a74c2e6fe062ba4292e786b",
    "RECL_NOME": "MARCOS MOREIRA PAULO",
    "RECL_CPF": "105.678.257-95",
    "FUNCAO": "Vigilante",
    "DATA_ADMISSAO": "2025-04-14",
    "DATA_RESCISAO": "2025-12-07",
    "tipo_dispensa": "sem_justa_causa",
    "escala": "12x36",
    "JORNADA_HORARIO": "das 19h às 07h",
    "email": "marcos81769111@gmail.com",
    "RECL1_NOME": "VIGSEG VIGILÂNCIA E SEGURANÇA DE VALORES LTDA",
    "RECL1_CNPJ": "04.542.518/0002-99",
    "RECL2_NOME": "GLP RÉGIS (Integral Médica)",
    "RECL2_CNPJ": "46.652.606/0001-02",
    "RECL2_ENDCOMPL": "Itapecerica da Serra/SP, CEP 06877-115",
    "folgas_trabalhadas": True,
    "FT_QTD_MEDIA": "5 a 6 por mês",
    "VAL_FT": "R$ 180 a R$ 200",
    "acumulo_funcao": True,
    "tem_periculosidade": True,
}


@pytest.fixture
def cliente(monkeypatch):
    monkeypatch.setattr(servico, "API_KEY", "k")
    return TestClient(servico.app)


CAB = {"X-API-Key": "k"}


def post(cliente, **extra):
    corpo = {"entrevista": MARCOS, "consultar_cct": False, "consultar_cnpj": False, "redigir_ia": False,
             "gerar_pdf": False, "persistir": False, **extra}
    return cliente.post("/peca/da-entrevista", json=corpo, headers=CAB)


def test_aceita_o_formulario_cru_sem_traducao(cliente):
    """O n8n manda o registro do Base44 como veio. Se este teste exigir
    tradução, a regra jurídica do adaptador vazou para o workflow."""
    r = post(cliente, salario="R$ 2.148,22")
    assert r.status_code == 200, r.text
    assert r.json()["codigo"] == MARCOS["id"]


def test_exige_autenticacao(cliente):
    assert cliente.post("/peca/da-entrevista",
                        json={"entrevista": MARCOS}).status_code == 401


def test_entrevista_sem_nome_e_422(cliente):
    r = cliente.post("/peca/da-entrevista",
                     json={"entrevista": {"RECL_CPF": "x"}}, headers=CAB)
    assert r.status_code == 422


def test_codigo_default_e_o_id_do_registro(cliente):
    """Idempotência: reenviar o mesmo webhook atualiza a peça, não duplica."""
    assert post(cliente, salario="R$ 1,00").json()["codigo"] == MARCOS["id"]


def test_codigo_explicito_prevalece(cliente):
    assert post(cliente, codigo="X-1", salario="R$ 1,00").json()["codigo"] == "X-1"


def test_devolve_o_que_faltou_no_formulario(cliente):
    corpo = post(cliente, salario="R$ 2.148,22").json()
    campos = {f["campo"] for f in corpo["campos_ausentes"]}
    # este registro não traz SALARIO nem a tarifa da condução
    assert "SALARIO" in campos
    assert "VAL_CONDUCAO" in campos
    assert all(f["efeito"] for f in corpo["campos_ausentes"])


def test_campos_ausentes_nao_reclama_do_que_existe():
    completo = {**MARCOS, "SALARIO": "R$ 2.148,22", "VAL_CONDUCAO": "R$ 10,00",
                "tem_adic_noturno": True}
    campos = {f["campo"] for f in campos_ausentes(completo)}
    assert not ({"SALARIO", "VAL_CONDUCAO", "tem_adic_noturno"} & campos)


def test_avisa_quando_o_noturno_foi_inferido():
    """Sem o campo explícito, a peça decide pelo horário — e isso vale
    R$ 3.592 no caso do Marcos. A especialista tem que saber que foi inferência."""
    aviso = next(f for f in campos_ausentes(MARCOS) if f["campo"] == "tem_adic_noturno")
    assert "SIM" in aviso["efeito"]          # "das 19h às 07h" cobre 22h-5h
