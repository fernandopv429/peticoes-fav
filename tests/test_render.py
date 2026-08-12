"""Gate de validação — cada teste corresponde a um erro que já saiu em peça real."""
from decimal import Decimal

from app.calculo.verbas import com_reflexos, sem_reflexo
from app.render.preencher import preencher, resolver_flags, validar


def validar_(html, verbas, valor, **kw):
    """Atalho dos testes: categoria já resolvida, para isolar a checagem alvo.
    A ausência de categoria tem teste próprio em test_categoria.py."""
    kw.setdefault("categoria", "vigilancia")
    kw.setdefault("competencia", type("C", (), {"revisar": False, "motivo": ""})())
    return validar(html, verbas, valor, **kw)


def test_flag_falsa_remove_o_capitulo():
    html = "<p>antes</p>{{#periculosidade}}<p>PERICULOSIDADE</p>{{/periculosidade}}<p>depois</p>"
    assert "PERICULOSIDADE" not in resolver_flags(html, {"periculosidade": False})
    assert "PERICULOSIDADE" in resolver_flags(html, {"periculosidade": True})


def test_nunca_sobra_chave_dupla_no_documento():
    """107 `{{}}` crus no corpo já foram para uma minuta gerada."""
    html = "<p>{{RECL_NOME}} e {{TAG_INEXISTENTE}} e {{#flag_orfa}}x</p>"
    saida = preencher(html, {"RECL_NOME": "MARCOS"}, {})
    assert "{{" not in saida and "}}" not in saida
    assert "MARCOS" in saida
    assert "[A PREENCHER: TAG_INEXISTENTE]" in saida


def test_campo_sem_valor_vira_marcador_visivel_e_nao_bloqueia():
    saida = preencher("<p>{{SALARIO}}</p>", {}, {})
    v = validar_(saida, [], Decimal("0"))
    assert "[A PREENCHER: SALARIO]" in saida
    assert any(p.codigo == "CAMPO_SEM_VALOR" and not p.bloqueia for p in v.problemas)


def test_json_da_ia_vazando_bloqueia():
    """Peça real saiu com { "BLOCO_DANO_MORAL": "..." } literal no corpo."""
    v = validar_('<p>{ "BLOCO_DANO_MORAL": "texto" }</p>', [], Decimal("0"))
    assert not v.aprovado
    assert any(p.codigo == "JSON_DA_IA_NO_CORPO" for p in v.problemas)


def test_valor_da_causa_tem_que_bater_com_a_soma():
    """O rol de pedidos mostrava um valor e o fecho outro."""
    verbas = [sem_reflexo("A", "a", Decimal("1000.00"))]
    assert validar_("<p>ok</p>", verbas, Decimal("1000.00")).aprovado
    assert not validar_("<p>ok</p>", verbas, Decimal("9999.00")).aprovado


def test_teto_de_400_mil_no_gate():
    verbas = [sem_reflexo("A", "a", Decimal("500000.00"))]
    v = validar_("<p>ok</p>", verbas, Decimal("400000.00"))
    assert v.aprovado  # limitado ao teto = correto


def test_paragrafo_vazio_da_flag_removida_some():
    html = "{{#x}}<p>a</p>{{/x}}<p>  </p><p>fim</p>"
    saida = preencher(html, {}, {"x": False})
    assert saida == "<p>fim</p>"


# --- adaptador da Entrevista (app Base44 6a734d6c...) ----------------------

from app.entrevista import _faixa_menor, _horario_e_noturno, _media_faixa, _municipio_uf


def test_jornada_noturna_por_sobreposicao_nao_pelos_extremos():
    """'das 19h às 07h' começa e termina fora da faixa 22h–5h, mas a atravessa
    inteira. Testar só os extremos dava False e apagava o adicional noturno —
    R$ 4.103,15 na peça real do caso MARCOS."""
    assert _horario_e_noturno("das 19h às 07h") is True
    assert _horario_e_noturno("das 18h às 06h") is True
    assert _horario_e_noturno("das 23h às 05h") is True
    assert _horario_e_noturno("das 07h às 19h") is False
    assert _horario_e_noturno("das 06h às 14h") is False
    assert _horario_e_noturno(None) is False


def test_faixas_do_formulario():
    """Valor: extremo conservador. Quantidade: média da faixa."""
    assert _faixa_menor("R$ 180 a R$ 200") == Decimal("180")
    assert _media_faixa("5 a 6 por mês") == Decimal("5.5")
    assert _faixa_menor(None) is None


def test_extrai_municipio_e_uf():
    assert _municipio_uf("Itapecerica da Serra/SP, CEP 06877-115") == ("Itapecerica da Serra", "SP")
    assert _municipio_uf("São Paulo/SP") == ("São Paulo", "SP")
    assert _municipio_uf(None) == (None, None)
