"""Adaptador: entidade `Entrevista` do app Base44 -> `Caso`.

O app `6a734d6c72c1f853994b8733` digitalizou o formulário assinado do escritório.
Os nomes dos campos lá seguem a convenção canônica das tags do template
(RECL_NOME, RECL_ESTADOCIVIL, ...), então o mapeamento é quase 1:1.

Regra: nada é inventado aqui. Campo ausente vira None e o gate reclama depois.
"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Any, Optional

from app.modelos import Caso, Modalidade, Reclamada

# tipo_dispensa da Entrevista -> modalidade do Caso
_MODALIDADE: dict[str, Modalidade] = {
    "sem_justa_causa": "sem_justa_causa",
    "rescisao_indireta": "rescisao_indireta",
    "nulidade_pedido_demissao": "coacao_demissao",
    "coacao_demissao": "coacao_demissao",
    "reversao_justa_causa": "reversao_justa_causa",
    "acordo": "acordo",
}


def _data(v: Any) -> Optional[date]:
    if not v:
        return None
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v)[:10])


def _faixa_menor(txt: Any) -> Optional[Decimal]:
    """'R$ 180 a R$ 200' -> 180 · '5 a 6 por mês' -> 5

    A especialista escolhe o extremo CONSERVADOR das faixas do formulário —
    pedir o maior valor sem prova enfraquece a peça."""
    if txt is None:
        return None
    nums = re.findall(r"\d+(?:[.,]\d+)?", str(txt).replace(".", ""))
    if not nums:
        return None
    return min(Decimal(n.replace(",", ".")) for n in nums)


def _media_faixa(txt: Any) -> Optional[Decimal]:
    """'5 a 6 por mês' -> 5.5 — para quantidade, a média da faixa."""
    if txt is None:
        return None
    nums = [Decimal(n.replace(",", ".")) for n in
            re.findall(r"\d+(?:[.,]\d+)?", str(txt).replace(".", ""))]
    if not nums:
        return None
    return (min(nums) + max(nums)) / 2 if len(nums) > 1 else nums[0]


def _horario_e_noturno(horario: Optional[str]) -> bool:
    """A jornada ATRAVESSA o horário noturno das 22h às 5h (art. 73 CLT)?

    Testar só os extremos é errado: "das 19h às 07h" tem início e fim fora da
    faixa e mesmo assim cobre as 22h–5h inteiras. Precisa ser sobreposição de
    intervalos, com o turno que vira o dia tratado como duas faixas."""
    if not horario:
        return False
    horas = [int(h) for h in re.findall(r"(\d{1,2})\s*(?:h|:)", horario.lower())]
    if len(horas) < 2:
        return False
    inicio, fim = horas[0] % 24, horas[1] % 24
    turno = ([(inicio, 24), (0, fim)] if fim <= inicio else [(inicio, fim)])
    noite = [(22, 24), (0, 5)]
    return any(a < d and c < b for a, b in turno for c, d in noite)


def _valor_brl(txt: Any) -> Optional[Decimal]:
    """'R$ 2.148,22' -> Decimal('2148.22')"""
    if txt is None:
        return None
    m = re.search(r"([\d.]*\d),(\d\d)", str(txt))
    if m:
        return Decimal(m.group(1).replace(".", "") + "." + m.group(2))
    m = re.search(r"(\d+)", str(txt))
    return Decimal(m.group(1)) if m else None


def _e_assiduidade(txt: Optional[str]) -> bool:
    return bool(txt) and "assidu" in txt.lower()


def _valores_prometido_pago(txt: Optional[str]) -> tuple[Optional[Decimal], Optional[Decimal]]:
    """'prometida R$ 300,00/mês, paga apenas R$ 100,00/mês' -> (300, 100)"""
    if not txt:
        return None, None
    vals = [Decimal(v.replace(".", "").replace(",", "."))
            for v in re.findall(r"R\$\s*([\d.]+,\d\d)", txt)]
    if len(vals) >= 2:
        return max(vals), min(vals)
    return (vals[0], None) if vals else (None, None)


def _reclamadas(e: dict[str, Any]) -> list[Reclamada]:
    saida: list[Reclamada] = []
    for i in (1, 2, 3):
        nome = (e.get(f"RECL{i}_NOME") or "").strip()
        if not nome:
            continue
        endereco = " - ".join(x for x in (e.get(f"RECL{i}_LOGRADOURO"),
                                          e.get(f"RECL{i}_ENDCOMPL")) if x)
        saida.append(Reclamada(razao_social=nome, cnpj=e.get(f"RECL{i}_CNPJ") or None,
                               endereco=endereco or None,
                               # a 1ª é a empregadora; as demais, tomadoras
                               tomadora=i > 1))
    return saida


def _municipio_uf(texto: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """'Itapecerica da Serra/SP, CEP 06877-115' -> ('Itapecerica da Serra', 'SP')"""
    if not texto:
        return None, None
    m = re.search(r"([A-Za-zÀ-ÿ'\.\s]+?)\s*/\s*([A-Z]{2})\b", texto)
    return (m.group(1).strip(), m.group(2)) if m else (None, None)


def de_entrevista(e: dict[str, Any], *, salario: Optional[Decimal] = None) -> Caso:
    """`Entrevista` -> `Caso`.

    `salario` vem por fora: o formulário assinado não o coleta, e a especialista
    o deduz do piso da CCT. Sem ele o gate barra — melhor que chutar, porque
    todo o resto da peça escala a partir do salário.
    """
    reclamadas = _reclamadas(e)
    # Competência = local da PRESTAÇÃO, que é o endereço da tomadora quando há
    # uma; senão, o da empregadora.
    tomadora = next((r for r in reclamadas if r.tomadora), None)
    base_local = (e.get("RECL2_ENDCOMPL") if tomadora else e.get("RECL1_ENDCOMPL"))
    municipio, uf = _municipio_uf(base_local)

    return Caso(
        nome=e["RECL_NOME"],
        funcao=e.get("FUNCAO") or "",
        nacionalidade=e.get("RECL_NACIONALIDADE"),
        estado_civil=e.get("RECL_ESTADOCIVIL"),
        rg=e.get("RECL_RG"), cpf=e.get("RECL_CPF"), pis=e.get("RECL_PIS"),
        ctps=e.get("RECL_CTPS"), ctps_serie=e.get("RECL_SERIE"),
        nascimento=_data(e.get("RECL_NASC")),
        filiacao=e.get("RECL_FILIACAO"), endereco=e.get("RECL_ENDERECO"),
        cep=e.get("RECL_CEP"),
        # a entidade guarda o e-mail do cliente ora em `email`, ora em RECL_EMAIL
        email=e.get("RECL_EMAIL") or e.get("email"),

        admissao=_data(e.get("DATA_ADMISSAO")),
        rescisao=_data(e.get("DATA_RESCISAO")),
        modalidade=_MODALIDADE.get(e.get("tipo_dispensa", ""), "sem_justa_causa"),
        # o formulário passou a ter campo SALARIO próprio; o parâmetro só
        # sobrepõe quando informado (ex.: piso deduzido da CCT)
        salario=(salario if salario is not None
                 else (_valor_brl(e.get("SALARIO")) or Decimal("0"))),
        reclamadas=reclamadas,
        municipio_prestacao=municipio, uf_prestacao=uf,
        endereco_prestacao=" - ".join(
            x for x in (e.get("RECL2_LOGRADOURO"), e.get("RECL2_ENDCOMPL")) if x) or None,

        escala=e.get("escala"),
        jornada_horario=e.get("JORNADA_HORARIO"),
        media_horas_extras=e.get("media_horas_extras"),
        periodo_antecedente=e.get("periodo_antecedente"),
        periodo_sucedente=e.get("periodo_sucedente"),
        trabalhou_fins_de_semana=bool(e.get("finais_semana")),
        # o formulário ganhou `tem_adic_noturno` explícito; a inferência pelo
        # horário vira só o fallback de quem preencheu antes do campo existir
        tem_adicional_noturno=(bool(e["tem_adic_noturno"]) if "tem_adic_noturno" in e
                               else _horario_e_noturno(e.get("JORNADA_HORARIO"))),
        intervalo_suprimido=bool(e.get("intervalo_suprimido")),
        intervalo_gozado=e.get("INTERVALO_GOZADO"),

        vale_refeicao=bool(e.get("vale_refeicao")),
        vale_alimentacao=bool(e.get("vale_alimentacao")),
        vale_transporte=bool(e.get("vale_transporte")),

        tem_periculosidade=bool(e.get("tem_periculosidade")),
        tem_insalubridade=bool(e.get("tem_insalubridade")),
        tem_doenca_ocupacional=bool(e.get("tem_doenca")),

        tem_espelho_ponto=bool(e.get("espelho_ponto")),
        tem_holerites=bool(e.get("holerites")),
        desconto_indevido=e.get("desconto_qual") if e.get("desconto_indevido") else None,

        fatos_narrados=e.get("fatos_narrados"),
        funcoes_acumuladas=e.get("funcoes_acumuladas"),

        # O formulário tem um só campo "Acúmulo/Desvio". A distinção é jurídica:
        # vigilante desviado para outra atividade = DESVIO (50%); porteiro que
        # soma funções = ACÚMULO (20%). Ver MATRIZ_GERAL_3_MODELOS.md §2.
        tem_desvio=bool(e.get("acumulo_funcao")) and "vigilante" in (e.get("FUNCAO") or "").lower(),
        tem_acumulo=bool(e.get("acumulo_funcao")) and "vigilante" not in (e.get("FUNCAO") or "").lower(),
        # "gratificacao" no formulário é genérico: pode ser gratificação de FUNÇÃO
        # (10% do condutor de vigilância) ou bonificação de ASSIDUIDADE — que é
        # outra verba, com outro cálculo (diferença entre prometido e pago).
        # O texto de `gratificacao_qual` desambigua.
        tem_gratificacao_funcao=(bool(e.get("gratificacao"))
                                 and not _e_assiduidade(e.get("gratificacao_qual"))),
        tem_assiduidade=(bool(e.get("assiduidade"))
                         or (bool(e.get("gratificacao"))
                             and _e_assiduidade(e.get("gratificacao_qual")))),
        assiduidade_prometida=(_valor_brl(e.get("assiduidade_prometido"))
                               or _valores_prometido_pago(e.get("gratificacao_qual"))[0]),
        assiduidade_paga=(_valor_brl(e.get("assiduidade_pago"))
                          or _valores_prometido_pago(e.get("gratificacao_qual"))[1]),
        tem_dano_moral=True,   # tese padrão da banca; a IA ancora no fato concreto

        folgas_trabalhadas_mes=_media_faixa(e.get("FT_QTD_MEDIA")),
        val_folgas_mensal=_valor_brl(e.get("VAL_FT")),
        ft_forma_pagamento=e.get("ft_pagamento"),
        # valores diários dos benefícios, quando a entrevista os traz
        valor_alimentacao_dia=_valor_brl(e.get("VALOR_AUX_ALIMENTACAO")),
        valor_transporte_dia=_valor_brl(e.get("VAL_CONDUCAO")),
    )
