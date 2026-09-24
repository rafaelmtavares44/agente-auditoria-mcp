# Guia de execução — como rodar tudo no dia da apresentação

Passo a passo para quem vai operar o computador (sugestão: **Rafael**). Todos os comandos são do **Windows PowerShell**.
Quem for apenas assistir à demo também deve ler: se o operador travar, qualquer um assume.

---

## Parte 1 — Na véspera (uma vez só)

### 1.1 Se for usar OUTRO computador (ex.: da faculdade ou de um colega)

```powershell
cd $HOME\Desktop
git clone https://github.com/rafaelmtavares44/agente-auditoria-mcp.git
cd agente-auditoria-mcp
py -3.13 -m venv .venv          # ou -3.11 / -3.12, conforme "py -0" mostrar
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env                    # colar a chave em ANTHROPIC_API_KEY e usar ANTHROPIC_MODEL=claude-sonnet-5
```

> A chave **nunca** vai para o GitHub (o `.env` é ignorado). Leve-a num pendrive ou gerenciador de senhas, não em print.

No seu próprio computador, o projeto já está pronto: pule para 1.2.

### 1.2 Conferências

```powershell
Set-Location "C:\Users\rafae\OneDrive\Desktop\IA 4_Fatesg\tecnologias emergentes\trabalhon2\agente-auditoria-mcp"
.\.venv\Scripts\python.exe -m pytest                 # esperado: 0 failed
.\.venv\Scripts\python.exe -m agent.list_models      # o modelo configurado aparece com "<- configurado"
```

No **Console da Anthropic**: confira **saldo** (Billing) e **limite de gasto** (Settings → Limits). Cada execução custa ~US$ 0,30 (estimativa).

### 1.3 Gravar o plano B (obrigatório)

1. Abra a **Ferramenta de Captura** do Windows (`Win + Shift + R` grava a tela no Windows 11).
2. Grave a execução completa do passo 2.3 abaixo, do comando até `status: completed`.
3. Salve como `plano_b_execucao.mp4` na área de trabalho. **Não suba no GitHub** (arquivo grande).

---

## Parte 2 — No dia, 20 minutos antes

### 2.1 Abrir o PowerShell na pasta e criar atalhos

```powershell
Set-Location "C:\Users\rafae\OneDrive\Desktop\IA 4_Fatesg\tecnologias emergentes\trabalhon2\agente-auditoria-mcp"
$PY  = ".\.venv\Scripts\python.exe"
$RUN = "demo-" + (Get-Date -Format "HHmm")
$RUN          # mostra o nome da execução, ex.: demo-1930
```

`$PY` e `$RUN` são "apelidos" que valem **só nesta janela**. Se fechar o PowerShell, rode este bloco de novo.

### 2.2 Deixar legível no projetor

- Terminal: **`Ctrl` + `+`** várias vezes (ou `Ctrl` + roda do mouse) até o texto ficar grande.
- Maximize a janela. Tema escuro com letra clara costuma ler melhor no projetor.
- Abra em abas do navegador: o **repositório no GitHub**, o **PDF do relatório** e os **slides**.
- Abra no Bloco de Notas ou VS Code: `legacy_sample\order_api.py` (José vai mostrar as linhas 22–25).

### 2.3 Ensaio rápido (opcional, gasta ~US$ 0,30)

```powershell
& $PY -m agent.cli "Audite o projeto e documente a API" --run-id "ensaio-$RUN"
```

Se terminar em `completed`, a rede, a chave e o saldo estão ok.

---

## Parte 3 — Durante a apresentação (na ordem dos slides)

### Bloco do Rafael — execução real do agente (slide "Demo ao vivo")

```powershell
& $PY -m agent.cli "Audite o projeto e documente a API" --run-id $RUN
```

**O que aparece na tela, e o que significa:**

| Linha no terminal | O que dizer |
|---|---|
| `MCP conectado (stdio): 5 ferramentas` | "O servidor MCP subiu como subprocesso e anunciou as 5 ferramentas." |
| `[1] consultando o modelo...` | "Mandamos o objetivo para o modelo na nuvem." |
| `-> scan_project_files()` / `-> run_security_linter()` | "O modelo escolheu a ferramenta; o orquestrador validou e o servidor executou." |
| `ok em 18 ms` | "A ferramenta é rápida; o tempo está no modelo." |
| `-> write_documentation_file(findings.json)` | "Agora ele grava os artefatos — só os 4 nomes permitidos." |
| `validação: OK (0 erros, 0 avisos)` | "O orquestrador conferiu tudo por conta própria antes de aceitar." |
| `status: completed` | "Concluído dentro dos limites." |

Leva **~2 minutos**. Enquanto roda, **volte aos slides** e explique o ciclo e o código; depois retorne ao terminal para mostrar o final.

### Bloco do Jorge — logs e artefatos da execução que acabou de rodar

```powershell
# Linha do tempo: cada pedido (tool_call) e sua resposta (tool_result) com o MESMO call_id
Get-Content "logs\$RUN.jsonl" -Encoding UTF8 | ForEach-Object { $_ | ConvertFrom-Json } |
  Where-Object event -in 'tool_call','tool_result' |
  Select-Object -First 6 seq, event, tool, call_id, is_error, duration_ms | Format-Table -AutoSize

# Achados: linter (ast_rule / confirmed_by_rule) x modelo (model / hypothesis)
(Get-Content "output\$RUN\findings.json" -Raw -Encoding UTF8 | ConvertFrom-Json).findings |
  Format-Table id, file, line, detection_source, status -AutoSize

# Avaliação contra o gabarito (precisão, recall, endpoints, prompt injection)
& $PY evaluation\evaluate.py $RUN --price-in 2 --price-out 10
```

Na saída da avaliação, aponte: a **tabela de achados** (linter 7/7), **"Endpoints inventados: nenhum"** e a seção **Prompt injection**.

### Bloco do José — restrições de segurança (não gasta API)

```powershell
& $PY -m evaluation.demo_restricoes
```

Leia em voz alta 3 ou 4 linhas: **"Ler o gabarito fora da raiz → BLOQUEADO pelo SERVIDOR MCP"**, **"Gravar ../../.env → BLOQUEADO"**,
**"Chamar ferramenta inexistente → BLOQUEADO pelo ORQUESTRADOR"** e, por fim, **"Pedido LEGÍTIMO → PERMITIDO"** (mostra que não é "bloquear tudo").

---

## Parte 4 — Se algo der errado

| Problema na hora | O que fazer (em 10 segundos) |
|---|---|
| `status: failed ... usage limits` ou erro de rede | Dizer: *"A API externa falhou — isso também é um resultado: o agente parou de forma controlada e registrou o motivo."* Em seguida, **plano B**. |
| Passou de 3 minutos sem terminar | `Ctrl + C` (o agente encerra o servidor MCP) e **plano B**. |
| `ModuleNotFoundError: server` | Você não está na pasta do projeto: rode de novo o `Set-Location` da Parte 2.1. |
| `$PY` ou `$RUN` "não reconhecido" | A janela foi fechada: rode de novo o bloco 2.1. |
| `Configuração inválida: ANTHROPIC_API_KEY` | O `.env` não está na pasta ou está sem a chave: `notepad .env`. |
| Texto pequeno no projetor | `Ctrl` + `+` no terminal. |

### Plano B (mostrar execução anterior)

1. Diga em voz alta: **"Vamos mostrar a execução gravada em 23/09/2026."**
2. Rode o vídeo `plano_b_execucao.mp4` **ou** abra a execução de referência:
   ```powershell
   $RUN = "20260923-202619-11744e"
   explorer "docs\evidencias\$RUN"
   notepad "docs\evidencias\$RUN\avaliacao.md"
   ```
3. Os comandos do Jorge funcionam com a execução de referência se trocar as pastas:
   `logs\$RUN.jsonl` → `docs\evidencias\$RUN\execucao.jsonl` e `output\$RUN\findings.json` → `docs\evidencias\$RUN\findings.json`.
4. A demo do José (`demo_restricoes`) **não depende da API**: ela sempre funciona.

---

## Resumo em uma tela (para colar num post-it)

```
Set-Location "...\agente-auditoria-mcp"
$PY = ".\.venv\Scripts\python.exe" ; $RUN = "demo-" + (Get-Date -Format "HHmm")
& $PY -m agent.cli "Audite o projeto e documente a API" --run-id $RUN     # Rafael
& $PY evaluation\evaluate.py $RUN --price-in 2 --price-out 10             # Jorge
& $PY -m evaluation.demo_restricoes                                       # José
Plano B: docs\evidencias\20260923-202619-11744e
```
