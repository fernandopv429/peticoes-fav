#!/usr/bin/env python3
"""Cria as coleções do projeto no PocketBase. Idempotente — pode rodar de novo.

Rodar:
    export POCKETBASE_URL=https://db.nexusdevhub.com
    export PB_EMAIL='...'          # superusuário; fica só na sua sessão de shell
    export PB_PASSWORD='...'
    python scripts/setup_pocketbase.py

Alternativa sem senha, se você já tem um token de superusuário:
    export PB_TOKEN='...'
    python scripts/setup_pocketbase.py

Depois de rodar, gere um token de serviço no Admin UI (Impersonate) e coloque
em POCKETBASE_TOKEN no .env — o serviço nunca deve usar a senha do superusuário.
"""
import os
import sys
import json
import urllib.request
import urllib.error

BASE = os.environ.get("POCKETBASE_URL", "https://db.nexusdevhub.com").rstrip("/")

# PocketBase >= 0.23 (confirmado pelos IDs de coleção no padrão `pbc_*`).
COLECOES = [
    {
        "name": "peticoes",
        "type": "base",
        "fields": [
            {"name": "codigo", "type": "text", "required": True},
            {"name": "status", "type": "select", "required": True, "maxSelect": 1,
             "values": ["recebido", "calculado", "redigido", "revisao",
                        "aprovado", "entregue", "erro"]},
            {"name": "reclamante", "type": "text"},
            {"name": "caso", "type": "json", "maxSize": 2000000},
            {"name": "blocos", "type": "json", "maxSize": 2000000},
            # `text` no PocketBase trava em 5.000 caracteres mesmo com max=0;
            # a peça tem ~140 KB. `editor` não tem teto.
            {"name": "peca_html", "type": "editor", "convertURLs": False},
            {"name": "pdf", "type": "file", "maxSelect": 1, "maxSize": 20000000},
            {"name": "valor_causa", "type": "number"},
            {"name": "validacao", "type": "json", "maxSize": 500000},
        ],
        # `codigo` único = idempotência do webhook: reenvio não duplica o caso.
        "indexes": ["CREATE UNIQUE INDEX idx_peticoes_codigo ON peticoes (codigo)"],
    },
    {
        "name": "regras_aprendidas",
        "type": "base",
        "fields": [
            {"name": "capitulo", "type": "text", "required": True},
            {"name": "texto_ia", "type": "text"},
            {"name": "texto_corrigido", "type": "text"},
            {"name": "licao", "type": "text"},
            {"name": "ativa", "type": "bool"},
        ],
        "indexes": ["CREATE INDEX idx_regras_capitulo ON regras_aprendidas (capitulo)"],
    },
]


def req(metodo, caminho, corpo=None, token=None):
    dados = json.dumps(corpo).encode() if corpo is not None else None
    r = urllib.request.Request(f"{BASE}{caminho}", data=dados, method=metodo)
    r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", token)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def autenticar():
    if os.environ.get("PB_TOKEN"):
        return os.environ["PB_TOKEN"]
    email, senha = os.environ.get("PB_EMAIL"), os.environ.get("PB_PASSWORD")
    if not (email and senha):
        sys.exit("Defina PB_TOKEN, ou PB_EMAIL e PB_PASSWORD, no ambiente.")
    st, corpo = req("POST", "/api/collections/_superusers/auth-with-password",
                    {"identity": email, "password": senha})
    if st != 200:
        sys.exit(f"Falha na autenticação ({st}): {corpo.get('message', corpo)}")
    return corpo["token"]


def main():
    token = autenticar()
    print(f"autenticado em {BASE}")
    for col in COLECOES:
        st, corpo = req("POST", "/api/collections", col, token)
        if st == 200:
            print(f"  criada: {col['name']}")
        elif st == 400 and "name" in str(corpo.get("data", {})):
            print(f"  já existe: {col['name']} (nada a fazer)")
        else:
            print(f"  ERRO em {col['name']} ({st}): {corpo.get('message', corpo)}")
            print(f"    detalhe: {json.dumps(corpo.get('data', {}), ensure_ascii=False)[:400]}")

    st, corpo = req("GET", "/api/collections?perPage=200", token=token)
    if st == 200:
        nomes = [c["name"] for c in corpo.get("items", [])]
        print("\ncoleções no servidor:", ", ".join(sorted(nomes)))


if __name__ == "__main__":
    main()
