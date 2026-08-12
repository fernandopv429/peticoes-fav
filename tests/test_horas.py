"""Verbas por hora — a IA dá a quantidade, o código faz a conta."""
from datetime import date
from decimal import Decimal

from app.calculo.horas import RUBRICAS, beneficios_das_folgas, de_quantidades, valor_hora
from app.modelos import Caso


def caso_marcos() -> Caso:
    return Caso(nome="Marcos", funcao="Vigilante", admissao=date(2025, 4, 14),
                rescisao=date(2025, 12, 7), modalidade="sem_justa_causa",
                salario=Decimal("2148.22"), categoria="vigilancia", escala="12x36",
                folgas_trabalhadas_mes=Decimal("5.5"), vale_alimentacao=True)


def test_valor_hora_e_salario_sobre_220():
    assert round(valor_hora(caso_marcos()), 4) == round(Decimal("2148.22") / 220, 4)


def test_rubricas_diferentes_geram_valores_diferentes():
    """O bug: a IA devolvia o mesmo valor para rubricas de bases distintas.
    Com quantidades diferentes, os valores agora divergem."""
    v = de_quantidades(caso_marcos(),
                       {"horas_extras_mes": 15, "domingos_feriados_mes": 66})
    valores = {x.principal for x in v}
    assert len(valores) == 2


def test_intervalo_art71_reproduz_a_peca_real():
    """Peça do MARCOS: R$ 635,10 de principal. 15 plantões x 1h, só o adicional
    de 60% (as peças pedem 'diferenças' — a hora já foi paga)."""
    v = de_quantidades(caso_marcos(), {"intervalo_art71_mes": 15})
    principal = next(x.principal for x in v if "art. 71" in x.rubrica)
    assert abs(principal - Decimal("635.10")) / Decimal("635.10") < Decimal("0.05")


def test_quantidade_zero_nao_vira_rubrica():
    assert de_quantidades(caso_marcos(), {"horas_extras_mes": 0}) == []


def test_periculosidade_incide_sobre_as_horas_extras():
    c = caso_marcos()
    c.tem_periculosidade = True
    v = de_quantidades(c, {"horas_extras_mes": 15})
    pericul = next(x for x in v if "Periculosidade" in x.rubrica)
    he = next(x for x in v if "Horas extras" in x.rubrica)
    assert pericul.principal == (he.principal * Decimal("0.30")).quantize(Decimal("0.01"))


def test_beneficio_sem_valor_da_cct_nao_entra():
    """Não se arbitra valor de benefício — sem o dado da CCT, a rubrica fica fora."""
    assert beneficios_das_folgas(caso_marcos(), valor_alimentacao_dia=None) == []
    v = beneficios_das_folgas(caso_marcos(), valor_alimentacao_dia=Decimal("42.00"))
    assert len(v) == 1 and "alimentação" in v[0].rubrica


def test_multiplicadores_documentam_a_calibracao():
    """Intervalo/HE usam só o adicional (0,60); domingos usam hora + 100% (2,00)."""
    assert RUBRICAS["intervalo_art71_mes"][0] == Decimal("0.60")
    assert RUBRICAS["domingos_feriados_mes"][0] == Decimal("2.00")


def test_criterio_de_horas_e_decisao_explicita():
    """As peças reais divergem na base: MARCOS conta por plantão (15,5 h/mês no
    intervalo do art. 71), JONATHAN conta por dia do mês (31,3) — o dobro, para
    a mesma rubrica. Não há constante que reproduza as duas; vira parâmetro,
    com o conservador como padrão."""
    from app.modelos import Caso
    assert caso_marcos().criterio_horas == "por_plantao"
    c = caso_marcos()
    c.criterio_horas = "por_dia_do_mes"
    assert c.criterio_horas == "por_dia_do_mes"


def test_avos_de_ferias_usam_o_periodo_aquisitivo():
    """Peça do JONATHAN: 13º 12/12 mas férias 11/12 — critérios diferentes.
    Ano-calendário nos dois dava 10 e subestimava as férias."""
    c = Caso(nome="Jonathan", funcao="Controlador", admissao=date(2025, 1, 25),
             rescisao=date(2025, 12, 11), modalidade="coacao_demissao",
             salario=Decimal("1912.07"))
    assert c.avos_ferias == 11
    assert c.avos_13 == 10      # regra dos 15 dias; a peça usou 12, generoso


def test_noturno_soma_adicional_e_hora_reduzida():
    """Art. 73 da CLT tem DUAS parcelas, e eu aplicava só a primeira:
    o adicional de 20% (caput) e a hora reduzida de 52min30s (§ 1º).
    105 h reais/mês -> 39 h-equivalentes, não 21."""
    from app.calculo.horas import _equivalente_noturno
    eq = _equivalente_noturno(Decimal(105))
    assert abs(eq - Decimal("39.00")) < Decimal("0.01")
    # só o adicional daria 21 — 46% menos
    assert eq > Decimal(105) * Decimal("0.20") * Decimal("1.8")


def test_noturno_entra_com_rubrica_propria():
    v = de_quantidades(caso_marcos(), {"adicional_noturno_mes": 105})
    noturno = next(x for x in v if "noturno" in x.rubrica.lower())
    assert "art. 73" in noturno.rubrica
    assert "52min30s" in noturno.fundamento
