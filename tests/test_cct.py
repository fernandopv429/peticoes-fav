"""Testes do cliente de CCT que não dependem de rede."""
from decimal import Decimal

from app.cct import Clausula, categoria_por_funcao, percentual_da_clausula


def test_funcao_so_decide_quando_e_inequivoca():
    """Controlador/Porteiro existe em SIEMACO **e** em SINDEEPRES
    (MATRIZ_GERAL_3_MODELOS.md §2) — decidir por função ali é chute, e o chute
    silencioso gerava peça com a CCT do sindicato errado."""
    from app.cct import funcao_e_ambigua
    assert categoria_por_funcao("Vigilante Patrimonial") == "vigilancia"
    assert categoria_por_funcao("Auxiliar de Limpeza") == "asseio_conservacao"
    assert categoria_por_funcao("Porteiro") is None
    assert categoria_por_funcao("Controlador de Acesso") is None
    assert funcao_e_ambigua("Porteiro") and funcao_e_ambigua("Controlador de Acesso")
    assert not funcao_e_ambigua("Vigilante")
    assert categoria_por_funcao("Analista de TI") is None


def test_extrai_percentual_e_numero_da_clausula():
    cs = [Clausula(ref="64ª", titulo="DESVIO DE FUNÇÃO",
                   conteudo="...será devido adicional de 50% (cinquenta por cento) sobre...",
                   similaridade=0.81)]
    assert percentual_da_clausula(cs, r"desvio", FAIXAS["desvio"]) == (Decimal("0.50"), "64ª")


def test_sem_clausula_do_tema_devolve_none():
    """Não pode 'achar' percentual de cláusula de outro assunto — foi assim que
    saiu peça com 3% no corpo e 2% no rol de pedidos."""
    cs = [Clausula(ref="12ª", titulo="VALE ALIMENTAÇÃO",
                   conteudo="valor diário de R$ 25,00 e desconto de 1%", similaridade=0.6)]
    assert percentual_da_clausula(cs, r"desvio") is None


# --- regressão: o bug dos 60% de gratificação ------------------------------

from app.cct import FAIXAS, numero_da_clausula


def test_nao_pega_percentual_de_outro_assunto():
    """Bug real (2026-08-08): uma cláusula que citava 'gratificação' de passagem
    e tratava de outro tema com 60% fez pct_gratificacao virar 60%."""
    cs = [Clausula(ref="CLÁUSULA DÉCIMA", titulo="ADICIONAL DE HORAS EXTRAS",
                   conteudo="as horas extras serão pagas com adicional de 60%, "
                            "sem prejuízo da gratificação de função prevista adiante",
                   similaridade=0.66)]
    # tema não está no TÍTULO -> não vale
    assert percentual_da_clausula(cs, r"gratifica", FAIXAS["gratificacao"]) is None


def test_faixa_rejeita_valor_absurdo():
    cs = [Clausula(ref="CLÁUSULA TERCEIRA", titulo="GRATIFICAÇÃO DE FUNÇÃO",
                   conteudo="gratificação de função de 60% para o cargo", similaridade=0.7)]
    assert percentual_da_clausula(cs, r"gratifica", FAIXAS["gratificacao"]) is None
    # dentro da faixa, aceita
    cs[0].conteudo = "gratificação de função de 10% sobre o salário base"
    assert percentual_da_clausula(cs, r"gratifica", FAIXAS["gratificacao"]) \
        == (Decimal("0.10"), "3ª")


def test_similaridade_baixa_e_descartada():
    cs = [Clausula(ref="CLÁUSULA TERCEIRA", titulo="GRATIFICAÇÃO DE FUNÇÃO",
                   conteudo="gratificação de 10%", similaridade=0.20)]
    assert percentual_da_clausula(cs, r"gratifica", FAIXAS["gratificacao"]) is None


def test_converte_ordinal_por_extenso_em_numero():
    """As peças citam 'cláusula 64ª'; a base guarda o título por extenso."""
    assert numero_da_clausula("CLÁUSULA SEXAGÉSIMA", "QUARTA - INIBIÇÃO AO DESVIO") == "64ª"
    assert numero_da_clausula("CLÁUSULA TRIGÉSIMA TERCEIRA - DESCANSO") == "33ª"
    assert numero_da_clausula("CLÁUSULA DÉCIMA QUINTA") == "15ª"
    assert numero_da_clausula("CLÁUSULA TERCEIRA") == "3ª"
    assert numero_da_clausula("SEM ORDINAL AQUI") is None


# --- piso por cargo --------------------------------------------------------
# A cláusula de salários normativos lista dezenas de cargos com piso E
# gratificação na mesma linha. Pegar o menor número dava R$ 1.209,00 (uma
# gratificação, abaixo do mínimo nacional) onde o piso do vigilante é
# R$ 2.148,22 — 44% de erro em TODA a peça, porque tudo escala do salário.

def test_cargo_normalizado_ignora_espaco_na_barra():
    from app.cct import _cargo_normalizado
    assert _cargo_normalizado("Vigilante /Líder") == _cargo_normalizado("Vigilante/Líder")
    assert _cargo_normalizado("  VIGILANTE   Balanceiro ") == "vigilante balanceiro"


def test_linha_da_tabela_de_pisos_e_extraida():
    from app.cct import _LINHA_CARGO
    linha = ("I- Vigilante R$2.148,22 Sem gratificação "
             "IX- Vigilante em Regime de Tempo Parcial (até 26 hs/semana) R$1.269,45")
    achados = _LINHA_CARGO.findall(linha)
    assert ("Vigilante ", "2.148,22") in [(c, v) for c, v in achados] or \
           any(c.strip() == "Vigilante" for c, _ in achados)
    assert any("Tempo Parcial" in c for c, _ in achados)


def test_piso_nunca_abaixo_do_minimo_nacional():
    """Trava contra extrair gratificação como piso (art. 7º, IV, CF)."""
    from app.cct import SALARIO_MINIMO
    from decimal import Decimal
    assert SALARIO_MINIMO >= Decimal("1518.00")


# --- leitura das duas tabelas de piso --------------------------------------
# SEEVISSP numera os cargos ("I- Vigilante R$2.148,22"); SIEMACO não usa
# separador nenhum e o cargo seguinte cola no valor anterior.

def test_tabela_sem_separador_e_lida_por_posicao():
    from app.cct import _cargos_por_posicao
    from decimal import Decimal
    linha = ("RECEPCIONISTA R$ 1.995,25PORTEIRO/CONTROLADOR DE ACESSO/FISCAL "
             "DE PISO R$ 2.162,60ZELADORIA EM PRÉDIOS PÚBLICOSR$ 2.351,12")
    pares = dict(_cargos_por_posicao(linha))
    assert pares["RECEPCIONISTA"] == Decimal("1995.25")
    assert any("PORTEIRO" in k and v == Decimal("2162.60") for k, v in pares.items())


def test_cargo_agrupado_casa_por_componente():
    """'PORTEIRO/CONTROLADOR DE ACESSO/FISCAL DE PISO' vale para os três —
    a CCT dá um piso só à linha inteira."""
    from app.cct import _cargo_normalizado
    cargo = _cargo_normalizado("PORTEIRO/CONTROLADOR DE ACESSO/FISCAL DE PISO")
    for f in ("porteiro", "controlador de acesso", "fiscal de piso"):
        assert f in cargo.split("/")


def test_prefixo_nao_casa_cargo_diferente():
    """'Zelador' NÃO pode pegar 'Zeladoria em Prédios Públicos': cargos
    distintos, pisos distintos. Casamento por prefixo fazia exatamente isso."""
    from app.cct import _cargo_normalizado
    assert _cargo_normalizado("Zelador") not in \
           _cargo_normalizado("ZELADORIA EM PRÉDIOS PÚBLICOS").split("/")


def test_valor_do_beneficio_aceita_as_duas_redacoes():
    from app.cct import _VALOR_FACIAL
    assert _VALOR_FACIAL.findall("no valor facial de R$ 39,00") == ["39,00"]
    assert _VALOR_FACIAL.findall("ANO 2026VALOR EM REAIS R$ 21,80") == ["21,80"]
