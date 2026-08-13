"""O pipeline inteiro, em um lugar só e testável de ponta a ponta.

Ordem errada gera peça errada tão bem quanto fórmula errada — por isso a
sequência mora aqui, com teste, e não espalhada em nós de workflow.
"""
from __future__ import annotations

import pathlib
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Optional

from app import cct as cct_mod
from app.competencia import resolver as resolver_competencia
from app.consultas import enriquecer_reclamadas
from app.calculo.horas import beneficios_das_folgas, de_quantidades
from app.calculo.verbas import Verba, calcular, rito, valor_da_causa
from app.modelos import Caso
from app.render.dados import montar_campos, montar_flags
from app.render.preencher import Validacao, preencher, validar

RUBRICAS_ESTIMADAS = {
    "horas_extras": "Horas extras (excedentes à 8ª diária e 44ª semanal)",
    "intervalo_art71": "Horas extras — intervalo do art. 71 da CLT",
    "minutos_residuais": "Horas extras — minutos que antecedem e sucedem a jornada",
    "adicional_noturno": "Adicional noturno e hora noturna reduzida",
    "domingos_feriados_100": "Domingos, folgas e feriados com adicional de 100%",
    "dez_minutos_cct": "Descanso de 10 minutos (cláusula 33ª da CCT)",
}

TEMPLATE = pathlib.Path(__file__).resolve().parent.parent / "templates" / "modelo.html"


@dataclass
class Resultado:
    codigo: str
    caso: Caso
    verbas: list[Verba]
    valor_causa: Decimal
    rito: str
    html: str
    validacao: Validacao
    cct: Optional[cct_mod.Enriquecimento] = None
    trace: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        return "redigido" if self.validacao.aprovado else "erro"

    def resumo(self) -> dict[str, Any]:
        return {
            "codigo": self.codigo,
            "status": self.status,
            "valor_causa": str(self.valor_causa),
            "rito": self.rito,
            "verbas": [{"codigo": v.codigo, "rubrica": v.rubrica,
                        "principal": str(v.principal), "total": str(v.total),
                        "origem": v.origem, "fundamento": v.fundamento}
                       for v in self.verbas],
            "cct": (self.cct.aplicados if self.cct else {}),
            "validacao": self.validacao.como_dict(),
            "trace": self.trace,
        }


def carregar_template() -> str:
    if not TEMPLATE.exists():
        raise FileNotFoundError(
            f"template ausente: {TEMPLATE}. Gere com scripts/preparar_template.py")
    return TEMPLATE.read_text(encoding="utf-8")


def gerar(caso: Caso, *, codigo: str, municipio: Optional[str] = None,
          consultar_cct: bool = True, template: Optional[str] = None,
          blocos: Optional[dict[str, str]] = None,
          redigir_ia: bool = False,
          consultar_cnpj: bool = True) -> Resultado:
    """Gera a peça. `blocos` são os capítulos narrativos da IA (fase 4); sem
    eles a peça sai estruturalmente correta com os capítulos marcados."""
    trace: list[str] = []

    # CNPJ antes da categoria: o CNAE da empregadora é o que decide
    # SIEMACO x SINDEEPRES, e sem ele o gate barraria todo porteiro.
    if consultar_cnpj:
        for nome, resultado in enriquecer_reclamadas(caso).items():
            trace.append(f"{nome[:34]}: {resultado}")

    # Resolver a categoria não depende de rede — faz sempre, mesmo sem consultar
    # a CCT. É o que decide se a peça pode sair.
    competencia = (resolver_competencia(caso.municipio_prestacao, caso.uf_prestacao)
                   if caso.municipio_prestacao and caso.uf_prestacao else None)
    if competencia:
        trace.append(f"competência: TRT-{competencia.regiao} "
                     f"({caso.municipio_prestacao}/{caso.uf_prestacao})"
                     + (" — CONFERIR" if competencia.revisar else ""))

    resolucao = cct_mod.resolver_categoria(caso)
    trace.append(f"categoria: {resolucao.categoria or 'INDEFINIDA'} (por {resolucao.origem})")

    enriquecimento = None
    if consultar_cct:
        cct_mod.municipios_sem_cobertura.discard(municipio or "")
        enriquecimento = cct_mod.enriquecer(caso, municipio=municipio)
        # A convenção vale para a base territorial inteira. Se o índice só tem
        # o município-sede, a busca foi refeita sem o filtro — e isso precisa
        # aparecer, porque a cláusula citada pode ser da sede e não daqui.
        if municipio and municipio in cct_mod.municipios_sem_cobertura:
            trace.append(f"CCT: '{municipio}' não indexado — cláusulas obtidas "
                         "sem filtro de município (CONFERIR base territorial)")
        if enriquecimento.erro:
            trace.append(f"CCT indisponível ({enriquecimento.erro}) — percentuais no default")
        else:
            for campo, origem in enriquecimento.aplicados.items():
                trace.append(f"{campo}: {origem}")

    # O formulário assinado não coleta salário — a especialista deduz o piso da
    # categoria. TODA a peça escala a partir dele, então o piso vem casado com o
    # CARGO na tabela da CCT; sem casamento confiável não se arbitra nada e o
    # gate barra, que é melhor do que uma peça inteira calculada errado.
    if caso.salario <= 0 and enriquecimento and enriquecimento.categoria:
        achado = cct_mod.piso_do_cargo(enriquecimento.categoria, caso.funcao,
                                       caso.rescisao, municipio)
        if achado:
            caso.salario, cargo = achado
            trace.append(f"salário: piso da CCT para '{cargo}' ({caso.salario}) "
                         "— não informado na entrevista, CONFERIR no holerite")
        else:
            trace.append(f"salário: NÃO informado e sem piso para a função "
                         f"'{caso.funcao}' na CCT — o gate vai barrar")
    elif caso.salario <= 0:
        trace.append("salário: NÃO informado e sem CCT — o gate vai barrar")

    verbas = calcular(caso)

    if redigir_ia:
        from app.redacao import redigir  # import tardio: só quem usa IA paga o custo
        saida = redigir(caso, verbas,
                        enriquecimento.clausulas if enriquecimento else [])
        uso = saida.pop("_uso", {})
        quantidades = saida.pop("quantidades", {})
        justificativa = saida.pop("justificativa_quantidades", "")
        blocos = {**(blocos or {}), **{k: v for k, v in saida.items() if isinstance(v, str)}}
        trace.append(f"IA: {len(saida)} trechos redigidos "
                     f"({uso.get('entrada', 0)} tokens in / {uso.get('saida', 0)} out, "
                     f"cache lido {uso.get('cache_lido', 0)})")
        if quantidades:
            trace.append("quantidades estimadas (h/mês): " +
                         ", ".join(f"{k.replace('_mes','')}={v:g}"
                                   for k, v in quantidades.items() if v))
        if justificativa:
            trace.append(f"base das quantidades: {justificativa[:300]}")

        # A IA dá as HORAS; a aritmética é do código. Cada rubrica tem
        # multiplicador próprio, então não saem mais valores idênticos.
        verbas += de_quantidades(caso, quantidades)

    # Fora do bloco da IA de propósito: auxílio-alimentação e vale-transporte
    # das folgas são valor da CCT x folgas x meses — aritmética, não redação.
    # Enquanto estavam lá dentro, gerar sem IA saía sem essas rubricas.
    verbas += beneficios_das_folgas(
        caso,
        valor_alimentacao_dia=caso.valor_alimentacao_dia,
        valor_transporte_dia=caso.valor_transporte_dia)

    valor, limitado = valor_da_causa(verbas)
    if limitado:
        trace.append("valor da causa limitado ao teto de R$ 400.000,00")
    r = rito(valor)

    campos = montar_campos(caso, verbas, valor, r)
    if blocos:
        campos.update(blocos)
    flags = montar_flags(caso)

    html = preencher(template if template is not None else carregar_template(),
                     campos, flags)
    val = validar(html, verbas, valor,
                  categoria=resolucao.categoria,
                  categoria_ambigua=resolucao.ambigua,
                  origem_categoria=resolucao.origem,
                  salario=caso.salario,
                  pisos=(enriquecimento.pisos if enriquecimento else None),
                  competencia=competencia)
    if not val.aprovado:
        trace.append(f"gate reprovou: {[p.codigo for p in val.problemas if p.bloqueia]}")

    return Resultado(codigo=codigo, caso=caso, verbas=verbas, valor_causa=valor,
                     rito=r, html=html, validacao=val, cct=enriquecimento, trace=trace)
