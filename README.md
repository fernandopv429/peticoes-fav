# Petições FAV — motor de geração de peças trabalhistas

Gera petição inicial trabalhista a partir da entrevista padronizada do escritório
FAV Advogados. Orquestrado pelo n8n (Nexus), com o miolo determinístico em Python.

Substitui/consolida o que hoje está espalhado entre os apps Base44
`6a5a44d24aa52c9fbdd61b1a` (HTML→DOCX) e `6a6526d39fede1a2a7a8c5a4` (docxtemplater).

> **Subir no Coolify e ligar no n8n: [`DEPLOY.md`](DEPLOY.md).**
> Este arquivo registra *por que* o motor é assim; o outro é o operacional.

---

## O invariante

> **Quem escreve a marcação é o código. A IA escreve só o texto.**

A deriva de layout do app 6a5a44 não vem de ser HTML — vem de a IA gerar o HTML.
Com o Python gerando a marcação a partir de um template congelado, o HTML fica tão
determinístico quanto um `.docx`, e a IA mantém a liberdade de redação que fazia a
prosa daquele app ser boa.

## Decisões de arquitetura

| Decisão | Escolha | Motivo |
|---|---|---|
| Formato final | **PDF** via HTML + Gotenberg | O entregável já era PDF; o `modelo-padrao.html` (conversão fiel do modelo Word) já existe |
| Geração do texto | **1 chamada** ao Claude, todos os blocos de uma vez | Coerência entre capítulos — foi o que fez o 6a5a44 escrever melhor |
| Formato da resposta da IA | **Structured output** (`output_config.format` + JSON Schema) | Elimina cerca markdown, parse frágil e JSON vazando no corpo da peça |
| Modelo | `claude-opus-5` (redação), `claude-haiku-4-5` (auditor) | `claude-3-5-*` foi aposentado em 19/02/2026 |
| Rigor | `effort` + schema + grounding | `temperature` foi **removido** no Opus 5 — enviar retorna 400 |
| Estado durável | `caso.json` (canônico) + `peca.html` (editável) | JSON permite regenerar/auditar/aprender; HTML é a superfície de edição |
| Onde o estado mora | **PocketBase** (`https://db.nexusdevhub.com`) | REST pronta (sem backend a escrever), campo `file` para o PDF, Admin UI para a especialista; já usado como file host no workflow `favatendimento` |
| Cálculo das verbas | Python, com teste contra gabarito | Cópias divergentes de `mathUtils` já causaram bug real em peça gerada |
| Estrutura da peça | Poda determinística por flag | A IA decidindo estrutura já fez sair peça sem Súmula 331 tendo tomadora |

## Fronteira n8n × Python

| n8n (orquestra) | Python (decide) |
|---|---|
| Webhook da entrevista | Extração estruturada |
| Chamada à API de CCT | Cálculo das verbas |
| Chamada ao Claude | Poda de capítulos por flag |
| Fila, retry, log | Injeção no template HTML |
| Aprovação humana | Gate de validação |
| Gotenberg → PDF | |
| Entrega | |

O cálculo **não** vai em Code node: seria mais uma cópia da fórmula, e a divergência
entre cópias já produziu peça com 3% no corpo e 2% no rol de pedidos.

## Calibragem contra as peças reais (2026-08-09)

Validado contra **MARCOS** (`Analise IA/MARCOS/Feita pela especialista.docx`) e
**JONATHAN** (`INICIAIS_REAIS/SINDEEPRES/Jonathan_x_TopService_Final.docx`).

**Exato:** dano moral (10x), multa 477, multa 467 (Marcos), 13º (Marcos),
férias (ambos), FTs por fora (Marcos).

**Dentro de 3%:** intervalo art. 71 e 10 min cl. 33ª (Marcos), minutos residuais
(Jonathan). **Dentro de 15%:** adicional noturno (Jonathan), domingos (Marcos).

### O que NÃO é calibrável — e por quê

**As peças usam bases diferentes para a mesma rubrica.** Extraindo a quantidade
implícita no intervalo do art. 71:

| Peça | h/mês implícita | Base |
|---|---|---|
| MARCOS | 15,5 | 1h × **15 plantões** |
| JONATHAN | 31,3 | 1h × **30 dias do mês** |

O dobro, mesma rubrica. Nenhuma constante reproduz as duas — qualquer valor fixo
acerta uma e erra a outra em 100%. Virou parâmetro: `Caso.criterio_horas`
(`por_plantao` — conservador, padrão — ou `por_dia_do_mes`).

O critério vale **só** para horas extras, intervalo e minutos residuais. Aplicá-lo
a adicional noturno e domingos produziu 240 h noturnas/mês numa 12x36 —
fisicamente impossível. Essas duas são limitadas pelos plantões efetivamente
trabalhados.

### Divergências que ficam, e são decisão sua

- **13º do JONATHAN:** a peça conta **12/12**, incluindo janeiro (7 dias) e
  dezembro (11). A regra dos 15 dias (art. 11, Lei 4.090/62) exclui ambos e dá
  **10/12**. O sistema usa 10 — o legalmente correto.
- **Multa 467 do JONATHAN:** a peça traz R$ 2.868,11; a fórmula da própria banca
  (50% das incontroversas, que bate ao centavo no MARCOS) dá R$ 3.431,10. A base
  implícita seria 8,4 avos — não inteiro, ou seja, não sai de fórmula. É erro de
  conta naquela peça.
- ~~**Adicional noturno do MARCOS**~~ — **RESOLVIDO.** Não era divergência da
  peça: era erro meu. Eu aplicava só o adicional de 20% do art. 73, *caput*, e
  esquecia a **hora noturna reduzida** do § 1º (52min30s valem 1 hora). Com as
  duas parcelas, 105 h reais/mês viram 39 h-equivalentes em vez de 21, e o desvio
  cai de −53% para **−12%**.

**Critério adotado (decisão do Fernando, 09/08/2026): onde as peças divergem
entre si, vale a regra LEGAL, não a que faz bater com uma delas.** Isso mantém o
13º em 10/12 no JONATHAN (regra dos 15 dias) e o art. 467 pela fórmula da banca —
os dois pontos em que aquela peça tem erro de conta.

### Resultado final

| | Sistema | Peça real | |
|---|---|---|---|
| **MARCOS — valor da causa** | R$ 68.950,38 | R$ 70.268,67 | **−1,9%** |
| 477 · 467 · dano moral | | | **exatos** |
| Intervalo art. 71 · 10 min cl. 33ª | | | −3% · −2% |
| Adicional noturno | | | −12% |

## Workflows no n8n (Nexus)

| Workflow | ID | Papel |
|---|---|---|
| **FAV — Gerar Petição (orquestração)** | `j8pll5gJgSt8ASxf` | `POST /webhook/fav-peticao` — recebe a entrevista, chama o serviço Python, responde |
| **FAV — HTML para PDF (Gotenberg)** | `FAmAf2vtpeCOtIkE` | `POST /webhook/fav-html-para-pdf` — detém a credencial Basic auth do Gotenberg |

O de orquestração distingue **três** desfechos, e a diferença importa:

| Desfecho | Resposta |
|---|---|
| Entrada incompleta | `campos_faltando: [...]` — não chega a processar |
| Serviço Python fora | `serviço de geração indisponível` |
| Gate reprovou | `bloqueios: [{codigo, detalhe}]` |

Confundir "serviço fora" com "gate reprovou" mandaria a especialista caçar
problema de validação onde há problema de infra — por isso são mensagens
distintas.

> ⚠️ **`$env` é bloqueado nas expressões do n8n** (`access to env vars denied`).
> A URL do serviço está fixa no nó *Gerar peça (Python)* — editar lá após o deploy.

## Deploy

`Dockerfile` no padrão da `cct-api` (que já roda no Coolify). Porta **8100**.
Chromium **não** entra na imagem: o PDF vem do Gotenberg, via webhook do n8n.
Env necessárias: `ANTHROPIC_API_KEY`, `CCT_API_KEY`, `POCKETBASE_TOKEN`
(`N8N_PDF_WEBHOOK`, `CCT_API_URL`, `POCKETBASE_URL` têm default).

## Fluxo

```
[webhook entrevista]
  → extrair            → caso.json
  → consultar CCT       (ccts.nexusdevhub.com, já em produção)
  → calcular            verbas + flags + valor da causa
  → redigir             1 chamada Claude → {BLOCO_*: [parágrafos]}
  → renderizar          template congelado → peca.html
  → validar             zero {{}}, soma == valor da causa, teto R$ 400.000
  → aprovação           especialista edita o HTML
  → Gotenberg           + header.html/footer.html → PDF
  → entrega
```

## Layout: o detalhe do timbrado

No modelo Word o timbrado vive no cabeçalho/rodapé e **repete em toda página**.
Em HTML→PDF isso **não** se obtém com CSS no `<body>` — o logo apareceria só na
primeira página. O Gotenberg resolve com `header.html` / `footer.html` enviados no
mesmo multipart, e exige `marginTop`/`marginBottom` grandes o suficiente para eles
caberem (margem pequena = header silenciosamente não desenhado).

Logo entra como data-URI base64, para não depender de arquivo externo.

## Infraestrutura existente (reaproveitada)

| Recurso | Endereço | Status |
|---|---|---|
| API de CCT (pgvector, 17 CCTs / 1499 cláusulas) | `https://ccts.nexusdevhub.com` | Em produção |
| Gotenberg | `http://72.60.61.18:3000/forms/chromium/convert/html` | Em produção (usado pelo `fazdocs`) |
| PocketBase | `https://db.nexusdevhub.com` | No ar. Coleções `peticoes` e `regras_aprendidas` **criadas e testadas** (índice único em `codigo` valida idempotência do webhook) |

> Recriar as coleções do zero: `python scripts/setup_pocketbase.py` (idempotente).
>
> ⚠️ **`peca_html` é do tipo `editor`, não `text`.** Campo `text` do PocketBase
> trava em **5.000 caracteres mesmo com `max: 0`** — a peça tem ~110 KB e o
> insert falha com `validation_max_text_constraint`. `editor` não tem teto
> (testado com 200 mil caracteres).
> O timbrado do FAV **não** está nas coleções `logo`/`TEMPLATE_ASSETS` — elas pertencem
> a outros produtos. O logo sai do `01_base_Jonathan_timbrado.docx`.
| n8n Nexus | `https://n8n.nexusdevhub.com` | 21 workflows |
| Modelo HTML | `modelo-padrao.html` (app 6a5a44) | A importar para `templates/` |

## Fases

1. ~~**Prova de layout**~~ — **FEITA.** `scripts/prova_layout.py` renderiza o mesmo `.docx`
   pelos dois caminhos: referência (docx→PDF, LibreOffice) × rota de produção
   (docx→HTML→PDF, Chromium = motor do Gotenberg). Resultado: **29 × 27 páginas**,
   timbrado repetindo corretamente em todas as páginas. A rota se sustenta.

   Dois achados que valem como regra do projeto:
   - **`position: fixed` NÃO desenha na margem** no Chromium em impressão — é recortado.
     Cabeçalho/rodapé corrente só via `headerTemplate`/`footerTemplate` (= `header.html`
     do Gotenberg). Chromium zera o `font-size` dentro do template: declarar sempre.
   - **O `@page` que o LibreOffice exporta está errado para o nosso uso:** ele usa a
     *distância do cabeçalho* (0,42 cm) como margem superior, não a margem de texto
     (4,3 cm). Sem remover, o corpo colide com o timbrado. `preparar_html()` remove.

   **Validado ponta a ponta no n8n** (workflow `FAmAf2vtpeCOtIkE`, webhook
   `POST /webhook/fav-html-para-pdf`): o PDF do Gotenberg saiu com **0 pixels de
   diferença** do render local. Terceiro achado, este específico do Gotenberg:

   - **Em `header.html`/`footer.html`, só estilo INLINE funciona.** Bloco `<style>`
     é ignorado pelo Chromium nesses templates — na primeira tentativa o logo foi
     ao tamanho natural (953 px) e saiu gigante e cortado. Com `style="..."` no
     próprio `<img>`, saiu correto.

   Decisão do Fernando (2026-08-08): **mesma marca em todas as páginas** — não
   replicar o `<w:titlePg/>` do Word (1ª página com logo largo). Um único template.
2. ~~**Cálculo com teste**~~ — **FEITA.** `app/calculo/verbas.py` + `app/modelos.py` +
   `app/calculo/dinheiro.py`. **24 testes passando**, incluindo os 8 valores do gabarito
   ao centavo (saldo 501,25 · aviso 2.148,22 · 13º 1.432,15 · férias 1.909,53 ·
   477 2.148,22 · 467 2.995,58 · dano 21.482,20 · desvio 8.592,88) e o "por extenso"
   batendo caractere a caractere com as peças reais.

   Decisões embutidas: dinheiro em `Decimal` com ROUND_HALF_UP (nunca `float`);
   reflexo sempre derivado do próprio principal (mata o bug de copy-paste);
   rito decidido por código pelo valor da causa, não pela IA; teto de R$ 400.000.

3. **CCT ligada** (`app/cct.py`) — validada contra a base real: Vigilante →
   desvio 50% **cláusula 64ª** (bate com `MATRIZ_GERAL_3_MODELOS.md`); Asseio →
   acúmulo 20% **cláusula 12ª**. Sem cláusula do tema, cai no default e **marca a
   origem** — nunca cita cláusula inexistente.

   Três travas, cada uma nascida de um erro observado nesta sessão:
   - **Uma consulta POR TEMA.** Uma query com 6 assuntos devolve a média semântica
     de todos: a cláusula 64ª não aparecia nem entre os 10 primeiros resultados.
   - **O tema tem que estar no TÍTULO da cláusula.** Casando também pelo corpo,
     uma cláusula de hora extra que citava "gratificação" de passagem fez
     `pct_gratificacao` virar **60%** (o correto é 10%). Teste de regressão em
     `tests/test_cct.py`.
   - **Faixa plausível por tema** (desvio 20–100%, acúmulo 10–50%, gratificação
     5–30%) + similaridade mínima 0,45.

   **SIEMACO × SINDEEPRES — bug corrigido (2026-08-08).** A `MATRIZ_GERAL_3_MODELOS.md`
   §2 mostra que **Controlador/Porteiro existe nos dois sindicatos**. O código
   decidia por função e mandava todo porteiro para `terceirizados` — ou seja,
   **todo caso SIEMACO saía com a CCT do SINDEEPRES**, em silêncio (HE 50% em vez
   de ~100%, cláusula de acúmulo errada). Os 3 casos SIEMACO do acervo (Adriano x
   Nesher, Carlos x ATS, Fabio x RBS) cairiam nisso. *O mesmo critério por função
   está descrito nos apps Base44 — vale conferir lá também.*

   O CNAE vem por consulta automática ao CNPJ (`app/consultas.py`, BrasilAPI) —
   validado nos casos reais: BK Portaria → 7830-2 (gestão de RH) → **SINDEEPRES**;
   VIGSEG → 8011-1 (vigilância) → **SEEVISSP**. O CNAE da *tomadora* é ignorado
   (Shopping Plaza Sul veio como 8112-5, condomínio predial).

   Precedência agora (`resolver_categoria`): **sindicato do holerite/TRCT** >
   **CNAE da empregadora** (8121→SIEMACO, 7820/8299→SINDEEPRES, 8011→vigilância;
   o CNAE da *tomadora* é ignorado) > **função, só quando inequívoca**. Sem
   nenhum dos três, o gate **bloqueia** com `CATEGORIA_INDEFINIDA` — não gerar é
   melhor que gerar citando a CCT de outro sindicato.

   **Salário como discriminador: testado e descartado.** Os pisos vigentes em
   09/2024 se sobrepõem — SIEMACO R$ 1.590,00–1.993,46 × SINDEEPRES
   R$ 1.590,00–1.964,49, mesmo piso-base. Só separa vigilância (R$ 2.045,92).
   Sobrou dele um ganho lateral: `pisos_da_categoria()` alimenta o aviso
   `SALARIO_ABAIXO_DO_PISO`, que é **pedido autônomo** de diferenças salariais e
   antes passava despercebido.

   **Gotcha da base:** a ingestão partiu o ordinal em dois campos — `clausula_ref`
   fica com a dezena (`CLÁUSULA SEXAGÉSIMA`) e `clausula_titulo` começa com a
   unidade (`QUARTA - INIBIÇÃO...`). Ler só o `ref` devolve **60ª** em vez de 64ª;
   `numero_da_clausula()` lê os dois.
3. ~~**Renderização**~~ — **FEITA.** `app/pipeline.py` encadeia tudo e
   `app/servico.py` expõe `POST /peca/gerar`. **41 testes.** Peça real gerada de ponta
   a ponta: CCT (cláusula 64ª) → cálculo → template → gate → PDF pelo n8n.

   **Arquitetura decidida (2026-08-08): Python é dono do miolo, n8n das pontas.**
   O n8n chama o Python **uma vez**, não cinco. Razão: o pipeline é linear, e o que
   precisa de teste é a *sequência* — ordem errada gera peça errada tão bem quanto
   fórmula errada. Espalhá-la em nós de workflow a deixaria sem teste, e cópias de
   lógica em Code node repetiriam o bug do `mathUtils` divergente. O n8n mantém o que
   só ele faz bem: webhook de entrada, **espera pela aprovação humana**, entrega
   (Evolution/e-mail) e a **credencial do Gotenberg** — o Python chama o webhook
   `fav-html-para-pdf` para gerar o PDF, sem mover credencial.

   Gate de validação (`app/render/preencher.py`) — cada checagem nasceu de um erro
   real: `{{}}` cru no corpo · JSON/markdown da IA vazando · valor da causa ≠ soma
   das verbas · teto de 400k · reflexo inconsistente com o principal. Campo sem
   valor vira `[A PREENCHER: TAG]` **visível** (avisa, não bloqueia).
4. ~~**Redação**~~ — **FEITA.** `app/redacao.py`, `claude-opus-5`, **uma chamada**
   para todos os trechos (coerência entre capítulos), **structured output** com
   schema dinâmico (só os campos que o caso sustenta), `effort: high`.

   - **Nada de `temperature`** — removido no Opus 5, retorna 400. Rigor vem do
     schema + grounding na matriz fática + `effort`.
   - **Prompt caching** no bloco de identidade/regras: 875 tokens, acima do
     mínimo de 512 do Opus 5 — da 2ª peça em diante é lido a ~0,1× do custo.
   - **Verbas por hora entram como `origem="estimado"`** (é o que a especialista
     faz); os **reflexos delas são calculados por código**.
   - Regras no system prompt, cada uma de um erro observado: não inventar fato ·
     citar só cláusula fornecida, pelo número curto (`cláusula 64ª`, não o título
     por extenso) · **não afirmar frequências que a matriz não traz** (a IA
     escreveu "quinze plantões por mês", número que veio da heurística de
     estimativa, não da entrevista) · concordância de gênero · não escrever
     valores em reais (são do código) · sem markdown.

   Efeito medido: as verbas estimadas somaram ~R$ 20 mil ao caso de teste
   (R$ 48.508,81 → **R$ 69.083,27**) e o rito virou de sumaríssimo para
   **ordinário** sozinho, ao cruzar 40 salários mínimos. Confirma que o "piso que
   subestima" era real.
5. **Edição + aprendizado** — HTML editável; diff das correções da especialista
   vira `RegraAprendida` reinjetada no prefixo cacheado.

## Pendências

- [x] **Verbas por hora: DECIDIDO (2026-08-08), com base nas 6 peças reais** em
      `~/Área de trabalho/petição referencia/`. Nenhuma usa "a apurar em liquidação";
      todas trazem valor concreto rotulado *"valor principal estimado"* (17–18
      ocorrências por peça). Vários principais são **redondos** (R$ 1.700,00 /
      3.220,00 / 1.600,00) — a especialista **arbitra**, não calcula. Logo:
      - **Principal por hora** (HE, art. 71, noturno, DSR, domingos, minutos) →
        **IA estima**, rotulado "estimado". Replica a prática real, não é remendo.
      - **Reflexos** → **código, sempre**. Percentuais do principal, medianas sobre
        86–151 observações em **25 peças reais** (todas as 4 categorias):

        | Aviso | DSR | Férias+1/3 | 13º | FGTS | Multa 40% | Total |
        |---|---|---|---|---|---|---|
        | 4,00% | 7,25% | 7,00% | 6,00% | 8,00% | 3,20% | **35,45%** |

        FGTS 8,00% é a alíquota legal e 3,20% = 40% × 8% — batem entre si, o que
        corrobora o conjunto. (Uma versão anterior deste README dizia 7,5%/3,0% e
        total 34,75%, extraídos de **uma só** peça; o corpus corrigiu.)

      - ⚠️ **O copy-paste dos reflexos é sistêmico, não exceção:** 15 blocos
        reaproveitados afetando **48 itens de pedido**. O pior usa o mesmo bloco para
        principais de R$ 1.390,75 a R$ 45.265,26 (**32×**). Por isso a taxa de acerto
        *por peça* é baixa (máx. 46%) enquanto a *mediana* cai em números redondos:
        a regra é essa, os documentos é que se desviam dela. Calcular por código
        corrige um erro que hoje chega ao protocolo.
      - Evidência da decisão: **0** ocorrências de "a apurar/em liquidação" nas 25
        peças, contra **369** de "valor estimado".
- [ ] As 5 perguntas da seção "DECISÕES necessárias" do `MATRIZ_GERAL_3_MODELOS.md`
      (HE% do SIEMACO, intervalo art. 71 do Vigilante, periculosidade, multa
      convencional) **calibram** a estimativa — não bloqueiam mais a v1.
- [ ] **`CCT_API_KEY` — a chave em `Agente 1.0/.env` está inválida (HTTP 401).**
      Provavelmente rotacionada (havia recomendação, pois vazou em chat). O cliente
      `app/cct.py` está pronto; falta só a chave vigente (Coolify → env do serviço
      `cct-api`, ou o secret do app Base44). A API em si está no ar: `/health` OK,
      17 documentos / 1499 cláusulas.
- [ ] **`ANTHROPIC_API_KEY` não existe** no ambiente nem em nenhum `.env` — necessária
      para a fase 4 (redação).
- [x] **Competência territorial (art. 651)** — `app/competencia.py`. Município da
      **prestação dos serviços** (não o domicílio do reclamante nem a sede da
      reclamada) → TRT. Preenche `VARA_CIDADE_REGIAO` no formato do modelo
      (`SÃO PAULO/SP – SEGUNDA REGIÃO`). Gate bloqueia sem local de prestação.
      ⚠️ **SP é o único estado com duas regiões, e é onde a banca atua:** TRT-2
      (capital, região metropolitana, Baixada Santista, Litoral Norte) × TRT-15
      (Campinas — resto do interior). Municípios paulistas fora da lista do TRT-2
      caem em TRT-15 com aviso `COMPETENCIA_A_CONFERIR` — **a lista precisa de
      revisão jurídica antes de produção.**
- [ ] Confirmar que `modelo-padrao.html` é o modelo oficial vigente da banca.
- [ ] Rotacionar os tokens do n8n (colados em chat, **sem expiração**).
