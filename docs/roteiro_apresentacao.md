# Roteiro da apresentação — 15 minutos, 5 integrantes

**Equipe:** Bruno, Daniel, Jorge, José e Rafael.
A divisão abaixo é uma sugestão: ajustem para que cada um apresente a parte que domina melhor.
**Todos** devem conseguir explicar o ciclo do agente (seção "Perguntas prováveis"), porque a arguição avalia o domínio de cada integrante.

## Linha do tempo

Comandos do dia: [`guia_execucao_apresentacao.md`](guia_execucao_apresentacao.md).

| Tempo | Quem | Slides | Bloco |
|---|---|---|---|
| 0:00–2:00 | **Bruno** | 1–4 | Problema, MCP e objetivo |
| 2:00–4:30 | **Daniel** | 5–8 | Arquitetura, dados, ferramentas e código de uma ferramenta MCP |
| 4:30–8:00 | **Rafael** | 9–12 | **Execução real ao vivo** + ciclo do agente e código do orquestrador |
| 8:00–10:00 | **Jorge** | 13–14 | Logs, achados e avaliação da execução que acabou de rodar |
| 10:00–12:00 | **José** | 15–17 | Prompt injection, três camadas e `demo_restricoes` |
| 12:00–14:30 | **Bruno** e **Daniel** | 18–20 | Trade-offs, limitações e conclusões |
| 14:30–15:00 | Todos | 21 | Encerramento e perguntas |

> Dica para o bloco do Rafael: a execução leva ~2 minutos. Iniciem o comando logo no começo do bloco e narrem enquanto ele roda.
> Se passar de 3 minutos ou a API falhar, mudem para o **plano B** sem perder tempo.

## Comandos da demonstração (PowerShell, na pasta do projeto)

```powershell
# Bloco do Rafael — execução real (consome API)
& ".\.venv\Scripts\python.exe" -m agent.cli "Audite o projeto e documente a API"

# Bloco do Jorge — avaliação da execução recém-gerada (troque o run_id)
& ".\.venv\Scripts\python.exe" evaluation\evaluate.py <run_id> --price-in 2 --price-out 10

# Bloco do José — restrições de segurança (NÃO consome API)
& ".\.venv\Scripts\python.exe" -m evaluation.demo_restricoes
```

## Plano B (contingência)

Se a rede, a API ou o limite de gasto falharem durante a apresentação:

1. Dizer em voz alta: **"Esta é uma execução anterior, gravada em 23/09/2026"**.
2. Abrir `docs/evidencias/20260923-202619-11744e/` (artefatos, log e `avaliacao.md`).
3. Se possível, mostrar uma gravação de tela da execução real, também identificada como gravação.
4. A falha em si também serve de demonstração: o agente termina em `failed` com o motivo registrado (como nas execuções de 23/09).

## Checklist antes da apresentação

- [ ] `.env` com chave válida e `ANTHROPIC_MODEL=claude-sonnet-5`; saldo e limite de gasto conferidos no Console.
- [ ] `python -m pytest` passando no computador da apresentação.
- [ ] Uma execução de ensaio no mesmo dia (confirma rede e API).
- [ ] Terminal com **fonte grande** (Ctrl + roda do mouse) — no projetor o texto sempre parece menor.
- [ ] Arquivos já abertos em abas: `order_api.py` (linhas 22–25), `execucao.jsonl`, `findings.json`, `openapi.json`, `relatorio.pdf`.
- [ ] Gravação de tela da execução de referência pronta para o plano B.
- [ ] Confirmar com o professor o tamanho da equipe: o enunciado indica **3 a 4 integrantes**.

## Perguntas prováveis na arguição (todos devem saber responder)

| Pergunta | Resposta curta |
|---|---|
| O que o MCP resolve aqui? | Padroniza como o agente descobre e chama ferramentas; o servidor poderia ser usado por outro cliente MCP sem mudança. |
| Quem decide o que o agente faz? | O modelo escolhe a próxima ferramenta; o código decide se ela é permitida (allowlist, schema, `path_guard`) e quando parar (limites). |
| Por que não confiar quando o modelo diz "terminei"? | Porque ele pode errar ou alucinar: o orquestrador roda o linter/extrator de novo e valida os artefatos antes de marcar `completed`. |
| O que acontece se o modelo obedecer ao *prompt injection*? | Os pedidos maliciosos são bloqueados pelo servidor e pelo orquestrador — é o que a `demo_restricoes` mostra sem o modelo. |
| Que dados saem da máquina? | Instruções, objetivo, definições das ferramentas e resultados delas (trechos de código **sanitizados**). A chave não vai para o subprocesso MCP e o gabarito nunca é lido. |
| Qual a diferença entre `confirmed_by_rule` e `hypothesis`? | O primeiro foi detectado por regra AST determinística (padrão, não prova de exploração); o segundo é interpretação do modelo e precisa de revisão humana. |
| Por que precisão 0,78 no critério estrito e 1,00 após revisão? | O gabarito só lista as 7 falhas intencionais; as 2 hipóteses extras do modelo foram revisadas manualmente e consideradas procedentes. |
| Por que o custo é dominado pela entrada? | O histórico inteiro é reenviado a cada iteração (86 mil tokens de entrada × 12 mil de saída). |
| Onde está o gargalo de latência? | No modelo: 98,9% do tempo; as ferramentas somaram 95 ms. |
| Isso generaliza para qualquer projeto Python? | Não: o extrator cobre FastAPI em estilo decorador e o gabarito é pequeno (7 falhas, 10 endpoints). As métricas descrevem este exemplo. |
| Como o código analisado é executado? | Não é: só é lido e parseado com `ast`; nada é importado ou executado. |
