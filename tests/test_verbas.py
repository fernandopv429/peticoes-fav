"""Testes contra o gabarito da especialista.

Os valores esperados são os que ela própria produziu num caso real de vigilante
(salário R$ 2.148,22). Se um destes quebrar, o cálculo divergiu da prática da
banca — não é para "ajustar o teste", é para investigar a fórmula.
"""
from datetime import date
from decimal import Decimal

import pytest

from app.calculo.dinheiro import centavos, valor_por_extenso
from app.calculo.verbas import (REFLEXOS, TOTAL_REFLEXOS, calcular, com_reflexos,
                                rito, valor_da_causa)
from app.modelos import Caso

SALARIO = Decimal("2148.22")


@pytest.fixture
def caso() -> Caso:
    # 8 meses de contrato, rescisão em 07/09 -> 8 avos, 7 dias de saldo
    return Caso(nome="Marcos", funcao="Vigilante",
                admissao=date(2024, 1, 1), rescisao=date(2024, 9, 7),
                modalidade="sem_justa_causa", salario=SALARIO,
                categoria="vigilancia", escala="12x36",
                tem_dano_moral=True, tem_desvio=True)


def por_codigo(verbas, codigo):
    return next(v for v in verbas if v.codigo == codigo)


# --- gabarito --------------------------------------------------------------

@pytest.mark.parametrize("codigo,esperado", [
    ("VALOR_SALDO_SALARIO", "501.25"),
    ("VALOR_AVISO_PREVIO",  "2148.22"),
    ("VALOR_13",            "1432.15"),
    ("VALOR_FERIAS",        "1909.53"),
    ("VALOR_MULTA_477",     "2148.22"),
    ("VALOR_ART_467",       "2995.58"),
    ("VALOR_DANO_MORAL",    "21482.20"),
    ("VALOR_DESVIO",        "8592.88"),
])
def test_bate_com_a_peca_da_especialista(caso, codigo, esperado):
    assert por_codigo(calcular(caso), codigo).principal == Decimal(esperado)


def test_meses_e_avos(caso):
    assert caso.meses_contrato == 8
    assert caso.avos == 8


def test_467_e_metade_das_incontroversas(caso):
    v = calcular(caso)
    incontroversas = sum(por_codigo(v, c).principal for c in
                         ("VALOR_SALDO_SALARIO", "VALOR_AVISO_PREVIO",
                          "VALOR_13", "VALOR_FERIAS"))
    # centavos() arredonda meio-para-cima: 5991,15/2 = 2995,575 -> 2995,58,
    # que é exatamente o valor da peça da especialista.
    assert por_codigo(v, "VALOR_ART_467").principal == centavos(incontroversas / 2)


# --- reflexos --------------------------------------------------------------

def test_reflexos_somam_34_75_por_cento():
    """Verificado em 6 rubricas independentes da peça do caso MARCOS."""
    assert TOTAL_REFLEXOS == Decimal("0.3475")


def test_reflexo_e_proporcional_ao_principal():
    """O bug das peças reais: bloco de reflexos copiado entre principais
    diferentes. Aqui o reflexo é sempre derivado do próprio principal."""
    a = com_reflexos("X", "x", Decimal("1000.00"))
    b = com_reflexos("Y", "y", Decimal("32000.00"))
    assert a.reflexos["dsr"] == Decimal("72.50")
    assert b.reflexos["dsr"] == Decimal("2320.00")
    assert a.total == Decimal("1347.50")     # 1000 + 34,75%


def test_multa_40_e_40_por_cento_do_fgts():
    assert REFLEXOS["multa_40"] == REFLEXOS["fgts"] * Decimal("0.40")


def test_verbas_rescisorias_nao_tem_reflexo(caso):
    """Reflexo de rescisória sobre rescisória seria dupla contagem."""
    for cod in ("VALOR_SALDO_SALARIO", "VALOR_13", "VALOR_MULTA_477", "VALOR_DANO_MORAL"):
        assert por_codigo(calcular(caso), cod).reflexos == {}


# --- valor da causa e rito -------------------------------------------------

def test_teto_de_400_mil():
    verbas = [com_reflexos("X", "x", Decimal("500000.00"))]
    valor, limitado = valor_da_causa(verbas)
    assert valor == Decimal("400000.00") and limitado is True


def test_rito_ordinario_acima_de_40_salarios_minimos():
    assert rito(Decimal("133601.57")) == "ordinário"
    assert rito(Decimal("30000.00")) == "sumaríssimo"


# --- extenso ---------------------------------------------------------------

@pytest.mark.parametrize("valor,esperado", [
    (SALARIO, "dois mil, cento e quarenta e oito reais e vinte e dois centavos"),
    (Decimal("2271.74"), "dois mil, duzentos e setenta e um reais e setenta e quatro centavos"),
    (Decimal("1000.00"), "mil reais"),
    (Decimal("100.00"), "cem reais"),
])
def test_por_extenso_bate_com_as_pecas(valor, esperado):
    assert valor_por_extenso(valor) == esperado


def test_flags_desligadas_removem_a_verba():
    c = Caso(nome="x", funcao="y", admissao=date(2024, 1, 1), rescisao=date(2024, 9, 7),
             modalidade="sem_justa_causa", salario=SALARIO)
    codigos = {v.codigo for v in calcular(c)}
    assert "VALOR_DANO_MORAL" not in codigos
    assert "VALOR_DESVIO" not in codigos


# --- gabarito 2: caso MARCOS (VIGSEG x GLP Régis) --------------------------
# Contrato 14/04/2025 a 07/12/2025, vigilante, piso R$ 2.148,22.
# Peça real: "Analise IA/MARCOS/Feita pela especialista.docx".

@pytest.fixture
def marcos() -> Caso:
    return Caso(nome="Marcos Moreira Paulo", funcao="Vigilante",
                admissao=date(2025, 4, 14), rescisao=date(2025, 12, 7),
                modalidade="sem_justa_causa", salario=SALARIO,
                categoria="vigilancia", escala="12x36",
                municipio_prestacao="Itapecerica da Serra", uf_prestacao="SP")


def test_avos_contam_da_admissao_e_nao_do_inicio_do_ano(marcos):
    """Contrato iniciado em abril: a conta antiga dava 11 avos (só olhava o mês
    da rescisão). A peça usa 8/12 — abril conta (17 dias), dezembro não (7)."""
    assert marcos.avos == 8


@pytest.mark.parametrize("codigo,esperado", [
    ("VALOR_SALDO_SALARIO", "501.25"),    # 7 dias de dezembro/2025
    ("VALOR_AVISO_PREVIO",  "2148.22"),
    ("VALOR_13",            "1432.15"),   # 8/12
    ("VALOR_FERIAS",        "1909.53"),   # 8/12 + 1/3
    ("VALOR_MULTA_477",     "2148.22"),
])
def test_rescisorias_do_marcos(marcos, codigo, esperado):
    assert por_codigo(calcular(marcos), codigo).principal == Decimal(esperado)


def test_467_do_marcos_bate_com_a_peca(marcos):
    """A peça traz R$ 2.995,57; a conta exata dá ...,575 e arredonda para ,58.
    Um centavo de diferença de arredondamento, não de fórmula."""
    calculado = por_codigo(calcular(marcos), "VALOR_ART_467").principal
    assert abs(calculado - Decimal("2995.57")) <= Decimal("0.01")


@pytest.mark.parametrize("principal,reflexos_esperados", [
    # (principal, {dsr, aviso, 13º, férias, fgts+40%}) — 6 rubricas da peça real
    ("522.00",  ("37.85", "20.88", "31.32", "36.54", "54.80")),
    ("635.10",  ("46.04", "25.40", "38.10", "44.46", "66.70")),
    ("3045.00", ("220.78", "121.80", "182.70", "213.14", "319.73")),
    ("7830.00", ("567.67", "313.20", "469.80", "548.10", "822.14")),
    ("1261.50", ("91.45", "50.46", "75.68", "88.31", "132.44")),
])
def test_reflexos_batem_com_a_peca(principal, reflexos_esperados):
    """FGTS+40% aparece combinado na peça (10,50% = 7,5% + 3,0%).

    Tolerância de 5 centavos, não igualdade exata: nas peças o percentual efetivo
    oscila entre 7,2492% e 7,2506% para o mesmo "7,25%", porque ela arredonda em
    passos intermediários que não dá para reconstruir. Exigir centavo exato
    testaria o arredondamento dela, não a fórmula."""
    TOLERANCIA = Decimal("0.05")
    v = com_reflexos("X", "x", Decimal(principal))
    dsr, aviso, d13, fer, fgts40 = (Decimal(x) for x in reflexos_esperados)
    assert abs(v.reflexos["dsr"] - dsr) <= TOLERANCIA
    assert abs(v.reflexos["aviso_previo"] - aviso) <= TOLERANCIA
    assert abs(v.reflexos["decimo_terceiro"] - d13) <= TOLERANCIA
    assert abs(v.reflexos["ferias_1_3"] - fer) <= TOLERANCIA
    assert abs((v.reflexos["fgts"] + v.reflexos["multa_40"]) - fgts40) <= TOLERANCIA
    # o TOTAL, esse, tem que fechar em 34,75%
    assert abs(v.total - Decimal(principal) * Decimal("1.3475")) <= TOLERANCIA
