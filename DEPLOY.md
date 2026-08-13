# Deploy no Coolify

Como subir o gerador de petições. O `README.md` explica *por que* o motor é
assim; este arquivo é só o operacional.

---

## O que vai para o ar

Uma API FastAPI. Uma chamada `POST /peca/gerar` = uma petição.

```
n8n  ──X-API-Key──▶  este serviço  ──▶  Claude (redação dos capítulos)
                          │            ──▶  ccts.nexusdevhub.com (cláusulas da CCT)
                          │            ──▶  webhook do n8n ──▶ Gotenberg (HTML→PDF)
                          └──────────────▶  db.nexusdevhub.com (PocketBase: HTML + PDF)
```

O Chromium **não** entra na imagem: quem converte para PDF é o Gotenberg, e a
credencial Basic auth dele fica no n8n, não aqui. Por isso a imagem tem ~200 MB
e o build leva ~15 s.

| | |
|---|---|
| Porta | `8100` |
| Healthcheck | `GET /health` (não exige chave) |
| Build pack | Dockerfile |
| Persistência | nenhuma — o serviço não escreve em disco |

---

## Pré-requisitos

1. **O repositório precisa estar num Git acessível pelo Coolify.** Hoje ele é
   local e ainda não tem nenhum commit:

   ```bash
   git -C "$PWD" add -A && git -C "$PWD" commit -m "motor de petições: primeira versão"
   ```

   Depois crie o repositório remoto (privado — o histórico não tem segredo, mas
   o projeto é interno) e envie:

   ```bash
   git remote add origin git@github.com:SEU-ORG/peticoes-fav.git && git push -u origin master
   ```

2. **Gere a chave da API** que o n8n vai usar:

   ```bash
   openssl rand -hex 32
   ```

3. Tenha em mãos: `ANTHROPIC_API_KEY`, `CCT_API_KEY` e o token de serviço do
   PocketBase.

---

## Passo a passo no Coolify

1. **+ New** → **Application** → **Public/Private Repository**, aponte para o
   repositório e escolha o branch.
2. **Build Pack**: `Dockerfile`. Não mexa em Base Directory nem em Dockerfile
   Location — os padrões (`/` e `/Dockerfile`) estão certos.
3. **Port Exposes**: `8100`.
4. **Environment Variables** — cole o bloco abaixo em *Developer view* e
   preencha os valores vazios. Marque **Build Variable? = não** em todas: são
   lidas em tempo de execução, e marcar como build assa a chave na imagem.

   ```
   API_KEY=
   ANTHROPIC_API_KEY=
   ANTHROPIC_MODEL=claude-opus-5
   CCT_API_URL=https://ccts.nexusdevhub.com
   CCT_API_KEY=
   N8N_PDF_WEBHOOK=https://n8n.nexusdevhub.com/webhook/fav-html-para-pdf
   POCKETBASE_URL=https://db.nexusdevhub.com
   POCKETBASE_TOKEN=
   ```

5. **Domains**: defina o domínio (ex.: `peticoes.nexusdevhub.com`). O Coolify
   emite o certificado sozinho.
6. **Health Check**: caminho `/health`, porta `8100`. O `HEALTHCHECK` do
   Dockerfile já cobre isso; configurar no painel é o que faz o Coolify segurar
   o deploy antigo até o novo responder.
7. **Deploy**.

### Conferir se subiu

```bash
curl -s https://peticoes.nexusdevhub.com/health
```

Resposta esperada — os quatro booleanos dizem quais credenciais chegaram:

```json
{"status":"ok","versao":"0.4.0","ia":true,"cct":true,"pocketbase":true,"autenticado":true}
```

Qualquer `false` é variável de ambiente faltando. `"autenticado":false` é o mais
grave: significa que `API_KEY` não foi definida — o serviço **recusa** gerar
peça nesse estado (503), de propósito.

Agora prove que o guarda está de pé:

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST https://peticoes.nexusdevhub.com/peca/gerar -H 'Content-Type: application/json' -d '{"codigo":"X","caso":{}}'
```

Tem que dar **401**. Se der 422, a API está aberta para a internet — pare e
confira a `API_KEY`.

---

## Ligar o n8n

> **Isto quebra o workflow atual.** O nó *Gerar peça (Python)* do workflow
> `j8pll5gJgSt8ASxf` hoje chama o serviço sem cabeçalho nenhum. Depois deste
> deploy ele passa a receber 401 até você adicionar a chave.

No nó *Gerar peça (Python)*:

- **URL**: `https://peticoes.nexusdevhub.com/peca/da-entrevista`
- **Headers**: `X-API-Key` = o valor de `API_KEY` (guarde como credencial do
  n8n, não em texto no nó)
- **Timeout**: `600000` (10 min). Uma peça completa leva 2–4 min — uma chamada
  ao Opus mais três renderizações no Gotenberg. Com o padrão a execução morre
  no meio e o n8n reporta falha de uma peça que ficou pronta.

Corpo — o registro do Base44 **como veio**, sem traduzir nada:

```json
{
  "entrevista": {{ JSON.stringify($json) }},
  "redigir_ia": true,
  "gerar_pdf": true,
  "persistir": true
}
```

Não monte o `caso` no workflow. A tradução formulário → caso tem regra jurídica
dentro — desvio x acúmulo depende da função, o adicional noturno sai da
sobreposição do horário com a faixa 22h–5h, as faixas ("5 a 6", "R$ 180 a
R$ 200") têm critério próprio de arredondamento — e ela mora em
`app/entrevista.py`, com teste. Reescrita em expressão de nó, desanda calada.

Os dois endpoints existem:

| endpoint | recebe | quando usar |
|---|---|---|
| `/peca/da-entrevista` | o formulário cru | **o webhook** — é o caminho normal |
| `/peca/gerar` | um `Caso` já montado | reprocessar caso corrigido à mão |

O `codigo` sai do `id` do registro quando você não manda um: reenviar o mesmo
webhook atualiza a peça em vez de criar uma segunda.

**Salário.** O formulário assinado não coleta salário. Sem `SALARIO` no
registro, o serviço usa o piso da CCT **casado com o cargo** — para "Vigilante",
R$ 2.148,22 da tabela de salários normativos. Se a função não casar com nenhum
cargo da convenção, ele NÃO arbitra: deixa o gate barrar. É a decisão certa,
porque toda a peça escala a partir do salário.

**`campos_ausentes` na resposta.** Lista o que faltou no formulário e o efeito
de cada falta. Vale mandar para a especialista junto com a peça:

```json
"campos_ausentes": [
  {"campo": "SALARIO", "efeito": "usa o piso da CCT da categoria; confira contra o holerite"},
  {"campo": "VAL_CONDUCAO", "efeito": "sem tarifa, o vale-transporte das folgas não é pedido"},
  {"campo": "tem_adic_noturno", "efeito": "inferido do horário: SIM"}
]
```

O PDF vai para o PocketBase; o `registro_id` da resposta é como buscá-lo. Se
preferir recebê-lo direto no n8n, mande `"incluir_pdf_base64": true` — custa uns
2 MB de payload por peça.

### Ler a resposta sem quebrar a execução

Campo ausente numa expressão do n8n mata a execução inteira. Use encadeamento
opcional:

```
{{ $json?.status === 'redigido' }}
```

`status` vem `"redigido"` quando o gate aprovou e `"erro"` quando barrou — e
nesse caso `validacao.problemas` diz o quê. `pdf_erro` e `persistencia_erro` só
aparecem quando algo falhou; a peça em si continua na resposta.

---

## Rodar local

Igual à produção, na mesma imagem:

```bash
cp .env.example .env && docker compose up --build
```

Sem Docker, para desenvolver:

```bash
python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
```

```bash
set -a && . ./.env && set +a && .venv/bin/uvicorn app.servico:app --port 8100 --reload
```

(o serviço lê variáveis de ambiente direto, sem `python-dotenv` — daí o
`set -a`.)

Testes, que não tocam a rede:

```bash
.venv/bin/python -m pytest -q
```

Gerar a peça de referência do Marcos e comparar com a da especialista:

```bash
set -a && . ./.env && set +a && .venv/bin/python scripts/gerar_marcos.py --ia --pdf
```

---

## Quando der errado

| Sintoma | Causa |
|---|---|
| `503 API_KEY não configurada` | faltou a variável no Coolify. É a falha desejada: fecha em vez de abrir |
| `401` vindo do n8n | header `X-API-Key` ausente ou com valor diferente do painel |
| `"ia":false` no `/health` | `ANTHROPIC_API_KEY` não chegou ao container |
| Peça sem cláusula de CCT | `"cct":false`, ou a categoria não foi resolvida — o `trace` da resposta diz por quê |
| `pdf_erro` na resposta | o webhook do Gotenberg no n8n não respondeu; a peça em HTML está salva e dá para reconverter |
| Build falha em `test -f templates/...` | os assets do timbrado não foram versionados. São eles que desenham o logo e a faixa do rodapé |
| Timbrado errado nas páginas 2+ | `pypdf` não instalou. Sem ele o `pdf.py` cai num fallback silencioso e repete a capa em todas as páginas |
| Execução do n8n morre aos 2 min | timeout do nó HTTP; suba para 600000 |

Logs: **Application → Logs** no Coolify. Rollback: **Deployments** → o deploy
anterior → **Rollback** (a imagem antiga fica guardada).

---

## Antes de rodar com cliente de verdade

- [ ] `API_KEY` definida e o `curl` sem chave respondendo 401
- [ ] Token do PocketBase de **serviço**, com validade longa — o atual expira em
      09/08/2026 e não é renovável
- [ ] Rotacionar as credenciais que já circularam em conversa (n8n, CCT,
      Anthropic, PocketBase)
- [ ] Revisar a lista de municípios do TRT-2 em `app/competencia.py` — é a única
      tabela do projeto que ninguém do jurídico conferiu ainda
