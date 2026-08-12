"""Verbas por hora: a IA estima a QUANTIDADE, o código faz a conta.

Antes a IA devolvia o valor final e repetia o mesmo número para rubricas de
bases diferentes (caso MARCOS: R$ 2.873,68 idênticos para horas extras,
intervalo e minutos residuais). Separando quantidade de aritmética, cada rubrica
tem fórmula própria e o resultado é auditável — dá para conferir horas × taxa ×
meses na peça.

MULTIPLICADORES — calibrados contra a peça real do caso MARCOS:

  intervalo art. 71: só o ADICIONAL (0,60). Reproduz R$ 615 contra os R$ 635,10
  da peça (3% de diferença) com 15 plantões/mês × 1h. Usar hora+adicional (1,60)
  daria R$ 1.640 — quase 3x o valor real. As peças pedem "diferenças", ou seja,
  a hora já foi paga e falta o adicional.

  domingos/feriados: hora + 100% (2,00). Com ~5 folgas/mês × 12h reproduz a
  ordem de grandeza da peça; ali a hora inteira é devida.

  adicional noturno: NÃO é multiplicador — ver `_equivalente_noturno`. Aplicar só
  os 20% do art. 73 dava 53% menos que a peça do MARCOS. Faltava a hora noturna
  reduzida do § 1º (52min30s valem 1 hora), que sozinha acrescenta ~14% de horas.
  Com as duas parcelas: 105 h reais/mês viram 39 h-equivalentes (contra 21), e o
  desvio cai para −12% no MARCOS.

Onde as peças divergem entre si, o critério adotado é o LEGAL, não o que faz
bater com uma delas — decisão do Fernando em 09/08/2026.
"""
from decimal import Decimal
from typing import Optional

from app.calculo.dinheiro import dec
from app.calculo.verbas import Verba, com_reflexos
from app.modelos import Caso

DIVISOR_MENSAL = Decimal("220")

# (multiplicador aplicado ao valor-hora, rótulo da rubrica)
# Multiplicador < 1 = só o adicional ("diferenças"); > 1 = hora + adicional.
RUBRICAS: dict[str, tuple[Decimal, str]] = {
    "horas_extras_mes":      (Decimal("0.60"), "Horas extras (excedentes à 8ª diária e 44ª semanal)"),
    "intervalo_art71_mes":   (Decimal("0.60"), "Horas extras — intervalo do art. 71 da CLT"),
    "minutos_residuais_mes": (Decimal("0.60"), "Horas extras — minutos que antecedem e sucedem"),
    "dez_minutos_mes":       (Decimal("0.60"), "Descanso de 10 minutos (cláusula 33ª da CCT)"),
    # Noturno tem tratamento próprio (ver `_equivalente_noturno`): não é um
    # multiplicador simples, porque soma o adicional do art. 73 à diferença
    # gerada pela hora noturna reduzida do § 1º.
    "domingos_feriados_mes": (Decimal("2.00"), "Domingos, folgas e feriados com adicional de 100%"),
}

PCT_PERICULOSIDADE = Decimal("0.30")
PCT_ADICIONAL_NOTURNO = Decimal("0.20")          # art. 73, caput (urbano)
MINUTOS_HORA_NOTURNA = Decimal("52.5")           # art. 73, § 1º

RUBRICA_NOTURNO = "Adicional noturno e hora noturna reduzida (art. 73 CLT)"


def _equivalente_noturno(horas_reais: Decimal) -> Decimal:
    """Horas-equivalentes devidas por N horas reais entre 22h e 5h.

    São DUAS parcelas, e eu aplicava só a primeira:
      1. adicional de 20% (art. 73, caput);
      2. hora noturna reduzida (§ 1º): 52min30s valem 1 hora, então N horas
         reais equivalem a N x 60/52,5 horas fictas — a diferença é hora extra
         não paga.

    Só o adicional dava, no caso MARCOS, 53% menos que a peça real. Com as duas
    parcelas a diferença cai para ~12%.
    """
    fictas = horas_reais * 60 / MINUTOS_HORA_NOTURNA
    reducao = fictas - horas_reais              # horas a mais pela redução
    adicional = fictas * PCT_ADICIONAL_NOTURNO  # 20% sobre as horas fictas
    return reducao + adicional


def valor_hora(caso: Caso) -> Decimal:
    return dec(caso.salario) / DIVISOR_MENSAL


def de_quantidades(caso: Caso, quantidades: dict[str, float],
                   *, adicional_he: Optional[Decimal] = None) -> list[Verba]:
    """Horas/mês -> verbas. `adicional_he` vem da CCT quando disponível."""
    vh = valor_hora(caso)
    meses = caso.meses_contrato
    verbas: list[Verba] = []

    for chave, (multiplicador, rubrica) in RUBRICAS.items():
        horas = dec(quantidades.get(chave) or 0)
        if horas <= 0:
            continue
        # o adicional da CCT substitui o default só nas rubricas de hora extra
        mult = multiplicador
        if adicional_he is not None and chave in (
                "horas_extras_mes", "intervalo_art71_mes",
                "minutos_residuais_mes", "dez_minutos_mes"):
            mult = adicional_he
        verbas.append(com_reflexos(
            f"VALOR_{chave.replace('_mes', '').upper()}", rubrica,
            vh * mult * horas * meses, origem="estimado",
            fundamento=f"{horas:g} h/mês x {meses} meses x valor-hora "
                       f"(salário/220) x {mult:g} — valor principal estimado"))

    horas_noturnas = dec(quantidades.get("adicional_noturno_mes") or 0)
    if horas_noturnas > 0:
        equivalente = _equivalente_noturno(horas_noturnas)
        verbas.append(com_reflexos(
            "VALOR_ADICIONAL_NOTURNO", RUBRICA_NOTURNO,
            vh * equivalente * meses, origem="estimado",
            fundamento=f"{horas_noturnas:g} h noturnas/mês x {meses} meses: "
                       f"adicional de 20% (art. 73) + hora reduzida de 52min30s "
                       f"(§ 1º) = {equivalente:.3f} h-equivalentes/mês — "
                       f"valor principal estimado"))

    # Periculosidade incide sobre as horas extras já apuradas (Súmula 132, I, TST)
    if caso.tem_periculosidade:
        base_he = sum(v.principal for v in verbas if "Horas extras" in v.rubrica)
        if base_he:
            verbas.append(com_reflexos(
                "VALOR_PERICULOSIDADE_HE",
                "Periculosidade sobre as horas extras (Súm. 132, I, TST)",
                base_he * PCT_PERICULOSIDADE, origem="estimado",
                fundamento="30% sobre as horas extras — valor principal estimado"))

    return verbas


def beneficios_das_folgas(caso: Caso, *, valor_alimentacao_dia: Optional[Decimal] = None,
                          valor_transporte_dia: Optional[Decimal] = None) -> list[Verba]:
    """Auxílio-alimentação e vale-transporte das folgas trabalhadas.

    A empresa não paga esses benefícios nas folgas que o empregado acaba
    trabalhando — viram pedido próprio. Os valores diários vêm da CCT; sem eles
    a rubrica não entra (não se arbitra valor de benefício)."""
    verbas: list[Verba] = []
    folgas = dec(caso.folgas_trabalhadas_mes or 0)
    if folgas <= 0:
        return verbas
    meses = caso.meses_contrato

    if caso.vale_alimentacao and valor_alimentacao_dia:
        verbas.append(com_reflexos(
            "VALOR_AUX_ALIM_TOTAL", "Auxílio-alimentação das folgas trabalhadas",
            dec(valor_alimentacao_dia) * folgas * meses,
            fundamento=f"{valor_alimentacao_dia}/dia x {folgas:g} folgas x {meses} meses (CCT)"))

    if caso.vale_transporte and valor_transporte_dia:
        verbas.append(com_reflexos(
            "VALOR_VT_TOTAL", "Vale-transporte das folgas trabalhadas",
            dec(valor_transporte_dia) * folgas * meses,
            fundamento=f"{valor_transporte_dia}/dia x {folgas:g} folgas x {meses} meses (CCT)"))

    return verbas
