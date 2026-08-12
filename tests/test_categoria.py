"""SIEMACO × SINDEEPRES — a distinção que a função NÃO faz.

A matriz do escritório (MATRIZ_GERAL_3_MODELOS.md §2) mostra que Controlador e
Porteiro aparecem nos dois sindicatos. Decidir por função é chute, e o chute
silencioso gerava peça com o percentual e a cláusula do sindicato errado.
"""
from datetime import date
from decimal import Decimal

from app.cct import categoria_por_cnae, resolver_categoria
from app.modelos import Caso, Reclamada
from app.render.preencher import validar


def caso(**kw) -> Caso:
    base = dict(nome="x", funcao="Porteiro", admissao=date(2024, 1, 1),
                rescisao=date(2024, 9, 7), modalidade="sem_justa_causa",
                salario=Decimal("1590.00"))
    return Caso(**{**base, **kw})


def test_cnae_de_limpeza_leva_a_siemaco():
    c = caso(reclamadas=[Reclamada(razao_social="LIMPA TUDO", cnae="8121-4/00")])
    r = resolver_categoria(c)
    assert r.categoria == "asseio_conservacao" and "CNAE" in r.origem


def test_cnae_de_mao_de_obra_leva_a_sindeepres():
    c = caso(reclamadas=[Reclamada(razao_social="TERCEIRIZA SA", cnae="7820-5/00")])
    assert resolver_categoria(c).categoria == "terceirizados"


def test_sindicato_do_holerite_prevalece_sobre_o_cnae():
    """O CNAE principal nem sempre reflete a atividade do contrato."""
    c = caso(sindicato="SIEMACO",
             reclamadas=[Reclamada(razao_social="TERCEIRIZA SA", cnae="7820-5/00")])
    r = resolver_categoria(c)
    assert r.categoria == "asseio_conservacao" and r.origem == "sindicato informado"


def test_cnae_da_tomadora_e_ignorado():
    """Quem define o sindicato é a EMPREGADORA, não o tomador dos serviços."""
    c = caso(reclamadas=[Reclamada(razao_social="TERCEIRIZA", cnae="7820-5/00"),
                         Reclamada(razao_social="HOSPITAL", cnae="8610-1/01",
                                   tomadora=True)])
    assert resolver_categoria(c).categoria == "terceirizados"


def test_porteiro_sem_cnae_nem_sindicato_fica_indefinido():
    r = resolver_categoria(caso())
    assert r.categoria is None and r.ambigua is True


def test_gate_bloqueia_categoria_indefinida():
    """Melhor não gerar do que gerar citando a CCT do sindicato errado."""
    v = validar("<p>ok</p>", [], Decimal("0"), categoria=None, categoria_ambigua=True,
                competencia=type("C", (), {"revisar": False})())
    assert not v.aprovado
    p = next(x for x in v.problemas if x.codigo == "CATEGORIA_INDEFINIDA")
    assert "sindicato" in p.detalhe and "cnae" in p.detalhe


def test_salario_abaixo_do_piso_vira_aviso():
    """Diferenças salariais por descumprimento do piso são pedido autônomo."""
    v = validar("<p>ok</p>", [], Decimal("0"), categoria="terceirizados",
                competencia=type("C", (), {"revisar": False})(),
                salario=Decimal("1400.00"), pisos=[Decimal("1590.00")])
    p = next(x for x in v.problemas if x.codigo == "SALARIO_ABAIXO_DO_PISO")
    assert not p.bloqueia and "diferenças salariais" in p.detalhe


def test_vigilante_continua_decidido_pela_funcao():
    c = caso(funcao="Vigilante Patrimonial")
    r = resolver_categoria(c)
    assert r.categoria == "vigilancia" and r.origem == "função"
