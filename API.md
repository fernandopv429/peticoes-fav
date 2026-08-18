# API — Gerador de Petições FAV

`https://peticoes.nexusdevhub.com` · versão 0.8.2

Uma chamada = uma petição inicial trabalhista, do formulário assinado ao PDF.

Para subir o serviço, ver [`DEPLOY.md`](DEPLOY.md). Para *por que* o motor é
assim, ver [`README.md`](README.md).

---

## Índice

- [Autenticação](#autenticação)
- [`GET /health`](#get-health)
- [`POST /peca/da-entrevista`](#post-pecada-entrevista) — **o endpoint principal**
  - [Opções da requisição](#opções-da-requisição)
  - [Campos da entrevista — referência completa](#campos-da-entrevista--referência-completa)
  - [Campos coletados que o motor ignora](#campos-coletados-que-o-motor-ignora)
- [`POST /peca/gerar`](#post-pecagerar)
- [`POST /peca/previa`](#post-pecaprevia)
- [Resposta](#resposta)
  - [JSON](#json)
  - [PDF binário](#pdf-binário)
- [Códigos de erro](#códigos-de-erro)
- [O que o motor decide sozinho](#o-que-o-motor-decide-sozinho)

---

## Autenticação

Todas as rotas exigem o header `X-API-Key`, exceto `/health`.

```
X-API-Key: <valor de API_KEY no ambiente do serviço>
```

| resposta | significado |
|---|---|
| `401` | chave ausente ou diferente |
| `503` | `API_KEY` não configurada no servidor |

O 503 é proposital: sem a variável o serviço **recusa** gerar, em vez de ficar
aberto. Cada chamada gasta uma requisição ao Claude e grava dados de cliente no
PocketBase.

---

## `GET /health`

Sem autenticação. É o que o Coolify usa para saber se o container subiu.

```bash
curl -s https://peticoes.nexusdevhub.com/health
```

```json
{
  "status": "ok",
  "versao": "0.8.2",
  "ia": true,
  "cct": true,
  "gotenberg": true,
  "pocketbase": true,
  "autenticado": true
}
```

| campo | |
|---|---|
| `ia` | `ANTHROPIC_API_KEY` presente |
| `cct` | `CCT_API_KEY` presente |
| `gotenberg` | `GOTENBERG_URL` + credencial presentes — **`false` = sem PDF** |
| `pocketbase` | `POCKETBASE_TOKEN` presente |
| `autenticado` | `API_KEY` presente — `false` significa que a API recusa tudo |

Reporta quais credenciais chegaram ao container, nunca o valor delas. É o
diagnóstico de "por que a peça saiu sem CCT?" sem abrir shell. `gotenberg` lê
exatamente o que a geração de PDF vai enxergar: `true` só confirma que as
variáveis existem — se a **senha** estiver errada, o PDF ainda falha com 409 e o
`pdf_erro` diz "Gotenberg recusou a credencial (401)".

---

## `POST /peca/da-entrevista`

**É o endpoint principal do backend.** Recebe os campos do formulário da
entrevista, crus, sem transformação. Os nomes dos campos (`RECL_NOME`,
`RECL1_CNPJ` etc.) seguem o formato do formulário — nomes herdados do Base44,
que foi só a fonte do formato; o backend não depende do Base44 em runtime.

Não monte o `caso` no cliente. A tradução formulário → caso tem regra jurídica
dentro — desvio × acúmulo depende da função, o adicional noturno sai da
sobreposição do horário com a faixa 22h–5h, as faixas ("5 a 6", "R$ 180 a
R$ 200") têm critério próprio de arredondamento — e mora em `app/entrevista.py`,
com teste. Reescrita fora do backend, desanda calada.

O corpo é:

```json
{
  "entrevista": {...},
  "redigir_ia": true,
  "gerar_pdf": true,
  "persistir": true
}
```

### Opções da requisição

| campo | tipo | padrão | |
|---|---|---|---|
| `entrevista` | objeto | — | **obrigatório.** O formulário da entrevista inteiro. Campo desconhecido é ignorado sem erro |
| `codigo` | string | `entrevista.id` | Id do caso. Reenviar o mesmo **atualiza** a peça em vez de criar outra. Sem `id`, cai para `CPF-data_rescisão` |
| `salario` | string | — | Sobrepõe o `SALARIO` do formulário. Aceita `"R$ 2.148,22"` ou `"2148.22"` |
| `municipio` | string | município da prestação | Filtra a CCT. Derivado de `RECL2_ENDCOMPL` (ou `RECL1_ENDCOMPL` se não há tomadora) |
| `redigir_ia` | bool | `true` | `false` devolve a peça só com a estrutura determinística, sem chamar o Claude. Útil para testar sem custo |
| `gerar_pdf` | bool | `true` | O PDF só é gerado se o gate aprovar |
| `persistir` | bool | `true` | Grava caso, HTML e PDF no PocketBase |
| `consultar_cct` | bool | `true` | `false` usa os percentuais default e não cita cláusula |
| `consultar_cnpj` | bool | `true` | Consulta o CNAE da empregadora na BrasilAPI — é o que decide SEEVISSP × SINDEEPRES × SIEMACO. Desligado, cai para a função, menos confiável |
| `incluir_pdf_base64` | bool | `false` | Devolve o PDF no JSON. Prefira `Accept: application/pdf` |
| `blocos` | objeto | — | `{tag: texto}` de capítulos prontos. Sobrepõem os da IA — é por aqui que a revisão da especialista volta ao motor |

### Campos da entrevista — referência completa

Só `RECL_NOME` é obrigatório. Todo o resto degrada: campo ausente vira `None`,
o gate barra o que for bloqueante, e `campos_ausentes` avisa o que muda a peça.

#### Identificação do reclamante

| campo | tipo | vai para | se faltar |
|---|---|---|---|
| `RECL_NOME` | texto | preâmbulo, em caixa alta | **422** — a requisição é recusada |
| `RECL_CPF` | texto | qualificação | qualificação incompleta |
| `RECL_RG` | texto | qualificação | idem |
| `RECL_PIS` | texto | qualificação | idem |
| `RECL_CTPS` | texto | qualificação | idem |
| `RECL_SERIE` | texto | qualificação (série da CTPS) | idem |
| `RECL_NASC` | data ISO | qualificação, formatada `dd/mm/aaaa` | idem |
| `RECL_FILIACAO` | texto | qualificação | idem |
| `RECL_ENDERECO` | texto | qualificação (junta com o CEP) | idem |
| `RECL_CEP` | texto | qualificação | idem |
| `RECL_NACIONALIDADE` | texto | qualificação | idem |
| `RECL_ESTADOCIVIL` | texto | qualificação | idem |
| `email` ou `RECL_EMAIL` | texto | endereço eletrônico da parte (art. 319, II, CPC) | a qualificação sai sem o e-mail do cliente |

#### Reclamadas

Aceita até três. A **1ª é a empregadora**; da 2ª em diante são **tomadoras**, o
que aciona o capítulo da Súmula 331 do TST.

| campo | tipo | vai para | se faltar |
|---|---|---|---|
| `RECL1_NOME` | texto | polo passivo | sem empregadora não há peça |
| `RECL1_CNPJ` | texto | polo passivo **e consulta de CNAE** | a categoria cai para a função, menos confiável |
| `RECL1_LOGRADOURO` | texto | endereço da 1ª | endereço incompleto |
| `RECL1_ENDCOMPL` | texto | cidade/UF/CEP da 1ª. Define a competência **quando não há tomadora** | competência indefinida |
| `RECL2_NOME` | texto | 2ª reclamada, tomadora | sem ela, não entra a Súmula 331 |
| `RECL2_CNPJ` | texto | polo passivo | — |
| `RECL2_LOGRADOURO` | texto | local da prestação | — |
| `RECL2_ENDCOMPL` | texto | cidade/UF/CEP. **É daqui que sai a competência** (art. 651 da CLT: local da prestação, não domicílio nem sede) | competência indefinida — o gate barra |
| `RECL3_*` | texto | 3ª reclamada, também tomadora | — |

#### Contrato e remuneração

| campo | tipo | vai para | se faltar |
|---|---|---|---|
| `DATA_ADMISSAO` | data ISO | avos, meses de contrato, FGTS, período aquisitivo | **bloqueia** — sem período não há cálculo |
| `DATA_RESCISAO` | data ISO | avos, saldo de salário, ano da CCT, vigência | **bloqueia** |
| `SALARIO` | texto | base de **tudo**: aviso, 13º, férias, FGTS, multas, valor-hora, dano moral | usa o piso da CCT casado com o cargo; sem casamento, o gate barra |
| `FUNCAO` | texto | qualificação, resolução de categoria, casamento do piso, e decide **desvio × acúmulo** | categoria só por CNAE |
| `tipo_dispensa` | enum | modalidade da rescisão | assume `sem_justa_causa` |

Valores aceitos em `tipo_dispensa`:

| valor | modalidade |
|---|---|
| `sem_justa_causa` | dispensa sem justa causa |
| `rescisao_indireta` | rescisão indireta (art. 483 da CLT) |
| `nulidade_pedido_demissao` ou `coacao_demissao` | pedido de demissão viciado |
| `reversao_justa_causa` | reversão da justa causa |
| `acordo` | extinção por acordo (art. 484-A) |

Valor desconhecido cai para `sem_justa_causa`.

#### Jornada

| campo | tipo | vai para | se faltar |
|---|---|---|---|
| `escala` | texto | capítulos da 12x36 e da 4x2, e a base de contagem das horas | sem capítulo de descaracterização da escala |
| `JORNADA_HORARIO` | texto | narrativa da jornada, e **inferência do noturno** quando `tem_adic_noturno` não existe | a IA fica sem horário para narrar |
| `tem_adic_noturno` | bool | adicional noturno + hora ficta do art. 73, § 1º | **inferido** da sobreposição de `JORNADA_HORARIO` com 22h–5h |
| `finais_semana` | bool | rubrica de domingos e feriados a 100% | rubrica não entra |
| `intervalo_suprimido` | bool | rubrica do art. 71, § 4º | rubrica não entra |
| `INTERVALO_GOZADO` | texto | narrativa de como o intervalo era usufruído (`"15 a 20 minutos"`, `"Rádio HT sempre ligado"`) | capítulo sem o fato concreto |
| `media_horas_extras` | texto | estimativa das horas extras (`"Até 1 hora"`) | a IA devolve 0 — não inventa quantidade |
| `periodo_antecedente` | texto | minutos residuais antes da jornada (`"30 minutos"`) | rubrica não entra |
| `periodo_sucedente` | texto | minutos residuais depois | rubrica não entra |

#### Folgas trabalhadas (FT)

| campo | tipo | vai para | se faltar |
|---|---|---|---|
| `folgas_trabalhadas` | bool | abre o capítulo | — |
| `FT_QTD_MEDIA` | texto | quantidade média/mês. Faixa vira **média**: `"5 a 6"` → 5,5 | **nenhuma rubrica de FT entra** |
| `VAL_FT` | texto | valor por folga. Faixa vira o **extremo conservador**: `"R$ 180 a R$ 200"` → 180 | sem pedido de integração dos valores por fora |
| `ft_pagamento` | texto | narrativa (`"PIX"`, `"dinheiro"`) | narrativa genérica |

Pedir o maior valor da faixa sem prova enfraquece a peça — daí o extremo
conservador no dinheiro, e a média na quantidade.

#### Benefícios

| campo | tipo | vai para | se faltar |
|---|---|---|---|
| `vale_refeicao` | bool | registro do benefício | — |
| `vale_alimentacao` | bool | abre o pedido do auxílio nas folgas | — |
| `vale_transporte` | bool | abre o pedido do VT nas folgas | — |
| `VALOR_AUX_ALIMENTACAO` | texto | valor diário do auxílio | **lê da CCT** (cláusula do tíquete-refeição) |
| `VAL_CONDUCAO` | texto | tarifa diária da condução | **o pedido de VT nas folgas não sai** — a CCT obriga o benefício mas não declara valor |

#### Teses

| campo | tipo | vai para | se faltar |
|---|---|---|---|
| `acumulo_funcao` | bool | abre desvio **ou** acúmulo, conforme a função | capítulo não entra |
| `funcoes_acumuladas` | texto | enumeração das atividades | capítulo sem conteúdo concreto |
| `gratificacao` | bool | gratificação de função **ou** prêmio de assiduidade | — |
| `gratificacao_qual` | texto | desambigua as duas, e de onde se extraem prometido/pago quando vêm no texto | pode classificar a verba errada |
| `assiduidade` | bool | prêmio de assiduidade | — |
| `assiduidade_prometido` | texto | valor prometido | a verba não é calculada |
| `assiduidade_pago` | texto | valor pago. O pedido é a **diferença** (art. 457, § 1º) | a verba não é calculada |
| `tem_periculosidade` | bool | adicional e reflexo nas horas extras (Súm. 132, I, do TST) | rubrica não entra |
| `tem_insalubridade` | bool | adicional de insalubridade | rubrica não entra |
| `tem_doenca` | bool | doença ocupacional e estabilidade | capítulos não entram |
| `desconto_indevido` | bool | abre o capítulo | — |
| `desconto_qual` | texto | o que foi descontado. **Só é lido se `desconto_indevido` for true** | capítulo sem o fato |

#### Documentos e narrativa

| campo | tipo | vai para | se faltar |
|---|---|---|---|
| `holerites` | bool | pedido de exibição | — |
| `espelho_ponto` | bool | inversão do ônus quanto aos cartões de ponto | — |
| `fatos_narrados` | texto | **a matriz fática que ancora toda a redação da IA** | a IA escreve só a partir dos campos estruturados; a peça perde os fatos do caso |

`fatos_narrados` é o campo de maior efeito na qualidade da prosa e o mais fácil
de esquecer ao montar o payload à mão. Mande o registro inteiro.

### Campos coletados que o motor ignora

Estão no formulário e no schema, mas hoje não afetam a peça. Enviar não causa
erro:

`modelo_peticao` · `titulo` · `telefone` · `ferias` · `ferias_quantidade` ·
`ft_comprovante` · `horas_extras` · `armamento_colete` · `rescisao_contratual` ·
`produtos` · `epi` · `testemunha`

Alguns são redundantes por construção: `horas_extras` é Sim/Não, mas quem decide
a rubrica é `media_horas_extras`. Outros são candidatos a entrar —
`armamento_colete` reforça a periculosidade do vigilante, `produtos` e `epi`
sustentam a insalubridade, e `ferias_quantidade` distingue férias vencidas de
proporcionais, que é diferença de valor.

### Exemplo mínimo

O menor payload que gera peça válida:

```bash
curl -s -X POST https://peticoes.nexusdevhub.com/peca/da-entrevista -H "X-API-Key: $CHAVE" -H "Content-Type: application/json" -d '{"entrevista":{"RECL_NOME":"MARCOS MOREIRA PAULO","FUNCAO":"Vigilante","DATA_ADMISSAO":"2025-04-14","DATA_RESCISAO":"2025-12-07","tipo_dispensa":"sem_justa_causa","RECL1_NOME":"VIGSEG VIGILANCIA E SEGURANCA DE VALORES LTDA","RECL1_CNPJ":"04.542.518/0002-99","RECL2_NOME":"GLP REGIS","RECL2_ENDCOMPL":"Itapecerica da Serra/SP, CEP 06877-115"},"redigir_ia":false,"gerar_pdf":false,"persistir":false}'
```

Uma peça completa leva **40 a 60 segundos** — a IA redigindo, a CCT sendo
consultada e o Gotenberg montando o PDF. Configure timeout de 600000 ms.

---

## `POST /peca/gerar`

Mesmo pipeline, mas recebe um `Caso` já montado em vez do formulário. Use para
reprocessar um caso corrigido à mão; para o fluxo normal, use o de cima.

| campo | tipo | |
|---|---|---|
| `codigo` | string | **obrigatório** |
| `caso` | objeto | **obrigatório.** Estrutura interna `Caso` — ver `app/modelos.py` |

Aceita as mesmas opções de `/peca/da-entrevista`, exceto `entrevista` e
`salario`. Não devolve `campos_ausentes`, que é diagnóstico do formulário.

---

## `POST /peca/previa`

Devolve só o HTML (`text/html`), sem gerar PDF nem gravar. Mesmo corpo de
`/peca/gerar`. Para inspeção rápida durante a revisão.

---

## Resposta

### JSON

```json
{
  "codigo": "6a74c2e6fe062ba4292e786b",
  "status": "redigido",
  "valor_causa": "68794.75",
  "rito": "ordinário",
  "verbas": [
    {
      "codigo": "VALOR_SALDO_SALARIO",
      "rubrica": "Saldo de salário",
      "principal": "501.25",
      "total": "501.25",
      "origem": "calculado",
      "fundamento": "7 dia(s) trabalhados no mês da rescisão"
    }
  ],
  "cct": {
    "pct_desvio": "cláusula 64ª",
    "pct_acumulo": "default (sem cláusula aplicável na CCT)",
    "valor_alimentacao_dia": "cláusula 6ª",
    "clausula_multa": "cláusula 71ª"
  },
  "validacao": {"aprovado": true, "problemas": []},
  "trace": [
    "competência: TRT-2 (Itapecerica da Serra/SP)",
    "categoria: vigilancia (por CNAE 8011101)",
    "salário: piso da CCT para 'vigilante' (2148.22) — não informado na entrevista, CONFERIR no holerite",
    "IA: 7 trechos redigidos (4530 tokens in / 2680 out, cache lido 0)"
  ],
  "pdf_bytes": 507548,
  "registro_id": "g2j23t041sysyu0",
  "campos_ausentes": [
    {"campo": "SALARIO", "efeito": "usa o piso da CCT da categoria; confira contra o holerite"}
  ]
}
```

| campo | |
|---|---|
| `codigo` | o id do caso, como gravado |
| `status` | `redigido` quando o gate aprovou, `erro` quando barrou |
| `valor_causa` | string decimal — string para não perder centavo em float |
| `rito` | `sumaríssimo` até 40 salários mínimos, `ordinário` acima |
| `verbas[]` | cada rubrica com `codigo`, `rubrica`, `principal`, `total` (com reflexos), `origem` (`calculado` ou `estimado`) e `fundamento` |
| `cct` | de qual cláusula veio cada percentual, ou `default` quando não achou |
| `validacao.aprovado` | `false` se algum problema bloqueia |
| `validacao.problemas[]` | `{codigo, detalhe, bloqueia}` |
| `trace[]` | as decisões do pipeline em ordem — é o que se lê quando a peça saiu estranha |
| `pdf_bytes` | tamanho do PDF gerado |
| `registro_id` | id no PocketBase; é como buscar o PDF depois |
| `campos_ausentes[]` | `{campo, efeito}` — o que faltou no formulário. Só em `/peca/da-entrevista` |
| `pdf_erro` | só aparece se o Gotenberg falhou. A peça em HTML continua salva |
| `persistencia_erro` | só aparece se o PocketBase falhou. A peça continua na resposta |

Erro de PDF ou de gravação **não** derruba a requisição: a peça volta assim
mesmo, com o erro sinalizado. O trabalho da IA não se perde por indisponibilidade
de terceiro.

### PDF binário

Mande `Accept: application/pdf` e a resposta é o arquivo, não JSON:

```bash
curl -s --max-time 900 -X POST https://peticoes.nexusdevhub.com/peca/da-entrevista -H "X-API-Key: $CHAVE" -H "Content-Type: application/json" -H "Accept: application/pdf" -d @caso.json -o peticao.pdf
```

Dois pontos que confundem no terminal:

- **`-o peticao.pdf` salva em SILÊNCIO.** A curl não imprime nada e leva ~40 s
  (IA + Gotenberg). Não travou — o arquivo aparece na pasta ao terminar. Para
  abri-lo na hora, acrescente `&& xdg-open peticao.pdf`.
- **`-d @caso.json` lê de um arquivo.** Se ele não existir, a curl falha com
  "Couldn't read data". Crie o `caso.json` com `{"entrevista": {...}}` antes, ou
  passe o JSON inline com `-d '{"entrevista": {...}}'`.

É o caminho certo para o cliente: a resposta já vem como binário, pronto para
anexar ou salvar, sem decodificar base64 — que ainda infla o corpo em ~33%.

Os metadados vão em cabeçalhos, para não se perderem na troca:

```
Content-Disposition: attachment; filename="MARCOS.pdf"
X-Status: redigido
X-Valor-Causa: 68794.75
X-Rito: ordinario
X-Registro-Id: g2j23t041sysyu0
X-Campos-Ausentes: SALARIO,VAL_CONDUCAO
```

Os valores são transliterados para ASCII: cabeçalho HTTP não carrega acento, e
mandar "ordinário" cru derruba a resposta inteira — o PDF junto.

Se o gate barrar, não há PDF para entregar: a resposta é **409** com o JSON
completo explicando, em vez de um 200 vazio.

---

## Códigos de erro

| código | quando | corpo |
|---|---|---|
| `401` | `X-API-Key` ausente ou inválida | `{"detail": "X-API-Key inválida ou ausente"}` |
| `409` | pediu PDF via `Accept` mas o gate barrou ou o Gotenberg falhou | JSON completo da peça, com `erro` |
| `422` | `entrevista` sem `RECL_NOME`, entrevista não convertível, ou corpo fora do schema | detalhe do campo |
| `500` | template ausente na imagem | caminho esperado |
| `503` | `API_KEY` não configurada no servidor | `{"detail": "API_KEY não configurada no ambiente do serviço"}` |

---

## O que o motor decide sozinho

Vale saber, para não estranhar a resposta.

**Categoria e CCT.** Precedência: sindicato do holerite > CNAE da empregadora >
função. A função só decide quando é inequívoca — "porteiro" e "controlador de
acesso" existem em SIEMACO **e** em SINDEEPRES, e chutar ali produz peça com a
CCT errada. Sem categoria confiável, o gate marca e a peça não cita cláusula.

**Salário.** Sem `SALARIO`, usa o piso da CCT **casado com o cargo** na tabela
de salários normativos — "Vigilante" → R$ 2.148,22. Se a função não casar com
nenhum cargo da convenção, não arbitra: deixa o gate barrar. Toda a peça escala
a partir do salário, e errá-lo erra tudo proporcionalmente.

**Desvio × acúmulo.** O formulário tem um campo só. A distinção é jurídica:
vigilante desviado para outra atividade é **desvio** (50%); quem soma funções à
contratada é **acúmulo** (20%). A função decide.

**Gratificação × assiduidade.** Também um campo só no formulário. O texto de
`gratificacao_qual` desambigua — são verbas diferentes, com cálculos diferentes.

**Quantidades de hora.** A IA devolve horas por mês; a aritmética é do código,
com multiplicador próprio por rubrica. `justificativa_quantidades`, no trace,
diz de qual dado da entrevista saiu cada número. Sem base na entrevista, ela
devolve 0 — não inventa quantidade.

**Reflexos.** 34,75% no total: DSR 7,25%, aviso prévio 4%, 13º 6%, férias + 1/3
7%, FGTS 7,5% e multa de 40% 3%. Verificado em seis rubricas independentes da
peça real do caso MARCOS.

**Conversão para PDF.** Três renderizações no Gotenberg — capa, miolo e a faixa
do rodapé — montadas em um documento só. O Chromium aplica um header/footer
único a todas as páginas, então a primeira página diferente do modelo Word exige
renderizar duas vezes e intercalar. O papel é A4 explícito: o padrão do
Gotenberg é Letter, e sem declarar a peça sai com paginação errada.

**O gate.** Barra `{{}}` residual, JSON da IA vazando como texto, valor da causa
divergindo da soma das verbas, teto de R$ 400.000, reflexo inconsistente,
categoria indefinida e competência indefinida. Sem aprovação, não há PDF.
