"""Competência territorial (art. 651 da CLT) — município da prestação -> TRT.

A regra é o LOCAL DA PRESTAÇÃO DOS SERVIÇOS, não o domicílio do reclamante nem
a sede da reclamada.

⚠️ São Paulo é o único estado com duas regiões, e é justamente onde o escritório
atua: **TRT-2** (capital, região metropolitana, Baixada Santista e Litoral Norte)
× **TRT-15** (Campinas — todo o restante do interior). A lista de municípios do
TRT-2 abaixo foi montada a partir da divisão jurisdicional conhecida e está
marcada como `revisar=True` para qualquer município paulista fora dela: um TRT
errado manda a peça para o juízo errado, então preferimos avisar a chutar.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

# UF -> região do TRT, para os estados com região única.
TRT_POR_UF: dict[str, int] = {
    "RJ": 1, "MG": 3, "RS": 4, "BA": 5, "PE": 6, "CE": 7, "PA": 8, "AP": 8,
    "PR": 9, "DF": 10, "TO": 10, "AM": 11, "RR": 11, "SC": 12, "PB": 13,
    "RO": 14, "AC": 14, "MA": 16, "ES": 17, "GO": 18, "AL": 19, "SE": 20,
    "RN": 21, "PI": 22, "MT": 23, "MS": 24,
    # SP não entra aqui: depende do município (ver TRT2_MUNICIPIOS).
}

REGIAO_POR_EXTENSO: dict[int, str] = {
    1: "PRIMEIRA", 2: "SEGUNDA", 3: "TERCEIRA", 4: "QUARTA", 5: "QUINTA",
    6: "SEXTA", 7: "SÉTIMA", 8: "OITAVA", 9: "NONA", 10: "DÉCIMA",
    11: "DÉCIMA PRIMEIRA", 12: "DÉCIMA SEGUNDA", 13: "DÉCIMA TERCEIRA",
    14: "DÉCIMA QUARTA", 15: "DÉCIMA QUINTA", 16: "DÉCIMA SEXTA",
    17: "DÉCIMA SÉTIMA", 18: "DÉCIMA OITAVA", 19: "DÉCIMA NONA",
    20: "VIGÉSIMA", 21: "VIGÉSIMA PRIMEIRA", 22: "VIGÉSIMA SEGUNDA",
    23: "VIGÉSIMA TERCEIRA", 24: "VIGÉSIMA QUARTA",
}

# Jurisdição do TRT da 2ª Região. Todo município paulista FORA desta lista é
# tratado como TRT-15, com pedido de conferência.
TRT2_MUNICIPIOS: set[str] = {
    # capital
    "sao paulo",
    # ABC
    "santo andre", "sao bernardo do campo", "sao caetano do sul", "diadema",
    "maua", "ribeirao pires", "rio grande da serra",
    # oeste
    "osasco", "barueri", "carapicuiba", "cotia", "itapevi", "jandira",
    "pirapora do bom jesus", "santana de parnaiba", "vargem grande paulista",
    "embu das artes", "embu-guacu", "itapecerica da serra", "taboao da serra",
    "juquitiba", "sao lourenco da serra",
    # norte
    "guarulhos", "caieiras", "cajamar", "franco da rocha", "francisco morato",
    "mairipora", "aruja", "santa isabel",
    # leste / alto tiete
    "ferraz de vasconcelos", "itaquaquecetuba", "poa", "suzano",
    "mogi das cruzes", "biritiba-mirim", "guararema", "salesopolis",
    # baixada santista
    "santos", "sao vicente", "cubatao", "guaruja", "praia grande", "bertioga",
    "itanhaem", "mongagua", "peruibe",
    # litoral norte
    "sao sebastiao", "caraguatatuba", "ubatuba", "ilhabela",
}


def normalizar(nome: str) -> str:
    sem_acento = "".join(c for c in unicodedata.normalize("NFKD", nome or "")
                         if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sem_acento).strip().lower()


@dataclass
class Competencia:
    municipio: str
    uf: str
    regiao: int
    revisar: bool = False
    motivo: str = ""

    @property
    def vara_cidade_regiao(self) -> str:
        """'SÃO PAULO/SP – SEGUNDA REGIÃO' — formato do endereçamento no modelo."""
        return f"{self.municipio.upper()}/{self.uf.upper()} – {REGIAO_POR_EXTENSO[self.regiao]} REGIÃO"

    @property
    def foro(self) -> str:
        return f"Fórum Trabalhista de {self.municipio}"


def resolver(municipio: str, uf: str) -> Optional[Competencia]:
    """Município da PRESTAÇÃO DOS SERVIÇOS -> competência. None se a UF é desconhecida."""
    uf = (uf or "").strip().upper()
    mun = (municipio or "").strip()
    if not mun or not uf:
        return None

    if uf == "SP":
        if normalizar(mun) in TRT2_MUNICIPIOS:
            return Competencia(mun, uf, 2)
        return Competencia(mun, uf, 15, revisar=True,
                           motivo="município paulista fora da lista do TRT-2 — "
                                  "assumido TRT-15 (Campinas); confirmar a jurisdição")

    if (regiao := TRT_POR_UF.get(uf)) is None:
        return None
    return Competencia(mun, uf, regiao)
