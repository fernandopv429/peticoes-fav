"""Consultas públicas de enriquecimento — determinísticas, sem IA.

Hoje só CNPJ (BrasilAPI). O CNAE que ela devolve é o que decide SIEMACO ×
SINDEEPRES: a função do empregado não distingue os dois (nos dois é
Controlador/Porteiro), mas a atividade da empregadora sim.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

import httpx

BRASIL_API = "https://brasilapi.com.br/api/cnpj/v1"


@dataclass
class DadosCnpj:
    cnpj: str
    razao_social: Optional[str] = None
    cnae: Optional[str] = None
    cnae_descricao: Optional[str] = None
    endereco: Optional[str] = None


def _so_digitos(cnpj: str) -> str:
    return re.sub(r"\D", "", cnpj or "")


def consultar_cnpj(cnpj: str, *, timeout: float = 20.0) -> Optional[DadosCnpj]:
    """None em qualquer falha: o enriquecimento é opcional e nunca deve derrubar
    a geração. Sem CNAE, a categoria cai para o sindicato informado ou o gate
    barra — as duas saídas são seguras."""
    digitos = _so_digitos(cnpj)
    if len(digitos) != 14:
        return None
    try:
        r = httpx.get(f"{BRASIL_API}/{digitos}", timeout=timeout)
        if r.status_code != 200:
            return None
        d = r.json()
    except (httpx.HTTPError, ValueError):
        return None

    endereco = ", ".join(str(x) for x in (
        d.get("logradouro"), d.get("numero"), d.get("bairro")) if x)
    if d.get("municipio"):
        endereco += f" - {d['municipio']}/{d.get('uf', '')}"
    if d.get("cep"):
        endereco += f", CEP {d['cep']}"

    return DadosCnpj(cnpj=digitos, razao_social=d.get("razao_social"),
                     cnae=str(d.get("cnae_fiscal") or "") or None,
                     cnae_descricao=d.get("cnae_fiscal_descricao"),
                     endereco=endereco or None)


def enriquecer_reclamadas(caso) -> dict[str, str]:
    """Preenche CNAE e endereço oficial das reclamadas. Devolve o trace.

    Não sobrescreve endereço já informado na entrevista — o do contrato pode
    ser o do posto de trabalho, não o da sede."""
    trace: dict[str, str] = {}
    for r in caso.reclamadas:
        if not r.cnpj or r.cnae:
            continue
        d = consultar_cnpj(r.cnpj)
        if not d:
            trace[r.razao_social] = "CNPJ não consultado"
            continue
        r.cnae = d.cnae
        if not r.endereco:
            r.endereco = d.endereco
        trace[r.razao_social] = f"CNAE {d.cnae} ({d.cnae_descricao})"
    return trace
