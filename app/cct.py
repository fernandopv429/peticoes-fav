"""Cliente da base de CCTs (pgvector) — https://ccts.nexusdevhub.com

Regra de ouro: a IA só redige sobre cláusula que a busca devolveu. Se a busca
não trouxer nada acima do corte de similaridade, o percentual cai no default
legal/da banca e o caso é marcado — nunca se inventa número de cláusula.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional

import httpx

from app.modelos import Caso, Categoria, Sindicato

URL = os.environ.get("CCT_API_URL", "https://ccts.nexusdevhub.com").rstrip("/")
CHAVE = os.environ.get("CCT_API_KEY", "")

SINDICATO_DA_CATEGORIA: dict[Categoria, Sindicato] = {
    "vigilancia": "SEEVISSP",
    "asseio_conservacao": "SIEMACO",
    "terceirizados": "SINDEEPRES",
}
CATEGORIA_DO_SINDICATO: dict[Sindicato, Categoria] = {
    v: k for k, v in SINDICATO_DA_CATEGORIA.items()}

# A função SÓ decide quando é inequívoca. Controlador/Porteiro aparece em SIEMACO
# **e** em SINDEEPRES (MATRIZ_GERAL_3_MODELOS.md §2) — decidir por função ali é
# chutar, e o chute silencioso produzia peça com a CCT errada.
_MAPA_CATEGORIA: list[tuple[str, Optional[Categoria]]] = [
    (r"vigilante|seguran[çc]a patrimonial|vigil[âa]ncia", "vigilancia"),
    (r"limpeza|asseio|conserva[çc][ãa]o|copeir|servente", "asseio_conservacao"),
    (r"porteiro|controlador de acesso|recepcionista|zelador|"
     r"auxiliar de servi[çc]os", None),   # ambíguo: SIEMACO ou SINDEEPRES
]

# CNAE principal da empregadora -> categoria. É o discriminador real: o sindicato
# representa os empregados da ATIVIDADE da empresa, não do cargo do empregado.
_MAPA_CNAE: list[tuple[str, Categoria]] = [
    ("8011", "vigilancia"),          # vigilância e segurança privada
    ("8012", "vigilancia"),          # transporte de valores
    ("8121", "asseio_conservacao"),  # limpeza em prédios e domicílios
    ("8122", "asseio_conservacao"),  # imunização e controle de pragas
    ("8129", "asseio_conservacao"),  # atividades de limpeza não especificadas
    ("8130", "asseio_conservacao"),  # paisagismo
    ("7820", "terceirizados"),       # locação de mão de obra temporária
    ("7830", "terceirizados"),       # fornecimento e gestão de RH
    ("8299", "terceirizados"),       # serviços prestados a empresas
    ("8011700", "vigilancia"),
]


def categoria_por_cnae(cnae: Optional[str]) -> Optional[Categoria]:
    """CNAE do empregador -> categoria. Aceita '8121-4/00', '8121400', '81.21-4/00'."""
    if not cnae:
        return None
    digitos = re.sub(r"\D", "", str(cnae))
    for prefixo, cat in sorted(_MAPA_CNAE, key=lambda x: -len(x[0])):
        if digitos.startswith(prefixo):
            return cat
    return None


class CctIndisponivel(RuntimeError):
    """A API não respondeu ou a chave é inválida. Nunca silenciar: sem CCT a peça
    sai com percentuais default e isso precisa aparecer no trace."""


@dataclass
class Clausula:
    ref: Optional[str]
    titulo: Optional[str]
    conteudo: str
    similaridade: float
    sindicato_laboral: Optional[str] = None
    vigencia_inicio: Optional[str] = None
    vigencia_fim: Optional[str] = None
    fonte_url: Optional[str] = None


def categoria_por_funcao(funcao: str) -> Optional[Categoria]:
    """Devolve None tanto para função desconhecida quanto para função AMBÍGUA
    (Controlador/Porteiro). Quem precisa saber a diferença usa `resolver_categoria`."""
    f = (funcao or "").lower()
    for padrao, cat in _MAPA_CATEGORIA:
        if re.search(padrao, f):
            return cat
    return None


def funcao_e_ambigua(funcao: str) -> bool:
    f = (funcao or "").lower()
    return any(re.search(p, f) and cat is None for p, cat in _MAPA_CATEGORIA)


@dataclass
class Resolucao:
    categoria: Optional[Categoria]
    origem: str            # 'sindicato informado' | 'CNAE' | 'função' | 'indefinida'
    ambigua: bool = False


def resolver_categoria(caso: Caso) -> Resolucao:
    """Precedência: sindicato do holerite > CNAE da empregadora > função.

    A função só decide quando é inequívoca. Sem nenhuma das três, devolve
    indefinida — e o gate barra, em vez de gerar peça com a CCT de outro
    sindicato."""
    if caso.categoria:
        return Resolucao(caso.categoria, "categoria informada")
    if caso.sindicato:
        return Resolucao(CATEGORIA_DO_SINDICATO[caso.sindicato], "sindicato informado")

    # CNAE da EMPREGADORA (a 1ª reclamada), não da tomadora
    empregadora = next((r for r in caso.reclamadas if not r.tomadora), None)
    if empregadora and (cat := categoria_por_cnae(empregadora.cnae)):
        return Resolucao(cat, f"CNAE {empregadora.cnae}")

    if cat := categoria_por_funcao(caso.funcao):
        return Resolucao(cat, "função")
    return Resolucao(None, "indefinida", ambigua=funcao_e_ambigua(caso.funcao))


def consultar(pergunta: str, *, categoria: Optional[str] = None,
              data_fato: Optional[date] = None, municipio: Optional[str] = None,
              limite: int = 6, timeout: float = 60.0) -> list[Clausula]:
    """Busca híbrida (categoria + vigência + município + similaridade)."""
    if not CHAVE:
        raise CctIndisponivel("CCT_API_KEY não configurada")
    corpo = {"pergunta": pergunta, "limite": limite}
    if categoria:
        corpo["categoria"] = categoria
    if data_fato:
        corpo["data_fato"] = data_fato.isoformat()
    if municipio:
        corpo["municipio"] = municipio
    try:
        r = httpx.post(f"{URL}/consultar-cct", json=corpo,
                       headers={"X-API-Key": CHAVE}, timeout=timeout)
    except httpx.HTTPError as e:
        raise CctIndisponivel(f"falha de rede: {e}") from e
    if r.status_code == 401:
        raise CctIndisponivel("API key ausente ou inválida")
    r.raise_for_status()
    dados = r.json()
    return [Clausula(ref=x.get("clausula_ref"), titulo=x.get("clausula_titulo"),
                     conteudo=x.get("conteudo", ""),
                     similaridade=float(x.get("similaridade") or 0),
                     sindicato_laboral=x.get("sindicato_laboral"),
                     vigencia_inicio=str(x.get("vigencia_inicio") or "") or None,
                     vigencia_fim=str(x.get("vigencia_fim") or "") or None,
                     fonte_url=x.get("fonte_url"))
            for x in dados.get("resultados", [])]


# --- extração de percentual ------------------------------------------------

_PCT = re.compile(r"(\d{1,3}(?:[.,]\d{1,2})?)\s*%")

_ORDINAIS = {
    "primeira": 1, "segunda": 2, "terceira": 3, "quarta": 4, "quinta": 5,
    "sexta": 6, "setima": 7, "oitava": 8, "nona": 9, "decima": 10,
    "vigesima": 20, "trigesima": 30, "quadragesima": 40, "quinquagesima": 50,
    # "septagesima" não é português correto, mas é como a CCT do SEEVISSP grafa
    # a cláusula 71ª. Sem essa variante o ordinal da dezena era ignorado e
    # `numero_da_clausula` devolvia "1ª" para a cláusula de penas cominatórias.
    "sexagesima": 60, "septuagesima": 70, "setuagesima": 70, "septagesima": 70,
    "setagesima": 70, "octogesima": 80,
    "nonagesima": 90, "centesima": 100,
}

# Faixas plausíveis por tema. Um percentual fora disso é sinal de que a extração
# pegou número de outro assunto — descarta em vez de levar para a peça.
FAIXAS: dict[str, tuple[Decimal, Decimal]] = {
    "desvio":      (Decimal("0.20"), Decimal("1.00")),
    "acumulo":     (Decimal("0.10"), Decimal("0.50")),
    "gratificacao": (Decimal("0.05"), Decimal("0.30")),
}


SIMILARIDADE_MINIMA = 0.45


def _sem_acento(s: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", s)
                   if not unicodedata.combining(c)).lower()


def numero_da_clausula(ref: Optional[str], titulo: Optional[str] = None) -> Optional[str]:
    """'CLÁUSULA SEXAGÉSIMA' + 'QUARTA - INIBIÇÃO AO DESVIO' -> '64ª'

    As peças citam 'cláusula 64ª'; a base guarda o ordinal por extenso — e a
    ingestão o partiu em dois campos: `clausula_ref` fica com a dezena
    ('CLÁUSULA SEXAGÉSIMA') e `clausula_titulo` começa com a unidade ('QUARTA').
    Ler só o `ref` devolve 60ª em vez de 64ª.
    """
    if not ref and not titulo:
        return None
    txt = _sem_acento(f"{ref or ''} {titulo or ''}")
    txt = re.split(r"\s[-–—]\s", txt)[0]           # corta o assunto após o traço
    total = sum(_ORDINAIS[p] for p in re.findall(r"[a-z]+", txt) if p in _ORDINAIS)
    return f"{total}ª" if total else None


def percentual_da_clausula(cs: list[Clausula], tema: str,
                           faixa: Optional[tuple[Decimal, Decimal]] = None
                           ) -> Optional[tuple[Decimal, str]]:
    """Percentual de uma cláusula QUE TRATA do tema.

    Três travas, cada uma por causa de um erro real observado:
      1. similaridade mínima — resultado fraco da busca não vira número na peça;
      2. o tema tem que estar no TÍTULO. Menção de passagem no corpo não vale:
         uma cláusula de hora extra que citava 'gratificação' fez o percentual
         virar 60%. O título é o que diz do que a cláusula trata;
      3. o valor tem que cair na faixa plausível do tema — trava contra cláusula
         que trate do tema mas contenha vários percentuais.

    Não se exige a palavra do tema no corpo: uma cláusula intitulada 'DESVIO DE
    FUNÇÃO' costuma dizer 'será devido adicional de 50%', sem repetir 'desvio'.
    """
    alvo = re.compile(tema, re.I)
    for c in sorted(cs, key=lambda x: -x.similaridade):
        if c.similaridade < SIMILARIDADE_MINIMA:
            continue
        if not alvo.search(_sem_acento(c.titulo or "")):
            continue
        for pm in _PCT.finditer(c.conteudo):
            valor = Decimal(pm.group(1).replace(",", ".")) / 100
            if faixa and not (faixa[0] <= valor <= faixa[1]):
                continue
            return valor, (numero_da_clausula(c.ref, c.titulo) or c.ref or "cláusula não numerada")
    return None


_VALOR_BRL = re.compile(r"R\$\s*([\d.]{3,12},\d\d)")


def pisos_da_categoria(categoria: Categoria, data_fato: date,
                       municipio: Optional[str] = None) -> list[Decimal]:
    """Pisos declarados na cláusula de salário normativo, do menor para o maior.

    Serve para dois usos: preencher o salário quando a entrevista não o traz
    (a especialista deduz o piso), e conferir o salário informado."""
    try:
        cs = consultar("piso salarial da categoria, salário normativo mensal",
                       categoria=categoria, data_fato=data_fato,
                       municipio=municipio, limite=5)
    except CctIndisponivel:
        return []
    valores: set[Decimal] = set()
    for c in cs:
        if c.similaridade < SIMILARIDADE_MINIMA:
            continue
        if not re.search(r"piso|salarios? normativos?|salarios? profissiona",
                         _sem_acento(c.titulo or "")):
            continue
        for v in _VALOR_BRL.findall(c.conteudo):
            d = Decimal(v.replace(".", "").replace(",", "."))
            if Decimal("1000") <= d <= Decimal("20000"):   # descarta multa, vale, etc.
                valores.add(d)
    return sorted(valores)


# O texto diz "no valor facial de R$ 39,00" — mas a CCT de 2024 omite o "R$".
_VALOR_FACIAL = re.compile(r"valor facial de\s*(?:R\$\s*)?([\d.]{0,7}\d,\d\d)", re.I)


def _mais_recente(cs: list[Clausula], titulo_alvo: str) -> list[Clausula]:
    """Cláusulas cujo TÍTULO trate do tema, da CCT mais nova para a mais velha.

    Duas convenções podem estar vigentes na data do fato (a de 2024/2025 e a de
    2025). Vale a mais recente: foi ela que reajustou o benefício."""
    alvo = re.compile(titulo_alvo, re.I)
    achadas = [c for c in cs
               if c.similaridade >= SIMILARIDADE_MINIMA
               and alvo.search(_sem_acento(c.titulo or ""))]
    return sorted(achadas, key=lambda c: str(c.vigencia_inicio or ""), reverse=True)


def valor_do_ticket_refeicao(categoria: Categoria, data_fato: date,
                             municipio: Optional[str] = None
                             ) -> Optional[tuple[Decimal, str]]:
    """Valor facial DIÁRIO do vale/ticket-refeição -> (valor, 'cláusula 6ª').

    A entrevista não coleta esse valor; a especialista o lê da CCT. Sem ele a
    rubrica do auxílio-alimentação nas folgas não pode ser pedida com número.
    """
    try:
        cs = consultar("vale ou ticket refeição valor facial por dia trabalhado",
                       categoria=categoria, data_fato=data_fato,
                       municipio=municipio, limite=6)
    except CctIndisponivel:
        return None
    for c in _mais_recente(cs, r"vale|ticket|refei|aliment"):
        for v in _VALOR_FACIAL.findall(c.conteudo):
            d = Decimal(v.replace(".", "").replace(",", "."))
            # faixa de um benefício DIÁRIO; descarta cesta básica e piso
            if Decimal("10") <= d <= Decimal("150"):
                return d, (numero_da_clausula(c.ref, c.titulo) or c.ref or "cláusula")
    return None


def clausula_da_multa_convencional(categoria: Categoria, data_fato: date,
                                   municipio: Optional[str] = None) -> Optional[str]:
    """Número da cláusula de penas cominatórias -> '71ª'.

    É a cláusula que a peça cita ao pedir as multas convencionais. Citar número
    errado é pior do que não citar: a defesa usa isso."""
    try:
        cs = consultar("penas cominatórias multa por descumprimento das cláusulas",
                       categoria=categoria, data_fato=data_fato,
                       municipio=municipio, limite=6)
    except CctIndisponivel:
        return None
    for c in _mais_recente(cs, r"penas cominatorias|multa convencional"):
        numero = numero_da_clausula(c.ref, c.titulo)
        if numero:
            return numero
    return None


@dataclass
class Enriquecimento:
    categoria: Optional[Categoria]
    clausulas: list[Clausula]
    aplicados: dict[str, str]   # campo -> de onde veio ("cláusula 64ª" ou "default")
    erro: Optional[str] = None
    origem_categoria: str = "indefinida"
    categoria_ambigua: bool = False
    pisos: list[Decimal] = field(default_factory=list)


def enriquecer(caso: Caso, *, municipio: Optional[str] = None) -> Enriquecimento:
    """Preenche os percentuais do caso a partir da CCT vigente na data da rescisão.

    Só sobrescreve o default quando encontra cláusula — e registra a origem de
    cada valor, para o trace e para a citação na peça.
    """
    resolucao = resolver_categoria(caso)
    categoria = resolucao.categoria
    aplicados: dict[str, str] = {}

    if categoria is None:
        # Sem categoria confiável não se consulta CCT: citar cláusula do
        # sindicato errado é pior do que não citar nenhuma.
        return Enriquecimento(None, [], {}, erro=None,
                              origem_categoria=resolucao.origem,
                              categoria_ambigua=resolucao.ambigua)

    # Uma consulta POR TEMA. Uma query com 6 assuntos devolve a média semântica
    # de todos e não traz a cláusula específica de nenhum — foi o que fez a
    # cláusula de desvio (64ª) não aparecer entre os 10 primeiros resultados.
    TEMAS = [
        ("pct_desvio", "desvio", "adicional por desvio de função"),
        ("pct_acumulo", "acumulo", "adicional por acúmulo de função"),
        ("pct_gratificacao", "gratifica", "gratificação de função do condutor"),
    ]

    clausulas: list[Clausula] = []
    for campo, tema, pergunta in TEMAS:
        try:
            achadas = consultar(pergunta, categoria=categoria, data_fato=caso.rescisao,
                                municipio=municipio, limite=6)
        except CctIndisponivel as e:
            return Enriquecimento(categoria, clausulas, aplicados, erro=str(e))
        clausulas.extend(achadas)

        achado = percentual_da_clausula(achadas, tema, FAIXAS.get(tema))
        if achado:
            valor, ref = achado
            setattr(caso, campo, valor)
            aplicados[campo] = f"cláusula {ref}"
        else:
            aplicados[campo] = "default (sem cláusula aplicável na CCT)"

    # Valores que a entrevista não coleta e a CCT declara. O informado na
    # entrevista tem precedência: é o que o cliente de fato recebia.
    if caso.valor_alimentacao_dia is None:
        achado = valor_do_ticket_refeicao(categoria, caso.rescisao, municipio)
        if achado:
            caso.valor_alimentacao_dia, ref = achado
            aplicados["valor_alimentacao_dia"] = f"cláusula {ref}"
        else:
            aplicados["valor_alimentacao_dia"] = "não encontrado na CCT"

    if not caso.clausula_multa:
        caso.clausula_multa = clausula_da_multa_convencional(
            categoria, caso.rescisao, municipio)
        aplicados["clausula_multa"] = (f"cláusula {caso.clausula_multa}"
                                       if caso.clausula_multa
                                       else "não encontrada na CCT")

    if categoria and not caso.categoria:
        caso.categoria = categoria
    if categoria and not caso.sindicato:
        caso.sindicato = SINDICATO_DA_CATEGORIA[categoria]

    return Enriquecimento(categoria, clausulas, aplicados,
                          origem_categoria=resolucao.origem,
                          pisos=pisos_da_categoria(categoria, caso.rescisao, municipio))
