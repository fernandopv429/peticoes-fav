"""Preenchimento do template + gate de validação.

O gate é a última barreira antes do PDF. Ele existe porque cada item que ele
checa já saiu errado numa peça real: `{{}}` cru no corpo, valor da causa
divergindo do rol de pedidos, JSON da IA vazando como texto.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from app.calculo.dinheiro import centavos
from app.calculo.verbas import TETO_VALOR_CAUSA, Verba

# {{#flag}} ... {{/flag}}  — sem aninhamento no template atual
_BLOCO = r"\{\{\s*#\s*%s\s*\}\}(.*?)\{\{\s*/\s*%s\s*\}\}"
_CAMPO = re.compile(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}")
_QUALQUER_TAG = re.compile(r"\{\{.*?\}\}", re.S)
_P_VAZIO = re.compile(r"<p[^>]*>(?:\s|&nbsp;|<br\s*/?>)*</p>", re.I)

MARCADOR = "[A PREENCHER: {}]"


def resolver_flags(html: str, flags: dict[str, bool]) -> str:
    """Mantém o miolo das flags verdadeiras, remove o das falsas."""
    for nome, ligada in flags.items():
        padrao = re.compile(_BLOCO % (re.escape(nome), re.escape(nome)), re.S)
        html = padrao.sub((lambda m: m.group(1)) if ligada else "", html)
    return html


def preencher(html: str, campos: dict[str, str], flags: dict[str, bool]) -> str:
    """Resolve flags, substitui campos e converte o que sobrou em marcador visível.

    Nunca deixa `{{}}` no documento: tag sem valor vira [A PREENCHER: TAG], que
    o advogado enxerga na revisão em vez de descobrir no protocolo.
    """
    html = resolver_flags(html, flags)
    html = _CAMPO.sub(lambda m: campos.get(m.group(1)) or MARCADOR.format(m.group(1)), html)
    html = _QUALQUER_TAG.sub("", html)      # flags órfãs, sem par
    return _P_VAZIO.sub("", html)


# --- gate ------------------------------------------------------------------

@dataclass
class Problema:
    codigo: str
    detalhe: str
    bloqueia: bool = True


@dataclass
class Validacao:
    problemas: list[Problema] = field(default_factory=list)

    @property
    def aprovado(self) -> bool:
        return not any(p.bloqueia for p in self.problemas)

    def como_dict(self) -> dict:
        return {"aprovado": self.aprovado,
                "problemas": [{"codigo": p.codigo, "detalhe": p.detalhe,
                               "bloqueia": p.bloqueia} for p in self.problemas]}


def validar(html: str, verbas: list[Verba], valor_causa: Decimal,
            *, categoria: Optional[str] = None, categoria_ambigua: bool = False,
            origem_categoria: str = "", salario: Optional[Decimal] = None,
            pisos: Optional[list[Decimal]] = None,
            competencia: Optional[object] = None) -> Validacao:
    v = Validacao()

    # TRT errado manda a peça para o juízo errado.
    if competencia is None:
        v.problemas.append(Problema(
            "COMPETENCIA_INDEFINIDA",
            "informe o município/UF da PRESTAÇÃO DOS SERVIÇOS (art. 651 CLT)"))
    elif getattr(competencia, "revisar", False):
        v.problemas.append(Problema("COMPETENCIA_A_CONFERIR",
                                    getattr(competencia, "motivo", ""), bloqueia=False))

    # Sem categoria confiável, a peça sairia com a CCT de outro sindicato —
    # Controlador/Porteiro existe em SIEMACO **e** em SINDEEPRES, e a função
    # não distingue os dois. Bloqueia: informe o sindicato do holerite ou o
    # CNAE da empregadora.
    if categoria is None:
        v.problemas.append(Problema(
            "CATEGORIA_INDEFINIDA",
            "função ambígua entre SIEMACO e SINDEEPRES — informe `sindicato` "
            "(holerite/TRCT) ou o `cnae` da empregadora"
            if categoria_ambigua else
            f"categoria da CCT não identificada ({origem_categoria})"))

    # Salário abaixo do piso normativo é pedido autônomo de diferenças salariais
    # — hoje isso passava despercebido.
    if salario is not None and pisos:
        if (menor := min(pisos)) > Decimal(salario):
            v.problemas.append(Problema(
                "SALARIO_ABAIXO_DO_PISO",
                f"salário {salario} abaixo do menor piso da CCT ({menor}) — "
                "cabe pedido de diferenças salariais",
                bloqueia=False))

    if sobras := _QUALQUER_TAG.findall(html):
        v.problemas.append(Problema("TAG_NAO_RESOLVIDA",
                                    f"{len(sobras)} tag(s) cruas: {sobras[:5]}"))

    if faltantes := re.findall(r"\[A PREENCHER: ([A-Z0-9_]+)\]", html):
        v.problemas.append(Problema("CAMPO_SEM_VALOR",
                                    f"{len(faltantes)} campo(s): {sorted(set(faltantes))[:8]}",
                                    bloqueia=False))

    # JSON/markdown da IA vazando como texto — aconteceu em peça real
    for marca, cod in ((r'\{\s*"BLOCO_', "JSON_DA_IA_NO_CORPO"),
                       (r"```", "MARKDOWN_NO_CORPO")):
        if re.search(marca, html):
            v.problemas.append(Problema(cod, "saída da IA não desembrulhada"))

    soma = centavos(sum(x.total for x in verbas))
    esperado = min(soma, TETO_VALOR_CAUSA)
    if centavos(valor_causa) != esperado:
        v.problemas.append(Problema(
            "VALOR_CAUSA_DIVERGENTE",
            f"soma das verbas {soma} != valor da causa {valor_causa}"))

    if centavos(valor_causa) > TETO_VALOR_CAUSA:
        v.problemas.append(Problema("TETO_EXCEDIDO",
                                    f"{valor_causa} acima de {TETO_VALOR_CAUSA}"))

    for x in verbas:
        if x.reflexos:
            esperado_total = centavos(x.principal + sum(x.reflexos.values()))
            if x.total != esperado_total:
                v.problemas.append(Problema(
                    "REFLEXO_INCONSISTENTE",
                    f"{x.codigo}: total {x.total} != principal + reflexos {esperado_total}"))

    return v
