"""Dinheiro em Decimal + valor por extenso em pt-BR.

Valor monetário nunca em float: 0.1 + 0.2 != 0.3, e uma petição soma dezenas de
rubricas. Tudo em Decimal com ROUND_HALF_UP (a convenção usada em cálculo
trabalhista), arredondando a 2 casas só na apresentação.
"""
from decimal import Decimal, ROUND_HALF_UP
from typing import Union

Numero = Union[int, float, str, Decimal]

CENTAVO = Decimal("0.01")


def dec(v: Numero) -> Decimal:
    """Converte para Decimal sem passar por float quando possível."""
    if isinstance(v, Decimal):
        return v
    if isinstance(v, float):
        return Decimal(str(v))  # str() evita o lixo binário do float
    return Decimal(v)


def centavos(v: Numero) -> Decimal:
    """Arredonda a 2 casas, meio-para-cima."""
    return dec(v).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def brl(v: Numero) -> str:
    """R$ 2.148,22"""
    q = centavos(v)
    inteiro, _, frac = f"{abs(q):.2f}".partition(".")
    grupos = f"{int(inteiro):,}".replace(",", ".")
    return f"{'-' if q < 0 else ''}R$ {grupos},{frac}"


# --- por extenso -----------------------------------------------------------

_UNI = ["", "um", "dois", "três", "quatro", "cinco", "seis", "sete", "oito", "nove"]
_DEZ_10 = ["dez", "onze", "doze", "treze", "quatorze", "quinze", "dezesseis",
           "dezessete", "dezoito", "dezenove"]
_DEZ = ["", "", "vinte", "trinta", "quarenta", "cinquenta", "sessenta",
        "setenta", "oitenta", "noventa"]
_CEM = ["", "cento", "duzentos", "trezentos", "quatrocentos", "quinhentos",
        "seiscentos", "setecentos", "oitocentos", "novecentos"]


def _ate_999(n: int) -> str:
    if n == 0:
        return ""
    if n == 100:
        return "cem"
    partes = []
    c, resto = divmod(n, 100)
    if c:
        partes.append(_CEM[c])
    if resto:
        if resto < 10:
            partes.append(_UNI[resto])
        elif resto < 20:
            partes.append(_DEZ_10[resto - 10])
        else:
            d, u = divmod(resto, 10)
            partes.append(_DEZ[d] + (f" e {_UNI[u]}" if u else ""))
    return " e ".join(partes)


def _liga_milhar(resto: int) -> str:
    """Regra do português: 'mil e duzentos' (resto redondo ou < 100),
    'dois mil, cento e quarenta e oito' (resto quebrado ≥ 100)."""
    return " e " if (resto < 100 or resto % 100 == 0) else ", "


def inteiro_por_extenso(n: int) -> str:
    """0 a 999.999."""
    if n == 0:
        return "zero"
    if n >= 1_000_000:
        raise ValueError("suportado até 999.999")
    milhares, resto = divmod(n, 1000)
    if not milhares:
        return _ate_999(resto)
    cabeca = "mil" if milhares == 1 else f"{_ate_999(milhares)} mil"
    if not resto:
        return cabeca
    return f"{cabeca}{_liga_milhar(resto)}{_ate_999(resto)}"


def valor_por_extenso(v: Numero) -> str:
    """2148.22 -> 'dois mil, cento e quarenta e oito reais e vinte e dois centavos'

    A vírgula antes da parte das centenas segue as peças da banca
    ('dois mil, cento e quarenta e oito reais').
    """
    q = centavos(v)
    reais = int(q)
    cent = int((q - reais) * 100)

    if reais == 0:
        corpo = ""
    elif reais == 1:
        corpo = "um real"
    else:
        corpo = f"{inteiro_por_extenso(reais)} reais"

    if cent == 0:
        return corpo or "zero reais"
    txt_cent = ("um centavo" if cent == 1 else f"{_ate_999(cent)} centavos")
    return f"{corpo} e {txt_cent}" if corpo else txt_cent


def brl_com_extenso(v: Numero) -> str:
    """R$ 2.148,22 (dois mil, cento e quarenta e oito reais e vinte e dois centavos)"""
    return f"{brl(v)} ({valor_por_extenso(v)})"
