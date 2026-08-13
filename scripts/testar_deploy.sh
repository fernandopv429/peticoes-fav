#!/usr/bin/env bash
# Bateria de testes contra o serviço no ar.
#
#     ./scripts/testar_deploy.sh https://peticoes.nexusdevhub.com
#
# Sobe em escada: o que não custa nada primeiro, o que gasta Opus por último.
# A API_KEY é lida do .env — não passa por linha de comando nem fica no histórico.
set -uo pipefail

URL="${1:-}"
[ -z "$URL" ] && { echo "uso: $0 https://SEU-DOMINIO"; exit 1; }
URL="${URL%/}"

cd "$(dirname "$0")/.."
[ -f .env ] || { echo "sem .env nesta pasta"; exit 1; }
CHAVE=$(grep -m1 '^API_KEY=' .env | cut -d= -f2-)
[ -z "$CHAVE" ] && { echo "API_KEY vazia no .env"; exit 1; }

ok=0; falhou=0
checar() {  # descrição, esperado, obtido
  if [ "$2" = "$3" ]; then printf '  OK   %-46s %s\n' "$1" "$3"; ok=$((ok+1))
  else printf '  FALHA %-45s esperado %s, veio %s\n' "$1" "$2" "$3"; falhou=$((falhou+1)); fi
}

echo "== $URL =="
echo

echo "1) o serviço está no ar (sem autenticação)"
codigo=$(curl -s -o /tmp/health.json -w '%{http_code}' --max-time 20 "$URL/health")
checar "GET /health" 200 "$codigo"
if [ "$codigo" = "200" ]; then
  python3 - /tmp/health.json <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
print(f"       versão {d.get('versao')}")
for k, rotulo in [("ia","ANTHROPIC_API_KEY"), ("cct","CCT_API_KEY"),
                  ("pocketbase","POCKETBASE_TOKEN"), ("autenticado","API_KEY")]:
    print(f"       {'OK  ' if d.get(k) else '<<< '} {rotulo} {'presente' if d.get(k) else 'AUSENTE no Coolify'}")
PY
fi
echo

echo "2) a porta está fechada para quem não tem a chave"
checar "POST sem chave" 401 "$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 \
  -X POST "$URL/peca/gerar" -H 'Content-Type: application/json' -d '{"codigo":"x","caso":{}}')"
checar "POST com chave errada" 401 "$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 \
  -X POST "$URL/peca/gerar" -H 'X-API-Key: nao-e-essa' \
  -H 'Content-Type: application/json' -d '{"codigo":"x","caso":{}}')"
echo

echo "3) caso real do Marcos, sem IA e sem PDF (rápido, não gasta nada)"
codigo=$(curl -s -o /tmp/peca.json -w '%{http_code}' --max-time 120 \
  -X POST "$URL/peca/gerar" -H "X-API-Key: $CHAVE" \
  -H 'Content-Type: application/json' --data-binary @scripts/caso_teste.json)
checar "POST /peca/gerar" 200 "$codigo"
if [ "$codigo" = "200" ]; then
  python3 - /tmp/peca.json <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
print(f"       status      {d.get('status')}")
print(f"       valor causa R$ {float(d.get('valor_causa', 0)):,.2f}".replace(",", "@").replace(".", ",").replace("@", "."))
print(f"       rito        {d.get('rito')}")
print(f"       verbas      {len(d.get('verbas', []))}")
for t in d.get("trace", []):
    if any(x in t for x in ("categoria", "competência", "cláusula", "CCT")):
        print(f"       · {t}")
PY
fi
echo

echo "resultado: $ok passaram, $falhou falharam"
[ "$falhou" -eq 0 ] || exit 1

cat <<'FIM'

Passou o essencial. O teste COMPLETO — com redação da IA, PDF e gravação no
PocketBase — gasta uma chamada Opus e leva 2 a 4 minutos:

  jq '.redigir_ia=true | .gerar_pdf=true | .persistir=true' scripts/caso_teste.json \
    > /tmp/completo.json
  curl -s --max-time 600 -X POST "$URL/peca/gerar" \
    -H "X-API-Key: $CHAVE" -H 'Content-Type: application/json' \
    --data-binary @/tmp/completo.json | jq '{status, valor_causa, pdf_bytes, registro_id, pdf_erro, persistencia_erro}'
FIM
