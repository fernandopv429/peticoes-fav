#!/usr/bin/env python3
"""Gera um token de serviço de LONGA duração no PocketBase.

    python scripts/token_pocketbase.py            # 10 anos
    python scripts/token_pocketbase.py --anos 2

O PocketBase não emite token eterno. O que existe é o endpoint `impersonate`,
que devolve um token com a duração que você pedir e `refreshable:false` — daí
"longa duração" em vez de "não expira". O token anterior do projeto foi emitido
com a duração PADRÃO e por isso morreu em poucos dias.

A senha é lida por `getpass`: não aparece na tela, não vai para o histórico do
shell e não é gravada em lugar nenhum. Ela serve só para pegar o token de
superusuário que autoriza o `impersonate`, e é descartada em seguida.
"""
import argparse
import getpass
import json
import sys
import urllib.error
import urllib.request
from base64 import urlsafe_b64decode
from datetime import datetime

BASE = "https://db.nexusdevhub.com"
SEGUNDOS_POR_ANO = 365 * 24 * 3600


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


def validade(token: str) -> str:
    """Lê o `exp` do JWT — confere na fonte em vez de confiar no que pedimos."""
    p = token.split(".")[1]
    d = json.loads(urlsafe_b64decode(p + "=" * (-len(p) % 4)))
    return datetime.fromtimestamp(d["exp"]).strftime("%d/%m/%Y %H:%M")


def main() -> None:
    global BASE                       # antes de qualquer leitura de BASE aqui

    ap = argparse.ArgumentParser()
    ap.add_argument("--anos", type=int, default=10)
    ap.add_argument("--url", default=BASE)
    args = ap.parse_args()
    BASE = args.url.rstrip("/")

    email = input(f"e-mail do superusuário em {BASE}: ").strip()
    senha = getpass.getpass("senha (não aparece na tela): ")

    st, corpo = req("POST", "/api/collections/_superusers/auth-with-password",
                    {"identity": email, "password": senha})
    del senha
    if st != 200:
        sys.exit(f"falha na autenticação ({st}): {corpo.get('message', corpo)}")

    token_curto, eu = corpo["token"], corpo["record"]
    print(f"autenticado como {eu['email']} (id {eu['id']})")

    duracao = args.anos * SEGUNDOS_POR_ANO
    st, corpo = req("POST", f"/api/collections/_superusers/impersonate/{eu['id']}",
                    {"duration": duracao}, token_curto)
    if st != 200:
        sys.exit(f"falha ao gerar o token ({st}): {corpo.get('message', corpo)}")

    token = corpo["token"]
    print(f"\ntoken válido até {validade(token)}\n")
    print("Cole em POCKETBASE_TOKEN — no .env local E nas variáveis do Coolify:\n")
    print(token)
    print("\nEste token vale tanto quanto a senha do superusuário: dá acesso "
          "total ao banco.\nNão o mande por chat nem o versione.")


if __name__ == "__main__":
    main()
