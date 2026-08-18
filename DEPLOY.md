# Deploy no Coolify

Como subir o gerador de petições. O `README.md` explica *por que* o motor é
assim; este arquivo é só o operacional.

---

## O que vai para o ar

Uma API FastAPI. Uma chamada `POST /peca/gerar` = uma petição.

```
o cliente  ──X-API-Key──▶  este serviço  ──▶  Claude (redação dos capítulos)
                                │            ──▶  ccts.nexusdevhub.com (cláusulas da CCT)
                                │            ──▶  Gotenberg (HTML→PDF, 3 renderizações)
                                └──────────────▶  db.nexusdevhub.com (PocketBase: HTML + PDF)
```

O Chromium **não** entra na imagem: quem converte para PDF é o Gotenberg. Por
isso a imagem tem ~200 MB e o build leva ~15 s.

O Python fala com o Gotenberg **direto**, guardando a Basic auth em
`GOTENBERG_USER`/`GOTENBERG_PASSWORD`. Sem essas variáveis não há fallback: a
conversão falha com erro claro e a peça em HTML fica salva para reconverter.

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

2. **Gere a chave da API** que o cliente vai usar:

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
   GOTENBERG_URL=http://72.60.61.18:3000
   GOTENBERG_USER=
   GOTENBERG_PASSWORD=
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
{"status":"ok","versao":"0.8.1","ia":true,"cct":true,"pocketbase":true,"autenticado":true}
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

## Chamar o backend

Qualquer cliente HTTP faz `POST` em `/peca/da-entrevista`:

- **URL**: `https://peticoes.nexusdevhub.com/peca/da-entrevista`
- **Headers**: `X-API-Key` = o valor de `API_KEY` (guarde como segredo, não em
  texto claro)
- **Timeout**: `600000` (10 min). Uma peça completa leva 2–4 min — uma chamada
  ao Opus mais três renderizações no Gotenberg. Com um timeout curto a chamada
  morre no meio e o cliente reporta falha de uma peça que ficou pronta.

Corpo — os campos do formulário da entrevista **como vieram**, sem traduzir nada:

```json
{
  "entrevista": {...},
  "redigir_ia": true,
  "gerar_pdf": true,
  "persistir": true
}
```

Não monte o `caso` no cliente. A tradução formulário → caso tem regra jurídica
dentro — desvio x acúmulo depende da função, o adicional noturno sai da
sobreposição do horário com a faixa 22h–5h, as faixas ("5 a 6", "R$ 180 a
R$ 200") têm critério próprio de arredondamento — e ela mora em
`app/entrevista.py`, com teste. Reescrita fora do backend, desanda calada.

Os dois endpoints existem:

| endpoint | recebe | quando usar |
|---|---|---|
| `/peca/da-entrevista` | o formulário cru | **o caminho normal** |
| `/peca/gerar` | um `Caso` já montado | reprocessar caso corrigido à mão |

O `codigo` sai do `id` do registro quando você não manda um: reenviar o mesmo
formulário atualiza a peça em vez de criar uma segunda.

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

**Para receber o PDF**, mande `Accept: application/pdf` na requisição. A
resposta vem como binário pronto para anexar ou salvar, sem decodificar nada,
e os metadados vêm em cabeçalhos:

```
Content-Disposition: attachment; filename="MARCOS.pdf"
X-Status: redigido
X-Valor-Causa: 68794.75
X-Rito: ordinario
X-Registro-Id: g2j23t041sysyu0
X-Campos-Ausentes: SALARIO,VAL_CONDUCAO
```

Sem esse cabeçalho a resposta é JSON e o PDF vai só para o PocketBase — o
`registro_id` é como buscá-lo. O `incluir_pdf_base64: true` ainda existe, mas
infla o corpo em ~33% e obriga a decodificar: prefira o `Accept`.

Se o gate barrar a peça não há PDF, e aí o `Accept: application/pdf` responde
**409** com o JSON do problema, em vez de 200 com corpo vazio.

### Ler a resposta com segurança

Para encadear uma leitura do JSON, use acesso opcional aos campos — alguns só
aparecem em certos estados. `status` vem `"redigido"` quando o gate aprovou e
`"erro"` quando barrou — e nesse caso `validacao.problemas` diz o quê. `pdf_erro`
e `persistencia_erro` só aparecem quando algo falhou; a peça em si continua na
resposta.

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
| `401` na chamada | header `X-API-Key` ausente ou com valor diferente do painel |
| `"ia":false` no `/health` | `ANTHROPIC_API_KEY` não chegou ao container |
| Peça sem cláusula de CCT | `"cct":false`, ou a categoria não foi resolvida — o `trace` da resposta diz por quê |
| `pdf_erro` na resposta | o Gotenberg não respondeu; a peça em HTML está salva e dá para reconverter |
| PDF em Letter, paginação errada | `paperWidth`/`paperHeight` ausentes — o padrão do Gotenberg é Letter, não A4 |
| Build falha em `test -f templates/...` | os assets do timbrado não foram versionados. São eles que desenham o logo e a faixa do rodapé |
| Timbrado errado nas páginas 2+ | `pypdf` não instalou. Sem ele o `pdf.py` cai num fallback silencioso e repete a capa em todas as páginas |
| A chamada morre aos 2 min | timeout do cliente HTTP; suba para 600000 |

Logs: **Application → Logs** no Coolify. Rollback: **Deployments** → o deploy
anterior → **Rollback** (a imagem antiga fica guardada).

---

## Antes de rodar com cliente de verdade

- [ ] `API_KEY` definida e o `curl` sem chave respondendo 401
- [ ] Token do PocketBase de **serviço**, com validade longa — o atual expira em
      09/08/2026 e não é renovável
- [ ] Rotacionar as credenciais que já circularam em conversa (API_KEY, CCT,
      Anthropic, PocketBase)
- [ ] Revisar a lista de municípios do TRT-2 em `app/competencia.py` — é a única
      tabela do projeto que ninguém do jurídico conferiu ainda
