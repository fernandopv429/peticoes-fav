# API — Gerador de Petições FAV

`https://peticoes.nexusdevhub.com` · versão 0.6.0

Uma chamada = uma petição inicial trabalhista, do formulário ao PDF.

Para subir o serviço, ver [`DEPLOY.md`](DEPLOY.md). Para *por que* o motor é
assim, ver [`README.md`](README.md).

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
aberto. Cada chamada gasta uma requisição ao Claude e grava dados de cliente.

---

## `GET /health`

Sem autenticação. É o que o Coolify usa para saber se o container subiu.

```bash
curl -s https://peticoes.nexusdevhub.com/health
```

```json
{"status":"ok","versao":"0.6.0","ia":true,"cct":true,"pocketbase":true,"autenticado":true}
```

Os quatro booleanos dizem quais credenciais chegaram ao container — nunca o
valor delas. É o diagnóstico de "por que a peça saiu sem CCT?" sem abrir shell.

---

## `POST /peca/da-entrevista`

**É este que o webhook do n8n deve chamar.** Recebe o registro da entidade
`Entrevista` do app Base44 `6a734d6c72c1f853994b8733`, cru, sem transformação.

Não monte o `caso` no workflow: a tradução formulário → caso tem regra jurídica
dentro (desvio × acúmulo pela função, adicional noturno por sobreposição do
horário com a faixa 22h–5h, extremo conservador das faixas "5 a 6"), mora em
`app/entrevista.py` e tem teste. Reescrita em expressão de nó, desanda calada.

### Corpo

| campo | tipo | padrão | |
|---|---|---|---|
| `entrevista` | objeto | — | **obrigatório.** O registro do Base44 inteiro |
| `codigo` | string | `entrevista.id` | id do caso; é o que dá idempotência |
| `salario` | string | — | sobrepõe o `SALARIO` do formulário (`"R$ 2.148,22"`) |
| `municipio` | string | do local da prestação | município para filtrar a CCT |
| `redigir_ia` | bool | `true` | `false` devolve só a estrutura determinística |
| `gerar_pdf` | bool | `true` | |
| `persistir` | bool | `true` | grava no PocketBase |
| `consultar_cct` | bool | `true` | |
| `consultar_cnpj` | bool | `true` | CNAE da empregadora — decide a categoria |
| `incluir_pdf_base64` | bool | `false` | prefira `Accept: application/pdf` |
| `blocos` | objeto | — | capítulos prontos; sobrepõem os da IA |

Reenviar o mesmo `codigo` **atualiza** a peça em vez de criar uma segunda.

### Exemplo

```bash
curl -s --max-time 900 -X POST https://peticoes.nexusdevhub.com/peca/da-entrevista -H "X-API-Key: $CHAVE" -H "Content-Type: application/json" -d '{"entrevista":{"id":"6a74c2e6fe062ba4292e786b","RECL_NOME":"MARCOS MOREIRA PAULO","RECL_CPF":"105.678.257-95","FUNCAO":"Vigilante","DATA_ADMISSAO":"2025-04-14","DATA_RESCISAO":"2025-12-07","tipo_dispensa":"sem_justa_causa","escala":"12x36","JORNADA_HORARIO":"das 19h às 07h","RECL1_NOME":"VIGSEG VIGILANCIA E SEGURANCA DE VALORES LTDA","RECL1_CNPJ":"04.542.518/0002-99","RECL2_NOME":"GLP REGIS","RECL2_CNPJ":"46.652.606/0001-02","RECL2_ENDCOMPL":"Itapecerica da Serra/SP, CEP 06877-115","folgas_trabalhadas":true,"FT_QTD_MEDIA":"5 a 6 por mês","VAL_FT":"R$ 180 a R$ 200","acumulo_funcao":true,"tem_periculosidade":true}}'
```

Leva **40 a 60 segundos** sem imprimir nada: é a IA redigindo, a CCT sendo
consultada e o Gotenberg montando o PDF. Configure timeout de 600000 ms.

---

## `POST /peca/gerar`

Mesmo pipeline, mas recebe um `Caso` já montado em vez do formulário. Use para
reprocessar um caso corrigido à mão; para o fluxo normal, use o de cima.

O corpo aceita `codigo` (obrigatório), `caso` e as mesmas opções acima.

---

## `POST /peca/previa`

Devolve só o HTML, sem gerar PDF nem gravar. Para inspeção rápida.

---

## Resposta

### JSON (padrão)

```json
{
  "codigo": "6a74c2e6fe062ba4292e786b",
  "status": "redigido",
  "valor_causa": "68794.75",
  "rito": "ordinário",
  "verbas": [
    {"codigo": "VALOR_SALDO_SALARIO", "rubrica": "Saldo de salário",
     "principal": "501.25", "total": "501.25", "origem": "calculado",
     "fundamento": "7 dia(s) trabalhados no mês da rescisão"}
  ],
  "cct": {"pct_desvio": "cláusula 64ª", "valor_alimentacao_dia": "cláusula 6ª"},
  "validacao": {"aprovado": true, "problemas": []},
  "trace": ["categoria: vigilancia (por CNAE 8011101)", "..."],
  "pdf_bytes": 507548,
  "registro_id": "g2j23t041sysyu0",
  "campos_ausentes": [
    {"campo": "SALARIO", "efeito": "usa o piso da CCT; confira contra o holerite"}
  ]
}
```

| campo | |
|---|---|
| `status` | `redigido` quando o gate aprovou, `erro` quando barrou |
| `valor_causa` | string decimal, para não perder centavo em float |
| `verbas` | cada rubrica com principal, total, origem e fundamento |
| `cct` | de qual cláusula veio cada percentual, ou `default` |
| `validacao.problemas` | o que o gate apontou; `bloqueia` diz se impede o PDF |
| `trace` | decisões do pipeline, em ordem — é o que se lê quando algo saiu estranho |
| `campos_ausentes` | o que faltou no formulário e o efeito de cada falta |
| `pdf_erro` / `persistencia_erro` | só aparecem quando falharam; a peça continua na resposta |

O PDF vai para o PocketBase; `registro_id` é como buscá-lo depois.

### PDF binário

Mande `Accept: application/pdf` e a resposta é o arquivo, não JSON:

```bash
curl -s --max-time 900 -X POST https://peticoes.nexusdevhub.com/peca/da-entrevista -H "X-API-Key: $CHAVE" -H "Content-Type: application/json" -H "Accept: application/pdf" -d @caso.json -o peticao.pdf
```

No n8n é o caminho certo: o nó HTTP já entrega um item binário, pronto para
anexar ou salvar, sem nó Code para decodificar base64 (que ainda infla o corpo
em ~33%).

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
completo explicando o motivo, em vez de um 200 vazio.

---

## Códigos de erro

| | |
|---|---|
| `401` | `X-API-Key` ausente ou inválida |
| `409` | pediu PDF (`Accept`) mas o gate barrou ou o Gotenberg falhou |
| `422` | entrevista sem `RECL_NOME`, ou corpo fora do schema |
| `500` | template ausente na imagem |
| `503` | `API_KEY` não configurada no servidor |

---

## O que o motor decide sozinho

Vale saber, para não estranhar a resposta:

**Categoria e CCT.** Precedência: sindicato do holerite > CNAE da empregadora >
função. A função só decide quando é inequívoca — "porteiro" e "controlador de
acesso" existem em SIEMACO **e** em SINDEEPRES, e chutar ali produz peça com a
CCT errada. Sem categoria confiável, o gate marca e a peça não cita cláusula.

**Salário.** Sem `SALARIO` no formulário, usa o piso da CCT **casado com o
cargo** na tabela de salários normativos. Se a função não casar com nenhum
cargo, não arbitra: deixa o gate barrar. Toda a peça escala a partir do salário.

**Quantidades de hora.** A IA devolve horas por mês; o cálculo é do código, com
multiplicador próprio por rubrica. `justificativa_quantidades`, no trace, diz de
qual dado da entrevista saiu cada número.

**O gate.** Barra `{{}}` residual, JSON vazando como texto, valor da causa
divergindo da soma das verbas, teto de R$ 400.000, reflexo inconsistente,
categoria indefinida e competência indefinida. Sem aprovação, não há PDF.
