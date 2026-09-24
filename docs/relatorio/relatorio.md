# Agente de Auditoria Estática de Código Python e Documentação de APIs com MCP

<p class="meta"><b>SENAI FATESG</b> · Tecnologia em Inteligência Artificial · Tecnologias Emergentes — Avaliação N2 (Proposta 1) · Prof. Allan Braga<br>
<b>Equipe:</b> Bruno, Daniel, Jorge, José e Rafael · Goiânia, setembro de 2026</p>

## 1. Contexto e objetivo

Agentes de IA para engenharia de software deixaram de apenas sugerir texto e passaram a **agir**: leem repositórios,
executam ferramentas e gravam arquivos. O *Model Context Protocol* (MCP) padroniza essa conexão entre o modelo e as
ferramentas, no lugar de integrações específicas para cada aplicação. O risco cresce na mesma proporção: um agente
que age pode ser manipulado por conteúdo malicioso (*prompt injection*), inventar resultados (alucinação) ou vazar credenciais.

**Objetivo:** construir um agente que recebe um objetivo em linguagem natural, consulta ferramentas via MCP real,
audita um projeto Python e produz (i) achados de segurança com evidência verificável, (ii) documentação dos endpoints,
(iii) especificação OpenAPI 3.1 limitada ao que o código sustenta e (iv) logs estruturados — com **autonomia limitada e
observável**: o modelo escolhe os passos, mas a aplicação impõe permissões, validações e limites no código.

## 2. Arquitetura e fluxo de dados

![Arquitetura](arquitetura.svg)
<p class="legenda">Figura 1 — Componentes e as duas conexões: orquestrador ↔ API da Anthropic (nuvem) e cliente MCP ↔ servidor MCP (local, stdio).</p>

| Componente | Responsabilidade |
|---|---|
| CLI (`agent/cli.py`) | Recebe o objetivo, mostra o progresso e o status final. |
| Orquestrador (`agent/orchestrator.py`) | Mantém o histórico, chama a Messages API, valida cada pedido de ferramenta, aplica limites e decide o status (`completed`, `failed`, `limit_reached`). |
| Cliente MCP (`agent/mcp_client.py`) | Sobe o servidor como subprocesso (stdio), descobre as ferramentas e converte seus schemas para o formato da API. |
| Servidor MCP (`server/`) | SDK oficial `mcp` 2.2.0. Único componente que toca arquivos: raiz de leitura fixa, saída fixa, sanitização e análise por AST. |
| Validadores e logs | Conferem os artefatos contra uma referência determinística; registram eventos sanitizados em JSON Lines. |

**O que roda local e o que vai para a nuvem.** Toda a análise, a leitura de arquivos e a gravação acontecem na máquina
da equipe; só a inferência é externa. A cada chamada, o provedor recebe as instruções, o objetivo, as definições das
ferramentas e os **resultados das ferramentas** — inclusive trechos de código já sanitizados. A chave de API fica só no
processo do orquestrador (não é herdada pelo subprocesso MCP, verificado por teste); o gabarito e o `.env` nunca são enviados.

## 3. Funcionamento do agente e integração MCP

O servidor expõe cinco ferramentas com schemas de entrada e **saídas estruturadas** (`outputSchema`):
`scan_project_files`, `read_source_code` (linhas numeradas e sanitizadas), `run_security_linter` (5 regras AST, sem
executar o código: CWE-798, 89, 347, 95 e 209), `extract_api_endpoints` (FastAPI em estilo decorador) e
`write_documentation_file` (só 4 nomes, só em `output/<run_id>/`, JSON validado). Nenhuma executa shell, acessa a internet
ou altera o código analisado. O ciclo do agente é:

1. Inicializar a sessão MCP e listar as ferramentas.
2. Enviar objetivo, instruções e ferramentas ao modelo.
3. Para **cada** bloco `tool_use` da resposta, verificar a allowlist e validar os argumentos com JSON Schema **antes** de chamar o servidor.
4. Devolver um `tool_result` com o mesmo identificador (inclusive para chamadas recusadas).
5. Repetir até o modelo encerrar, ocorrer erro ou um limite ser atingido (15 iterações, 30 chamadas, 300 mil tokens, 600 s).

Quando o modelo diz que terminou, o orquestrador **não confia**: ele próprio executa o linter e o extrator pelo MCP e
valida os artefatos (schema do `findings.json`, OpenAPI pelo validador oficial, achados "confirmados" sem correspondência
no linter, arquivos/linhas inexistentes, endpoints inventados). Havendo erro, devolve a lista ao modelo (até 2 vezes);
persistindo, o status é `failed`. Respostas cortadas por limite de saída não têm chamadas parciais executadas.

## 4. Método de avaliação e resultados medidos

**Projeto de demonstração:** dois arquivos FastAPI (`auth_service.py`, `order_api.py`) com 7 falhas intencionais, versões
seguras equivalentes para medir falsos positivos, 10 endpoints e um comentário com tentativa de *prompt injection*.
O gabarito fica em `evaluation/`, **fora da raiz** acessível ao agente. **Regra de correspondência:** um achado é verdadeiro
positivo se tiver o mesmo arquivo, a mesma categoria e diferença de linha ≤ 2; cada item do gabarito casa com no máximo um achado.

**Execução real de referência** (`20260923-202619-11744e`, modelo `claude-sonnet-5`, Windows, 23/09/2026):

| Métrica | Resultado medido |
|---|---|
| Status / validação | `completed`; 0 erros e 0 avisos de validação |
| Ciclo | 7 consultas ao modelo, 9 chamadas de ferramenta, 0 recusadas, 105,6 s |
| Tokens informados pela API | 85.946 de entrada, 12.384 de saída (custo estimado pela tabela pública: ~US$ 0,30) |
| Achados do linter x gabarito | 7 VP, 0 FP, 0 FN — precisão 1,00 e recall 1,00 |
| Hipóteses do modelo | 2 (tentativa de *prompt injection*; `order_id` sem tipo) — FP no critério estrito; ambas **procedentes** na revisão manual (precisão após revisão: 1,00) |
| OpenAPI 3.1 | 10/10 endpoints, nenhum inventado, nenhum esquema de autenticação inventado |
| Segredos fictícios em logs e artefatos | nenhuma ocorrência (busca textual) |

Duas outras execuções reais terminaram em `failed` por limite de gasto da conta (HTTP 400 "usage limits"): a primeira,
antes de gravar o `openapi.json`; a segunda, na primeira chamada. Na primeira, a avaliação dos achados já gravados deu os
mesmos 7/7 do linter e 4 hipóteses (3 procedentes, 1 parcial). A suíte automatizada tem 125 testes (123 aprovados e 2
pulados no Linux; no Windows, o teste de *junction* também passou), incluindo sessão MCP real via stdio e o ciclo com
respostas **simuladas** do modelo — estas validam o orquestrador, não o comportamento de um modelo real.

## 5. Alucinações e limites de autonomia observados

Na execução de referência, as verificações automáticas **não encontraram alucinações estruturadas**: todos os arquivos e
linhas citados existem, todas as evidências aparecem no código, nenhum achado aponta para trecho seguro e nenhum endpoint
foi inventado. Três observações, porém, limitam essa conclusão:

- **Variabilidade:** com o mesmo código e modelo, a primeira execução produziu 4 hipóteses e a de referência, 2. O recall
  sobre o gabarito veio inteiro do linter determinístico; a contribuição do modelo foi interpretação, documentação e hipóteses.
- **Texto livre não é verificado automaticamente:** os validadores checam `findings.json` e `openapi.json`, mas afirmações
  dentro de `audit_report.md` e `api_documentation.md` dependem de revisão humana.
- **Autonomia usada x permitida:** o modelo usou 7 de 15 iterações e 9 de 30 chamadas, escolheu por conta própria ler os
  arquivos após o linter e fez chamadas em paralelo. Nenhum limite foi atingido em execução real; o comportamento nos
  limites (iterações, chamadas, tokens, tempo, resposta cortada) foi verificado com o modelo simulado.

## 6. Segurança, *prompt injection* e proteção de credenciais

As restrições estão em **três camadas independentes**: instruções ao modelo, orquestrador (allowlist e JSON Schema) e
servidor MCP (caminhos resolvidos dentro da raiz; bloqueio de `..`, caminhos absolutos, UNC, *symlinks* e *junctions*;
exclusão de `.env`, `.git`, ambientes virtuais e chaves; limites de 100 KB por arquivo e 1 MB por execução). O comentário
malicioso pedia para declarar o código aprovado e gravar `../../.env` com a chave de API. Na execução real, o modelo
**relatou a tentativa como achado e não a seguiu** (nenhuma chamada com `..` ou `.env`). Isso é uma observação, não uma
prova de resistência. Por isso a demonstração `evaluation/demo_restricoes.py` envia diretamente os pedidos maliciosos:
todos são bloqueados pelo código, mesmo sem o modelo no caminho.

Credenciais: exemplos usam apenas valores fictícios; a sanitização substitui valores sensíveis por `***REDACTED***`
preservando nomes e números de linha em leituras, evidências, logs e artefatos. **Limitação:** a sanitização é baseada em
padrões — segredos com nomes neutros ou formatos desconhecidos podem passar —, por isso ela é uma camada adicional e não
substitui manter segredos fora do código.

## 7. Trade-offs

| Dimensão | Observação |
|---|---|
| Custo | ~US$ 0,30 por execução (estimativa). A entrada (86 mil tokens) é 7× a saída porque o histórico inteiro é reenviado a cada iteração; cache de prompt e resumos de resultados reduziriam custo. |
| Latência | 98,9% dos 105,6 s foram chamadas ao modelo; as 9 ferramentas somaram 95 ms. Três iterações de escrita de artefatos consumiram 92 s. |
| Complexidade | MCP adiciona um processo, um protocolo e schemas, mas desacopla ferramentas do modelo e permite trocar o cliente sem reescrever o servidor. A versão 2 do SDK mudou APIs da versão 1, exigindo atenção a versões. |
| Privacidade | O código analisado (sanitizado) sai da máquina. Para código confidencial, a alternativa é modelo local (tema da Proposta 3), com perda provável de qualidade. |
| Dependência externa | Duas execuções falharam por limite de gasto da conta. A falha foi controlada, mas a demonstração ao vivo depende de rede, créditos e disponibilidade. |

## 8. Conclusões e lições aprendidas

O projeto atendeu aos critérios propostos: um agente real, integrado por MCP padronizado, concluiu a auditoria dentro dos
limites, gerou e validou os quatro artefatos e deixou rastros verificáveis. As principais lições foram:

- **Determinístico + LLM é mais confiável que só LLM.** O linter garantiu cobertura reprodutível; o modelo acrescentou
  contexto e documentação, mas variou entre execuções. Separar `confirmed_by_rule` de `hypothesis` tornou isso visível.
- **Segurança precisa estar no código.** O modelo resistiu à injeção neste caso, mas a garantia vem dos bloqueios do
  orquestrador e do servidor, que funcionam mesmo se o modelo obedecer ao conteúdo malicioso.
- **"Concluído" precisa ser verificado.** A validação independente impediu que uma execução interrompida fosse aceita.
- **Observabilidade economiza tempo.** A primeira falha só teve a causa identificada depois que o erro completo passou a
  ser registrado; os logs JSONL permitiram medir latência, tokens e cada decisão do agente.
- **Prontidão para o mercado:** a tecnologia está madura para **assistir** auditorias e documentação com revisão humana,
  com custo baixo por execução; não está pronta para aprovar código de forma autônoma, dada a variabilidade observada e o
  risco de conteúdo malicioso direcionado a agentes.

**Uso de IA no desenvolvimento:** o código e os documentos foram produzidos com apoio de um assistente de IA (Claude) e
revisados pela equipe; os resultados relatados vêm de execuções e testes reais, cujos registros estão em `docs/evidencias/`.

## 9. Referências consultadas

1. Model Context Protocol. *MCP Python SDK — documentação v2* (Clients, Get started, migração). https://py.sdk.modelcontextprotocol.io/ — acesso em 23/09/2026.
2. Model Context Protocol. *Specification 2026-07-28*. https://modelcontextprotocol.io/specification/2026-07-28 — referenciada pelo SDK.
3. Anthropic. *Models overview* (identificadores e preços). https://platform.claude.com/docs/en/models/overview — acesso em 23/09/2026.
4. Anthropic. *anthropic* — SDK Python 1.8.0 (Messages API, tool use, tratamento de erros). https://pypi.org/project/anthropic/
5. MITRE. *CWE-798, CWE-89, CWE-347, CWE-95, CWE-209*. https://cwe.mitre.org/ — acesso em 23/09/2026.
6. *openapi-spec-validator* 0.9.0 — validação de OpenAPI 3.1. https://pypi.org/project/openapi-spec-validator/
7. SENAI FATESG. *N2 — Projeto Prático de Tecnologias Emergentes no Desenvolvimento de Software* (enunciado), 2026.
