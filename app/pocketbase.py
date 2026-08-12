"""Persistência no PocketBase (https://db.nexusdevhub.com).

Estado canônico da peça: `caso` (JSON) permite regerar e auditar; `peca_html` é
a superfície que a especialista edita; `pdf` é o entregável.
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

import httpx

URL = os.environ.get("POCKETBASE_URL", "https://db.nexusdevhub.com").rstrip("/")
TOKEN = os.environ.get("POCKETBASE_TOKEN", "")
COLECAO = "peticoes"


class PocketBaseIndisponivel(RuntimeError):
    pass


def _headers() -> dict[str, str]:
    if not TOKEN:
        raise PocketBaseIndisponivel("POCKETBASE_TOKEN não configurado")
    return {"Authorization": TOKEN}


def buscar_por_codigo(codigo: str) -> Optional[dict[str, Any]]:
    r = httpx.get(f"{URL}/api/collections/{COLECAO}/records",
                  params={"filter": f'codigo="{codigo}"', "perPage": 1},
                  headers=_headers(), timeout=30)
    r.raise_for_status()
    itens = r.json().get("items", [])
    return itens[0] if itens else None


def salvar(codigo: str, dados: dict[str, Any]) -> dict[str, Any]:
    """Cria ou atualiza pelo `codigo`. O índice único garante idempotência —
    reenvio do webhook não duplica o caso."""
    corpo = {k: (json.dumps(v, default=str) if isinstance(v, (dict, list)) else v)
             for k, v in dados.items()}
    corpo["codigo"] = codigo
    existente = buscar_por_codigo(codigo)
    if existente:
        r = httpx.patch(f"{URL}/api/collections/{COLECAO}/records/{existente['id']}",
                        json=corpo, headers=_headers(), timeout=30)
    else:
        r = httpx.post(f"{URL}/api/collections/{COLECAO}/records",
                       json=corpo, headers=_headers(), timeout=30)
    r.raise_for_status()
    return r.json()


def anexar_pdf(record_id: str, pdf: bytes, nome: str = "peticao.pdf") -> dict[str, Any]:
    r = httpx.patch(f"{URL}/api/collections/{COLECAO}/records/{record_id}",
                    files={"pdf": (nome, pdf, "application/pdf")},
                    headers=_headers(), timeout=120)
    r.raise_for_status()
    return r.json()
