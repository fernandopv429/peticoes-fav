"""A orientação de redação muda com o sindicato.

Sem isto, caso de porteiro do SIEMACO saía com cara de peça de vigilante
reaproveitada — citando periculosidade da vigilância e o descanso de 10 minutos
da CCT do SEEVISSP, que não existem naquela convenção. Base empírica:
`INICIAIS_REAIS/SIEMACO/00 - inicial jose.docx` e `Erick_Camargo_x_Evidence.docx`.
"""
from datetime import date
from decimal import Decimal

import pytest

from app.modelos import Caso
from app.redacao import ORIENTACAO_POR_CATEGORIA, _orientacao_categoria


def caso(categoria=None, funcao="Porteiro") -> Caso:
    return Caso(nome="x", funcao=funcao, admissao=date(2025, 1, 1),
                rescisao=date(2025, 12, 1), modalidade="sem_justa_causa",
                salario=Decimal("2031.57"), categoria=categoria)


def test_siemaco_pede_acumulo_em_20_por_cento():
    """As duas iniciais reais: 'percentual correspondente a 20% do salário
    contratual do reclamante por cada mês laborado'."""
    t = _orientacao_categoria(caso("asseio_conservacao"))
    assert "ACÚMULO" in t and "20%" in t


def test_vigilancia_pede_desvio_em_50_por_cento():
    t = _orientacao_categoria(caso("vigilancia", "Vigilante"))
    assert "DESVIO" in t and "50%" in t


@pytest.mark.parametrize("categoria", ["asseio_conservacao", "terceirizados"])
def test_fora_da_vigilancia_a_orientacao_proibe_as_teses_de_vigilante(categoria):
    """Periculosidade de vigilância e os 10 minutos são cláusulas do SEEVISSP.
    Numa peça de porteiro do SIEMACO, denunciam modelo reaproveitado."""
    t = _orientacao_categoria(caso(categoria))
    assert "NÃO cabem" in t
    assert "10 minutos" in t and "periculosidade" in t.lower()


def test_terceirizados_poe_a_sumula_331_no_eixo():
    t = _orientacao_categoria(caso("terceirizados"))
    assert "331" in t and "tomadora" in t.lower()


def test_sem_categoria_nao_ha_orientacao():
    """Orientação errada é pior que nenhuma: sem categoria confiável a peça sai
    genérica, e o gate já marca CATEGORIA_INDEFINIDA."""
    assert _orientacao_categoria(caso(None)) == ""


def test_toda_categoria_conhecida_tem_orientacao():
    from app.cct import SINDICATO_DA_CATEGORIA
    assert set(SINDICATO_DA_CATEGORIA) == set(ORIENTACAO_POR_CATEGORIA)
