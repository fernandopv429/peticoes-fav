"""Caso + verbas -> {TAG: valor} e {flag: bool} do template.

Mapa explícito de propósito: é o contrato entre o cálculo e o documento. Tag que
não aparece aqui fica sem valor e o preenchimento a marca como [A PREENCHER],
visível — nunca vira parêntese vazio nem `{{}}` cru.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from app.calculo.dinheiro import brl, brl_com_extenso
from app.calculo.verbas import Verba
from app.competencia import resolver as resolver_competencia
from app.modelos import Caso

# Código interno da Verba -> tag do template. Os nomes divergem por história:
# o template veio da peça do Jonathan, o cálculo foi escrito agora.
MAPA_VERBA_TAG = {
    "VALOR_13": "VALOR_13",
    "VALOR_AVISO_PREVIO": "VALOR_AVISO_PREVIO",
    "VALOR_FERIAS": "VALOR_FERIAS",
    "VALOR_FGTS": "VALOR_FGTS",
    "VALOR_MULTA_40": "VALOR_MULTA_40",
    "VALOR_DANO_MORAL": "VALOR_DANO_MORAL_10X",   # nome do template
    "VALOR_DESVIO": "VALOR_DESVIO",
    "VALOR_ACUMULO": "VALOR_ACUMULO",
    "VALOR_GRATIFICACAO": "VALOR_GRATIFICACAO",
    "VALOR_SALARIOS_ABERTO": "SALARIOS_ABERTO",
    # A verba é o TOTAL a integrar; o template usa {{VALOR_POR_FORA}} para o
    # valor mensal narrado ("gira em torno de R$ 180,00") e {{VALOR_INTEGRACAO}}
    # para esse total. Mapear a verba em VALOR_POR_FORA trocava os dois.
    "VALOR_POR_FORA": "VALOR_INTEGRACAO",
    "VALOR_SALDO_SALARIO": "VALOR_SALDO_SALARIO",
    "VALOR_MULTA_477": "VALOR_MULTA_477",
    "VALOR_ART_467": "VALOR_ART_467",
    "VALOR_AUX_ALIM_TOTAL": "VALOR_AUX_ALIM_TOTAL",
    "VALOR_VT_TOTAL": "VALOR_VT_TOTAL",
    # A multa convencional fica sem valor de propósito: a cláusula 71ª manda
    # apurar 3% por dia E por cláusula descumprida, e nem os dias nem quais
    # cláusulas se sabe na propositura. Vai como "a apurar em liquidação".
}


_MESES = {1: "janeiro", 2: "fevereiro", 3: "março", 4: "abril", 5: "maio",
          6: "junho", 7: "julho", 8: "agosto", 9: "setembro", 10: "outubro",
          11: "novembro", 12: "dezembro"}


def _data(d: Optional[date]) -> Optional[str]:
    return d.strftime("%d/%m/%Y") if d else None


def _periodo_aquisitivo(caso: Caso) -> str:
    """'2025/2026' — o aquisitivo em curso na rescisão.

    Corre de aniversário a aniversário da ADMISSÃO, não do ano-calendário."""
    aniversario = (caso.admissao.month, caso.admissao.day)
    inicio = caso.rescisao.year - (0 if (caso.rescisao.month, caso.rescisao.day)
                                   >= aniversario else 1)
    inicio = max(inicio, caso.admissao.year)   # contrato com menos de um ano
    return f"{inicio}/{inicio + 1}"


def montar_flags(caso: Caso) -> dict[str, bool]:
    """Quais capítulos entram. Decidido por código — a IA decidindo estrutura já
    fez sair peça sem Súmula 331 tendo tomadora."""
    tem_tomadora = any(r.tomadora for r in caso.reclamadas)
    return {
        "sem_justa_causa": caso.modalidade == "sem_justa_causa",
        "rescisao_indireta": caso.modalidade == "rescisao_indireta",
        "coacao_demissao": caso.modalidade == "coacao_demissao",
        "reversao_justa_causa": caso.modalidade == "reversao_justa_causa",
        "tem_capitulo_rescisao": caso.modalidade != "sem_justa_causa",
        "tem_tomadora": tem_tomadora,
        "escala_12x36": caso.escala == "12x36",
        "escala_4x2": caso.escala == "4x2",
        "desvio_funcao": caso.tem_desvio,
        "acumulo_funcao": caso.tem_acumulo,
        "gratificacao_funcao": caso.tem_gratificacao_funcao,
        "adicional_noturno": caso.tem_adicional_noturno,
        "folgas_trabalhadas": bool(caso.folgas_trabalhadas_mes),
        # o capítulo só entra se houver valor a integrar — senão a peça abria
        # um pedido de integração com o valor em branco
        "integracao_por_fora": bool(caso.val_folgas_mensal),
        "salarios_em_aberto": caso.salarios_em_aberto_meses > 0,
        "periculosidade": caso.tem_periculosidade,
        "dez_minutos_cct": caso.categoria == "vigilancia",
        "doenca_ocupacional": caso.tem_doenca_ocupacional,
        "estabilidade_doenca": caso.tem_doenca_ocupacional,
        # Benefício sem valor diário não vira pedido: `beneficios_das_folgas`
        # não gera a verba, então o capítulo sairia com o valor em branco.
        "auxilio_alimentacao": (caso.vale_alimentacao
                                and bool(caso.folgas_trabalhadas_mes)
                                and caso.valor_alimentacao_dia is not None),
        "vale_transporte": (caso.vale_transporte
                            and bool(caso.folgas_trabalhadas_mes)
                            and caso.valor_transporte_dia is not None),
        # sem dado no formulário
        "pensao_vitalicia": False,
        "assiduidade": False,
    }


def montar_campos(caso: Caso, verbas: list[Verba], valor_causa: Decimal,
                  rito: str, *, data_peca: Optional[date] = None) -> dict[str, str]:
    campos: dict[str, str] = {}

    # --- valores calculados
    for v in verbas:
        tag = MAPA_VERBA_TAG.get(v.codigo)
        if tag:
            campos[tag] = brl(v.total)

    campos["VALOR_CAUSA_TOTAL"] = brl_com_extenso(valor_causa)
    campos["SALARIO"] = brl_com_extenso(caso.salario)
    campos["RITO"] = rito

    # --- reclamante
    campos.update({
        "RECL_NOME": caso.nome.upper(),
        "RECL_FUNCAO": caso.funcao,
        "RECL_NACIONALIDADE": caso.nacionalidade,
        "RECL_ESTADO_CIVIL": caso.estado_civil,
        "RECL_RG": caso.rg, "RECL_CPF": caso.cpf, "RECL_PIS": caso.pis,
        "RECL_CTPS": caso.ctps, "RECL_SERIE": caso.ctps_serie,
        "RECL_NASCIMENTO": _data(caso.nascimento),
        "RECL_FILIACAO": caso.filiacao,
        "RECL_ENDERECO": " - ".join(x for x in (caso.endereco, caso.cep) if x) or None,
        "RECL_EMAIL": caso.email,
        "JORNADA_HORARIOS": caso.jornada_horario,
        "INTERVALO_USUFRUIDO": caso.intervalo_gozado,
        "ESCALA": caso.escala,
        "FOLGAS_LABORADAS_MES": (str(caso.folgas_trabalhadas_mes)
                                 if caso.folgas_trabalhadas_mes else None),
        "ACUMULO_ATIVIDADES": caso.funcoes_acumuladas,
        "DESVIO_ATIVIDADES": caso.funcoes_acumuladas,
        "DATA_ADMISSAO": _data(caso.admissao),
        "DATA_RESCISAO": _data(caso.rescisao),
        "DATA_PECA": _data(data_peca or date.today()),
        "ESCALA": caso.escala,
    })

    # --- reclamadas
    for i, r in enumerate(caso.reclamadas[:2], start=1):
        campos[f"RECLAMADA{i}_RAZAO"] = r.razao_social
        campos[f"RECLAMADA{i}_CNPJ"] = r.cnpj
        campos[f"RECLAMADA{i}_ENDERECO"] = r.endereco

    # --- competência (art. 651)
    if caso.municipio_prestacao and caso.uf_prestacao:
        comp = resolver_competencia(caso.municipio_prestacao, caso.uf_prestacao)
        if comp:
            campos["VARA_CIDADE_REGIAO"] = comp.vara_cidade_regiao
    if caso.endereco_prestacao:
        campos["LOCAL_PRESTACAO_ENDERECO"] = caso.endereco_prestacao

    # --- verbas rescisórias discriminadas
    # A peça da especialista escreve "saldo de salário de 7 (sete) dias de
    # dezembro/2025" e "férias 2025/2026 – 8/12". Antes esses números vinham
    # chumbados do modelo (11/12 do caso Jonathan) e mentiam em todo caso novo.
    if caso.rescisao:
        campos["DIAS_SALDO_SALARIO"] = str(min(caso.rescisao.day, 30))
        campos["MES_RESCISAO"] = f"{_MESES[caso.rescisao.month]}/{caso.rescisao.year}"
        campos["AVOS_13"] = f"{caso.avos_13}/12"
        campos["AVOS_FERIAS"] = f"{caso.avos_ferias}/12"
        campos["ANO_RESCISAO"] = str(caso.rescisao.year)
        campos["PERIODO_AQUISITIVO"] = _periodo_aquisitivo(caso)

    # --- valores por fora: o mensal narrado, não o total (esse é a integração)
    if caso.val_folgas_mensal:
        campos["VALOR_POR_FORA"] = brl(caso.val_folgas_mensal)
    if caso.valor_alimentacao_dia:
        campos["VALOR_AUX_ALIMENTACAO"] = brl(caso.valor_alimentacao_dia)

    # --- CCT
    if caso.rescisao:
        campos["CCT_ANO"] = str(caso.rescisao.year)
    if caso.clausula_multa:
        campos["CCT_CLAUSULA_MULTA"] = caso.clausula_multa

    return {k: v for k, v in campos.items() if v is not None}
