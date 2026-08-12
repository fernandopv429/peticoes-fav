"""Competência territorial — art. 651 da CLT.

O critério é o LOCAL DA PRESTAÇÃO DOS SERVIÇOS. TRT errado manda a peça para o
juízo errado, então o que não é certo é sinalizado, não chutado.
"""
from datetime import date
from decimal import Decimal

from app.competencia import resolver
from app.modelos import Caso, Reclamada
from app.pipeline import gerar
from app.render.preencher import validar


def test_capital_e_regiao_metropolitana_sao_trt2():
    for mun in ("São Paulo", "Guarulhos", "Osasco", "Santo André", "Santos"):
        c = resolver(mun, "SP")
        assert c.regiao == 2 and not c.revisar, mun


def test_interior_paulista_cai_no_trt15_com_pedido_de_conferencia():
    c = resolver("Ribeirão Preto", "SP")
    assert c.regiao == 15 and c.revisar
    assert "confirmar" in c.motivo


def test_acentuacao_e_caixa_nao_atrapalham():
    assert resolver("SAO BERNARDO DO CAMPO", "sp").regiao == 2
    assert resolver("são bernardo do campo", "SP").regiao == 2


def test_estados_de_regiao_unica():
    assert resolver("Rio de Janeiro", "RJ").regiao == 1
    assert resolver("Belo Horizonte", "MG").regiao == 3
    assert resolver("Recife", "PE").regiao == 6


def test_formato_do_enderecamento():
    assert resolver("São Paulo", "SP").vara_cidade_regiao == "SÃO PAULO/SP – SEGUNDA REGIÃO"
    assert resolver("Campinas", "SP").vara_cidade_regiao == "CAMPINAS/SP – DÉCIMA QUINTA REGIÃO"


def test_uf_desconhecida_devolve_none():
    assert resolver("Lisboa", "XX") is None


def test_gate_bloqueia_sem_local_de_prestacao():
    v = validar("<p>ok</p>", [], Decimal("0"), categoria="vigilancia", competencia=None)
    assert not v.aprovado
    assert any(p.codigo == "COMPETENCIA_INDEFINIDA" for p in v.problemas)


def test_enderecamento_entra_na_peca():
    c = Caso(nome="x", funcao="Vigilante", admissao=date(2024, 1, 1),
             rescisao=date(2024, 9, 7), modalidade="sem_justa_causa",
             salario=Decimal("2148.22"), categoria="vigilancia",
             municipio_prestacao="Guarulhos", uf_prestacao="SP",
             reclamadas=[Reclamada(razao_social="X LTDA")])
    r = gerar(c, codigo="T", consultar_cct=False, consultar_cnpj=False,
              template="<p>AO JUÍZO DA VARA DO TRABALHO DE {{VARA_CIDADE_REGIAO}}</p>")
    assert "GUARULHOS/SP – SEGUNDA REGIÃO" in r.html
    assert r.validacao.aprovado
