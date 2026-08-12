"""Redação dos trechos narrativos — a única parte do sistema onde a IA escreve.

Três decisões de projeto, cada uma com motivo:

1. **Uma chamada só, todos os trechos juntos.** A IA enxerga a peça inteira
   enquanto escreve: o fato narrado nos FATOS reaparece no DANO MORAL com as
   mesmas palavras, a escala citada na jornada bate com a do desvio. Chamada por
   capítulo isolada produz módulos bem escritos com costura aparente.

2. **Structured output**, não texto livre. Elimina cerca markdown e JSON vazando
   no corpo do documento — que já aconteceu em peça protocolada.

3. **Nada de `temperature`.** Foi removido no Opus 5 (retorna 400). O rigor vem
   do schema, do grounding na matriz fática e do `effort`.
"""
from __future__ import annotations

import json
import os
from decimal import Decimal
from typing import Any, Optional

import anthropic

from app.calculo.dinheiro import brl
from app.calculo.verbas import Verba
from app.cct import Clausula, numero_da_clausula
from app.modelos import Caso

_CRITERIO = {
    "por_plantao": ("conte por PLANTÃO/JORNADA efetivamente trabalhada — numa "
                    "escala 12x36 são ~15 por mês. É o critério conservador."),
    "por_dia_do_mes": ("conte por DIA DO MÊS (~30), e não por plantão. É o "
                       "critério mais amplo, usado quando a supressão é diária."),
}

MODELO = os.environ.get("ANTHROPIC_MODEL", "claude-opus-5")
MAX_TOKENS = 16000

IDENTIDADE = """\
Você redige petições iniciais trabalhistas para o escritório FAV Advogados.
Advogado responsável: Dr. Fernando Andrade Vieira — OAB/SP nº 320.825.
Contato institucional: trabalhista@favadvogados.com.br.

REGRAS INVIOLÁVEIS

1. FATOS. Você só pode afirmar o que está na matriz fática fornecida. Não invente
   datas, valores, nomes, locais, doenças, testemunhas ou episódios. Se um dado
   necessário não estiver na matriz, escreva o trecho sem ele — nunca preencha
   com suposição plausível.

2. CCT. Cite cláusula apenas quando ela estiver na lista de cláusulas fornecida,
   com o número exato que ali constar. Não invente número nem percentual. Se o
   trecho exigiria uma cláusula que não foi fornecida, redija sem citá-la.

3. FREQUÊNCIAS E QUANTIDADES. Não afirme quantidades que a matriz não traz
   ("quinze plantões por mês", "duas vezes por semana"). O método de estimativa
   abaixo serve para calcular VALORES, não para virar afirmação de fato no texto.
   Nos trechos narrativos, descreva a habitualidade em termos qualitativos
   ("de forma habitual", "em praticamente todos os plantões").

4. GÊNERO. Concorde todos os adjetivos, particípios e pronomes com o gênero do
   reclamante informado. Isso vale para "o reclamante/a reclamante", "admitido/
   admitida", "dispensado/dispensada", "o próprio/a própria".

5. VALORES. Não escreva valores em reais nos textos: eles são calculados por
   código e inseridos no documento. Quando precisar referir-se a um valor, use a
   descrição da rubrica, não o número.

6. FORMA. Prosa jurídica corrida, em português formal, na terceira pessoa. Sem
   markdown, sem títulos, sem listas, sem aspas de código, sem emojis. Cada campo
   recebe apenas o texto que entra naquele ponto do documento — não repita o
   título do capítulo.

ESTILO DA BANCA
Períodos completos e articulados. Cada afirmação de fato seguida da consequência
jurídica. Evite adjetivação vazia; o peso vem do encadeamento entre o fato
concreto e a norma. Nunca use frases genéricas que caberiam em qualquer peça.
"""

METODO_ESTIMATIVA = """\
QUANTIFICAÇÃO DAS VERBAS POR HORA

As verbas que dependem de contagem de horas não são calculadas por código. A
especialista do escritório as ESTIMA, e a peça as rotula "valor principal
estimado".

VOCÊ NÃO DEVOLVE VALORES EM REAIS. Você devolve QUANTIDADES — quantas horas por
mês cada rubrica representa. O código multiplica pelo valor-hora, pelo adicional
da CCT e pelos meses de contrato. Assim cada rubrica tem fórmula própria e a
conta é auditável.

BASE DE CONTAGEM: {criterio}

Chame de UNIDADE a base definida acima (plantão ou dia do mês). Ela vale APENAS
para horas extras, intervalo do art. 71 e minutos residuais — que são as rubricas
em que a prática da banca varia.

Adicional noturno e domingos/feriados NÃO usam a unidade: são limitados pelos
plantões efetivamente trabalhados. Numa 12x36 são ~15 plantões/mês; as horas
noturnas de cada plantão são só as que caem entre 22h e 5h. Um total de horas
noturnas acima de ~110/mês numa 12x36 é fisicamente impossível — confira antes
de responder.

Como estimar a quantidade de cada uma:
- horas_extras_mes: horas além da 8ª diária/44ª semanal, pela média informada
  na entrevista x unidades no mês.
- intervalo_art71_mes: 1 hora por unidade em que o intervalo foi suprimido.
- minutos_residuais_mes: (minutos que antecedem + os que sucedem) / 60 x unidades.
- adicional_noturno_mes: horas REAIS entre 22h e 5h por plantão x plantões no
  mês. Máximo de 7h por plantão (a faixa noturna tem 7 horas). NÃO aplique aqui
  o adicional nem a redução da hora noturna — o código faz as duas contas.
- domingos_feriados_mes: horas laboradas em folgas/domingos/feriados — use a
  quantidade de folgas informada na entrevista x horas do plantão.
- dez_minutos_mes: 10 minutos por hora trabalhada, em horas (só vigilância).

Antes de responder, confira: as quantidades de intervalo e de minutos residuais
têm que ser coerentes com o número de unidades no mês que você adotou.

Se a entrevista não informar a base de uma rubrica, devolva 0 — não invente
quantidade. O número tem que ser defensável a partir do que o cliente disse.
"""


def _campos_narrativos(caso: Caso) -> dict[str, str]:
    """Campo do template -> o que a IA deve escrever ali. Só o que o caso sustenta."""
    campos = {
        "MOTIVO_SAIDA_RESUMIDO":
            "Sintagma curto que completa 'tendo ___' descrevendo o fim do contrato "
            "(ex.: 'sido dispensado sem justa causa'). Sem ponto final.",
        "JORNADA_HORARIOS":
            "Descrição da jornada efetivamente praticada: horários de entrada e "
            "saída, escala e frequência. Uma a duas frases.",
        "INTERVALO_USUFRUIDO":
            "Como o intervalo intrajornada era usufruído na prática. Uma a duas frases.",
        "PRORROGACAO_JORNADA":
            "Como a jornada se prorrogava para além do contratado, e com que "
            "frequência. Uma a duas frases.",
    }
    if caso.tem_dano_moral:
        campos["DANO_MORAL_FATO_ESPECIFICO"] = (
            "Parágrafo que narra o elemento CONCRETO deste caso que caracteriza o "
            "dano moral — não a tese genérica. Deve ser reconhecível como deste "
            "processo e de nenhum outro.")
    if caso.tem_desvio:
        campos["DESVIO_ATIVIDADES"] = (
            "Enumeração corrida das atividades estranhas à função contratada que o "
            "reclamante exercia, e por que extrapolam a função.")
    if caso.tem_acumulo:
        campos["ACUMULO_ATIVIDADES"] = (
            "Enumeração corrida das funções acumuladas simultaneamente à contratada.")
    if caso.folgas_trabalhadas_mes:
        campos["FT_100"] = (
            "Como as folgas trabalhadas eram acionadas e pagas por fora da folha.")
    return campos


def _rubricas_estimadas(caso: Caso) -> dict[str, str]:
    """Rubricas por hora que o caso sustenta — schema dinâmico.

    A IA devolve HORAS POR MÊS, não reais. Pedir o valor final fazia com que ela
    repetisse o mesmo número para rubricas de bases diferentes (no caso MARCOS,
    R$ 2.873,68 idênticos para horas extras, intervalo e minutos residuais)."""
    r = {"horas_extras_mes": "Horas extras além da 8ª diária/44ª semanal, por mês"}
    if caso.intervalo_suprimido:
        r["intervalo_art71_mes"] = "Horas de intervalo suprimido por mês (1h por jornada)"
    if caso.periodo_antecedente or caso.periodo_sucedente:
        r["minutos_residuais_mes"] = "Horas/mês dos minutos que antecedem e sucedem"
    if caso.tem_adicional_noturno:
        r["adicional_noturno_mes"] = "Horas noturnas (22h-5h) por mês, com a redução"
    if caso.folgas_trabalhadas_mes or caso.trabalhou_fins_de_semana:
        r["domingos_feriados_mes"] = "Horas em folgas/domingos/feriados por mês"
    if caso.categoria == "vigilancia":
        r["dez_minutos_mes"] = "Horas/mês do descanso de 10 min (cláusula 33ª)"
    return r


def _schema(caso: Caso) -> dict[str, Any]:
    narrativos = _campos_narrativos(caso)
    estimadas = _rubricas_estimadas(caso)
    props: dict[str, Any] = {
        k: {"type": "string", "description": v} for k, v in narrativos.items()
    }
    props["quantidades"] = {
        "type": "object",
        "description": "HORAS POR MÊS de cada rubrica. Nunca valores em reais.",
        "properties": {k: {"type": "number", "description": v}
                       for k, v in estimadas.items()},
        "required": list(estimadas),
        "additionalProperties": False,
    }
    props["justificativa_quantidades"] = {
        "type": "string",
        "description": "Em uma frase por rubrica, de onde saiu cada quantidade "
                       "(qual dado da entrevista). Vai para o trace, não para a peça.",
    }
    return {"type": "object", "properties": props,
            "required": list(narrativos) + ["quantidades", "justificativa_quantidades"],
            "additionalProperties": False}


def _matriz_fatica(caso: Caso, verbas: list[Verba], clausulas: list[Clausula]) -> str:
    partes = [
        "MATRIZ FÁTICA (fonte única — não extrapole)",
        f"Reclamante: {caso.nome} — gênero {'feminino' if caso.genero == 'F' else 'masculino'}",
        f"Função: {caso.funcao}",
        f"Admissão: {caso.admissao:%d/%m/%Y} · Rescisão: {caso.rescisao:%d/%m/%Y} "
        f"({caso.meses_contrato} meses)",
        f"Modalidade do fim do contrato: {caso.modalidade}",
        f"Último salário: {brl(caso.salario)}",
        f"Escala: {caso.escala or 'não informada'}",
        f"Categoria/CCT: {caso.categoria or 'não identificada'}",
    ]
    partes.append("")
    partes.append("JORNADA (base das estimativas — use ESTES números):")
    for rotulo, valor in (
        ("horário", caso.jornada_horario), ("escala", caso.escala),
        ("média de horas extras", caso.media_horas_extras),
        ("minutos que antecedem", caso.periodo_antecedente),
        ("minutos que sucedem", caso.periodo_sucedente),
        ("intervalo intrajornada", caso.intervalo_gozado),
    ):
        partes.append(f"  - {rotulo}: {valor or 'não informado'}")
    partes.append(f"  - intervalo suprimido: {'sim' if caso.intervalo_suprimido else 'não'}")
    partes.append(f"  - trabalhou fins de semana e feriados: "
                  f"{'sim' if caso.trabalhou_fins_de_semana else 'não'}")
    partes.append(f"  - folgas trabalhadas por mês: {caso.folgas_trabalhadas_mes or 'não informado'}")
    partes.append(f"  - espelho de ponto: "
                  f"{'fornecido' if caso.tem_espelho_ponto else 'NÃO fornecido pela empresa'}")

    beneficios = [n for n, on in (("vale-refeição", caso.vale_refeicao),
                                  ("vale-alimentação", caso.vale_alimentacao),
                                  ("vale-transporte", caso.vale_transporte)) if on]
    partes.append("Benefícios recebidos: " + (", ".join(beneficios) or "nenhum"))
    partes.append("Periculosidade: " + ("sim" if caso.tem_periculosidade else "não"))
    if caso.desconto_indevido:
        partes.append(f"Desconto indevido: {caso.desconto_indevido}")

    if caso.reclamadas:
        partes.append("Reclamadas: " + "; ".join(
            f"{r.razao_social}{' (tomadora)' if r.tomadora else ''}" for r in caso.reclamadas))
    partes.append("Teses ativas: " + ", ".join(t for t, on in (
        ("dano moral", caso.tem_dano_moral), ("desvio de função", caso.tem_desvio),
        ("acúmulo de função", caso.tem_acumulo),
        ("gratificação de função", caso.tem_gratificacao_funcao),
        ("adicional noturno", caso.tem_adicional_noturno),
        ("folgas trabalhadas", bool(caso.folgas_trabalhadas_mes))) if on) or "nenhuma")

    if caso.funcoes_acumuladas:
        partes.append(f"\nFUNÇÕES ACUMULADAS/DESVIADAS (literal da entrevista):\n"
                      f"  {caso.funcoes_acumuladas}")
    if caso.fatos_narrados:
        partes.append("\nFATOS NARRADOS PELO RECLAMANTE (fonte primária — a "
                      "narrativa da peça sai daqui, não de suposição):\n"
                      + "\n".join(f"  {l}" for l in caso.fatos_narrados.splitlines() if l.strip()))

    partes.append("\nVERBAS JÁ CALCULADAS POR CÓDIGO (não as recalcule nem cite valores):")
    partes += [f"  - {v.rubrica}: {v.fundamento or '—'}" for v in verbas]

    if clausulas:
        partes.append("\nCLÁUSULAS DA CCT DISPONÍVEIS (só estas podem ser citadas, e "
                      "SEMPRE pelo número curto entre colchetes — 'cláusula 64ª' — "
                      "nunca pelo título por extenso):")
        for c in clausulas[:12]:
            numero = numero_da_clausula(c.ref, c.titulo) or "sem número"
            assunto = (c.titulo or "").split(" - ", 1)[-1]
            partes.append(f"  - [cláusula {numero}] {assunto}".rstrip())
            partes.append(f"      {c.conteudo[:300]}")
    else:
        partes.append("\nNENHUMA CLÁUSULA DE CCT DISPONÍVEL — não cite cláusula alguma.")
    return "\n".join(partes)


def redigir(caso: Caso, verbas: list[Verba], clausulas: Optional[list[Clausula]] = None,
            *, effort: str = "high") -> dict[str, Any]:
    """Uma chamada, todos os trechos. Devolve {campo: texto} + valores_estimados."""
    cliente = anthropic.Anthropic()
    resposta = cliente.messages.create(
        model=MODELO,
        max_tokens=MAX_TOKENS,
        # Prefixo estável em bloco próprio e cacheado: idêntico entre casos,
        # então da segunda peça em diante ele é lido do cache (~0,1x do custo).
        system=[
            {"type": "text", "text": IDENTIDADE, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": METODO_ESTIMATIVA.format(criterio=_CRITERIO[caso.criterio_horas])},
        ],
        output_config={
            "format": {"type": "json_schema", "schema": _schema(caso)},
            "effort": effort,
        },
        messages=[{"role": "user",
                   "content": _matriz_fatica(caso, verbas, clausulas or [])}],
    )
    texto = next(b.text for b in resposta.content if b.type == "text")
    dados = json.loads(texto)
    dados["_uso"] = {
        "entrada": resposta.usage.input_tokens,
        "saida": resposta.usage.output_tokens,
        "cache_escrito": getattr(resposta.usage, "cache_creation_input_tokens", 0),
        "cache_lido": getattr(resposta.usage, "cache_read_input_tokens", 0),
    }
    return dados
