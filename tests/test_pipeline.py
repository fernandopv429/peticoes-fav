"""Pipeline ponta a ponta — é a sequência que produz peça certa ou errada."""
from datetime import date
from decimal import Decimal

import pytest

from app.modelos import Caso, Reclamada
from app.pipeline import gerar

TEMPLATE = ("<html><body>"
            "<p>{{RECL_NOME}}, {{RECL_FUNCAO}}, admitido em {{DATA_ADMISSAO}}</p>"
            "<p>Salário: {{SALARIO}}</p>"
            "{{#tem_tomadora}}<p>DA SÚMULA 331 DO C. TST</p>{{/tem_tomadora}}"
            "{{#desvio_funcao}}<p>DO DESVIO: {{VALOR_DESVIO}}</p>{{/desvio_funcao}}"
            "{{#periculosidade}}<p>DA PERICULOSIDADE</p>{{/periculosidade}}"
            "<p>Dá-se à causa {{VALOR_CAUSA_TOTAL}}, rito {{RITO}}.</p>"
            "</body></html>")


@pytest.fixture
def caso():
    return Caso(nome="Marcos", funcao="Vigilante",
               admissao=date(2024, 1, 1), rescisao=date(2024, 9, 7),
               modalidade="sem_justa_causa", salario=Decimal("2148.22"),
               categoria="vigilancia",
               municipio_prestacao="São Paulo", uf_prestacao="SP",
               escala="12x36", tem_desvio=True, tem_dano_moral=True,
               reclamadas=[Reclamada(razao_social="VIGSEG LTDA"),
                           Reclamada(razao_social="TOMADORA SA", tomadora=True)])


def test_gera_peca_aprovada_sem_ia(caso):
    r = gerar(caso, codigo="T-1", consultar_cct=False, consultar_cnpj=False, template=TEMPLATE)
    assert r.validacao.aprovado, r.validacao.como_dict()
    assert r.status == "redigido"
    assert "{{" not in r.html


def test_sumula_331_entra_quando_ha_tomadora(caso):
    r = gerar(caso, codigo="T-2", consultar_cct=False, consultar_cnpj=False, template=TEMPLATE)
    assert "SÚMULA 331" in r.html


def test_sumula_331_sai_quando_nao_ha_tomadora(caso):
    caso.reclamadas = [Reclamada(razao_social="SO A EMPREGADORA")]
    r = gerar(caso, codigo="T-3", consultar_cct=False, consultar_cnpj=False, template=TEMPLATE)
    assert "SÚMULA 331" not in r.html


def test_capitulo_sem_suporte_nao_entra(caso):
    """Peça real saiu com capítulos que o caso não sustentava."""
    r = gerar(caso, codigo="T-4", consultar_cct=False, consultar_cnpj=False, template=TEMPLATE)
    assert "PERICULOSIDADE" not in r.html


def test_valor_da_causa_no_texto_e_o_calculado(caso):
    r = gerar(caso, codigo="T-5", consultar_cct=False, consultar_cnpj=False, template=TEMPLATE)
    from app.calculo.dinheiro import brl
    assert brl(r.valor_causa) in r.html


def test_trace_registra_origem_dos_percentuais(caso):
    r = gerar(caso, codigo="T-6", consultar_cct=False, consultar_cnpj=False, template=TEMPLATE)
    assert isinstance(r.trace, list)
    assert r.resumo()["validacao"]["aprovado"] is True


def test_resumo_serializa_o_que_o_pocketbase_espera():
    """`caso` e `validacao` vão como JSON; `peca_html` é texto longo (~110 KB) e
    por isso o campo no PocketBase precisa ser do tipo `editor`, não `text`."""
    c = Caso(nome="x", funcao="Vigilante", admissao=date(2024, 1, 1),
             rescisao=date(2024, 9, 7), modalidade="sem_justa_causa",
             salario=Decimal("2148.22"), categoria="vigilancia",
             municipio_prestacao="São Paulo", uf_prestacao="SP")
    r = gerar(c, codigo="P-1", consultar_cct=False, consultar_cnpj=False, template=TEMPLATE)
    resumo = r.resumo()
    assert isinstance(resumo["valor_causa"], str)      # Decimal não é JSON-serializável
    assert isinstance(resumo["validacao"], dict)
    assert isinstance(c.model_dump(mode="json"), dict)
