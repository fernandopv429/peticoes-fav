"""Cálculo determinístico das verbas. Nenhuma IA toca neste módulo.

As fórmulas foram calibradas contra peças reais da especialista — em especial a
do caso MARCOS (VIGSEG x GLP Régis), cujos valores estão travados em tests/.
Toda alteração aqui precisa passar naqueles testes.
"""
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from app.calculo.dinheiro import centavos, dec
from app.modelos import Caso

# Percentuais de reflexo sobre o principal. Verificados ao centavo em SEIS
# rubricas independentes da peça real do caso MARCOS (VIGSEG x GLP Régis),
# todas fechando em 34,75%.
#
# ⚠️ Nas peças, "FGTS + 40%" aparece como UM valor combinado de 10,50%
# (= 7,5% + 3,0%). Uma análise por mediana sobre o corpus chegou a sugerir
# 8,0%/3,2% — era artefato de a extração ora ler o combinado, ora o separado.
# O gabarito byte a byte manda: 7,5% e 3,0%.
REFLEXOS: dict[str, Decimal] = {
    "aviso_previo": Decimal("0.0400"),
    "dsr":          Decimal("0.0725"),
    "ferias_1_3":   Decimal("0.0700"),
    "decimo_terceiro": Decimal("0.0600"),
    "fgts":         Decimal("0.0750"),
    "multa_40":     Decimal("0.0300"),
}
TOTAL_REFLEXOS = sum(REFLEXOS.values())  # 0.3475

# A VERBA de FGTS usa a alíquota legal de 8% (art. 15, Lei 8.036/90). O REFLEXO
# de FGTS sobre outra verba é 7,5% — são coisas distintas, e usar o mesmo número
# nas duas subestimava o depósito do período.
ALIQUOTA_FGTS = Decimal("0.08")

TETO_VALOR_CAUSA = Decimal("400000.00")


@dataclass
class Verba:
    codigo: str
    rubrica: str
    principal: Decimal
    reflexos: dict[str, Decimal] = field(default_factory=dict)
    # 'calculado'  = fórmula determinística (auditável)
    # 'estimado'   = arbitrado pela IA, rotulado como estimativa na peça
    origem: str = "calculado"
    fundamento: str = ""

    @property
    def total(self) -> Decimal:
        return centavos(self.principal + sum(self.reflexos.values()))


def com_reflexos(codigo: str, rubrica: str, principal: Decimal, **kw) -> Verba:
    """Verba de natureza salarial — repercute nas demais rubricas."""
    p = centavos(principal)
    return Verba(codigo, rubrica, p,
                 {k: centavos(p * pct) for k, pct in REFLEXOS.items()}, **kw)


def sem_reflexo(codigo: str, rubrica: str, principal: Decimal, **kw) -> Verba:
    """Verba que não repercute (multas, indenizações)."""
    return Verba(codigo, rubrica, centavos(principal), {}, **kw)


# --- verbas rescisórias ----------------------------------------------------

def saldo_de_salario(c: Caso) -> Verba:
    dias = min(c.rescisao.day, 30)
    return sem_reflexo("VALOR_SALDO_SALARIO", "Saldo de salário",
                       dec(c.salario) / 30 * dias,
                       fundamento=f"{dias} dia(s) trabalhados no mês da rescisão")


def aviso_previo(c: Caso) -> Verba:
    """Indenizado. Base de 1 salário; a proporcionalidade da Lei 12.506/2011
    (+3 dias por ano) entra em dias, não no valor-base usado pelas peças."""
    return sem_reflexo("VALOR_AVISO_PREVIO", "Aviso prévio indenizado",
                       dec(c.salario), fundamento="art. 487, § 1º, CLT")


def decimo_terceiro(c: Caso) -> Verba:
    return sem_reflexo("VALOR_13", "13º salário proporcional",
                       dec(c.salario) / 12 * c.avos_13,
                       fundamento=f"{c.avos_13}/12 avos (ano-calendário)")


def ferias(c: Caso) -> Verba:
    valor = dec(c.salario) / 12 * c.avos_ferias * Decimal("4") / Decimal("3")
    return sem_reflexo("VALOR_FERIAS", "Férias proporcionais + 1/3", valor,
                       fundamento=f"{c.avos_ferias}/12 avos do período aquisitivo "
                                  f"+ 1/3 constitucional")


def fgts(c: Caso) -> Verba:
    return sem_reflexo("VALOR_FGTS", "FGTS do período",
                       dec(c.salario) * ALIQUOTA_FGTS * c.meses_contrato,
                       fundamento=f"8% x {c.meses_contrato} meses")


def multa_40(c: Caso) -> Verba:
    return sem_reflexo("VALOR_MULTA_40", "Multa de 40% do FGTS",
                       fgts(c).principal * Decimal("0.40"),
                       fundamento="art. 18, § 1º, Lei 8.036/90")


def multa_477(c: Caso) -> Verba:
    return sem_reflexo("VALOR_MULTA_477", "Multa do art. 477, § 8º, CLT",
                       dec(c.salario), fundamento="1 salário — verbas pagas fora do prazo")


def multa_467(c: Caso) -> Verba:
    """50% sobre as verbas rescisórias INCONTROVERSAS."""
    incontroversas = (saldo_de_salario(c).principal + aviso_previo(c).principal
                      + decimo_terceiro(c).principal + ferias(c).principal)
    return sem_reflexo("VALOR_ART_467", "Multa do art. 467 da CLT",
                       incontroversas * Decimal("0.50"),
                       fundamento="50% das verbas incontroversas")


# --- teses -----------------------------------------------------------------

def dano_moral(c: Caso) -> Verba:
    return sem_reflexo("VALOR_DANO_MORAL", "Indenização por dano moral",
                       c.base_dano_moral * 10,
                       fundamento="10x a maior remuneração")


def desvio_de_funcao(c: Caso) -> Verba:
    meses = c.meses_desvio or c.meses_contrato
    return com_reflexos("VALOR_DESVIO", "Desvio de função",
                        dec(c.salario) * c.pct_desvio * meses,
                        fundamento=f"{c.pct_desvio:.0%} x {meses} meses (CCT)")


def acumulo_de_funcao(c: Caso) -> Verba:
    return com_reflexos("VALOR_ACUMULO", "Acúmulo de função",
                        dec(c.salario) * c.pct_acumulo * c.meses_contrato,
                        fundamento=f"{c.pct_acumulo:.0%} x {c.meses_contrato} meses (CCT)")


def gratificacao_funcao(c: Caso) -> Verba:
    return com_reflexos("VALOR_GRATIFICACAO", "Gratificação de função",
                        dec(c.salario) * c.pct_gratificacao * c.meses_contrato,
                        fundamento=f"{c.pct_gratificacao:.0%} x {c.meses_contrato} meses (CCT)")


def assiduidade(c: Caso) -> Verba:
    """Diferença entre a bonificação prometida e a efetivamente paga."""
    diferenca = dec(c.assiduidade_prometida or 0) - dec(c.assiduidade_paga or 0)
    return com_reflexos("VALOR_ASSIDUIDADE", "Bonificação de assiduidade suprimida",
                        diferenca * c.meses_contrato,
                        fundamento=f"({c.assiduidade_prometida} - {c.assiduidade_paga}) "
                                   f"x {c.meses_contrato} meses")


def salarios_em_aberto(c: Caso) -> Verba:
    return com_reflexos("VALOR_SALARIOS_ABERTO", "Salários em aberto",
                        dec(c.salario) * c.salarios_em_aberto_meses,
                        fundamento=f"{c.salarios_em_aberto_meses} mês(es) não quitados")


def folgas_trabalhadas(c: Caso) -> Verba:
    """FTs pagas por fora — valor MENSAL x meses de contrato.

    A peça da especialista diz "gira em torno de R$ 180,00 mensais". Tratar o
    valor como por-folga (x 5,5 folgas) inflou a rubrica em 450% no caso MARCOS."""
    valor = dec(c.val_folgas_mensal) * c.meses_contrato
    return com_reflexos("VALOR_POR_FORA", "Folgas trabalhadas pagas por fora", valor,
                        fundamento="integração à remuneração")


# --- montagem --------------------------------------------------------------

def calcular(c: Caso) -> list[Verba]:
    """Todas as verbas determinísticas aplicáveis ao caso, guardadas por flag."""
    verbas = [saldo_de_salario(c), aviso_previo(c), decimo_terceiro(c), ferias(c),
              fgts(c), multa_40(c), multa_477(c), multa_467(c)]

    if c.tem_dano_moral:
        verbas.append(dano_moral(c))
    if c.tem_desvio:
        verbas.append(desvio_de_funcao(c))
    if c.tem_acumulo:
        verbas.append(acumulo_de_funcao(c))
    if c.tem_gratificacao_funcao:
        verbas.append(gratificacao_funcao(c))
    if c.tem_assiduidade and c.assiduidade_prometida and c.assiduidade_paga:
        verbas.append(assiduidade(c))
    if c.salarios_em_aberto_meses:
        verbas.append(salarios_em_aberto(c))
    if c.val_folgas_mensal:
        verbas.append(folgas_trabalhadas(c))

    return verbas


def valor_da_causa(verbas: list[Verba]) -> tuple[Decimal, bool]:
    """Soma com o teto de R$ 400.000,00. Devolve (valor, foi_limitado)."""
    soma = centavos(sum(v.total for v in verbas))
    if soma > TETO_VALOR_CAUSA:
        return TETO_VALOR_CAUSA, True
    return soma, False


def rito(valor_causa: Decimal, salario_minimo: Decimal = Decimal("1518.00")) -> str:
    """Sumaríssimo só até 40 salários mínimos (art. 852-A CLT). Decidido por
    código: a IA já sugeriu 'sumaríssimo' para causa de R$ 133 mil."""
    return "sumaríssimo" if valor_causa <= salario_minimo * 40 else "ordinário"
