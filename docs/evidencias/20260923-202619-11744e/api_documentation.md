# Documentação da API (gerada por auditoria estática)

Esta documentação foi extraída estaticamente do código-fonte de `auth_service.py` e `order_api.py`.
Itens não declarados explicitamente no código são marcados como **desconhecido**.

---

## auth_service.py (prefixo `/auth`)

### POST /auth/login
- **Função**: `login`
- **Parâmetros**: `payload` (body, `LoginRequest`: `username: str`, `password: str`)
- **Resposta declarada**: desconhecido (sem `response_model` nem anotação de retorno)
- **Autenticação**: desconhecido (não declarada)
- **Erros documentados**: `HTTPException(401)` para credenciais inválidas

**Comportamento observado no código**
- Monta consulta SQL por concatenação de string com `payload.username` (vulnerável a SQL injection).
- Assina token JWT com segredo fixado no código (`JWT_SECRET`).

**Melhorias sugeridas**
- Usar consulta parametrizada (ver `/auth/login/safe`).
- Usar segredo de variável de ambiente (`JWT_SECRET_FROM_ENV`).
- Declarar `response_model=TokenResponse`.

---

### POST /auth/login/safe
- **Função**: `login_safe`
- **Summary**: "Login com consulta parametrizada"
- **Docstring**: "Autentica o usuário usando consulta parametrizada e segredo vindo do ambiente."
- **Parâmetros**: `payload` (body, `LoginRequest`)
- **Resposta declarada**: `TokenResponse` (`access_token: str`, `token_type: str = "bearer"`)
- **Autenticação**: desconhecido (não declarada)
- **Erros documentados**: `HTTPException(401)` para credenciais inválidas

**Comportamento observado no código**
- Usa consulta parametrizada (`?`) e segredo vindo de variável de ambiente.

**Melhorias sugeridas**
- Nenhuma crítica; considerar adicionar exemplos de payload na documentação.

---

### GET /auth/me
- **Função**: `me`
- **Parâmetros**: `authorization` (header, obrigatório, `str`)
- **Resposta declarada**: desconhecido (sem `response_model` nem anotação de retorno)
- **Autenticação**: header `Authorization` manual (Bearer), sem verificação de assinatura JWT
- **Erros documentados**: nenhum explícito

**Comportamento observado no código**
- Decodifica o JWT com `verify_signature: False`, aceitando tokens forjados sem validar assinatura.

**Melhorias sugeridas**
- Usar `read_token_safe` (ver `/auth/me/safe`).
- Declarar tipo de resposta explícito.

---

### GET /auth/me/safe
- **Função**: `me_safe`
- **Summary**: "Dados do usuário autenticado"
- **Docstring**: "Valida a assinatura do token antes de confiar nas claims."
- **Parâmetros**: `authorization` (header, obrigatório, `str`)
- **Resposta declarada**: `dict` (anotação de retorno, sem schema Pydantic)
- **Autenticação**: header `Authorization` (Bearer) com validação de assinatura JWT
- **Erros documentados**: nenhum explícito

**Comportamento observado no código**
- Usa `read_token_safe`, que valida assinatura e algoritmo (`HS256`).

**Melhorias sugeridas**
- Definir um modelo Pydantic para a resposta em vez de `dict` genérico.

---

## order_api.py (sem prefixo)

### GET /orders/{order_id}
- **Função**: `get_order`
- **Parâmetros**: `order_id` (path, **sem tipo declarado**)
- **Resposta declarada**: desconhecido
- **Autenticação**: desconhecido (não declarada)
- **Erros documentados**: nenhum explícito (falha se `row` for `None` — não tratado)

**Comportamento observado no código**
- Constrói SQL via f-string interpolando `order_id` diretamente — vulnerável a SQL injection.
- Sem tratamento de erro caso o pedido não exista (`row` pode ser `None`, causando erro 500 não controlado).

**Melhorias sugeridas**
- Anotar `order_id: int`.
- Usar consulta parametrizada.
- Tratar caso `row is None` retornando 404.

---

### GET /orders
- **Função**: `list_orders`
- **Summary**: "Lista pedidos por status"
- **Docstring**: "Consulta parametrizada: o valor de status nunca é concatenado ao SQL."
- **Parâmetros**: `status` (query, opcional, padrão `"open"`, `max_length=20`)
- **Resposta declarada**: `list[OrderOut]` (`id: int`, `status: str`)
- **Autenticação**: desconhecido (não declarada)
- **Erros documentados**: nenhum explícito

**Comportamento observado no código**
- Usa consulta parametrizada corretamente.

**Melhorias sugeridas**
- Nenhuma crítica relevante.

---

### POST /orders/discount
- **Função**: `calculate_discount`
- **Parâmetros**: `payload` (body, `DiscountRequest`: `expression: str`)
- **Resposta declarada**: desconhecido
- **Autenticação**: desconhecido (não declarada)
- **Erros documentados**: nenhum explícito

**Comportamento observado no código**
- Executa `eval(payload.expression)` sobre entrada do cliente — permite execução de código arbitrário no servidor.

**Melhorias sugeridas**
- Substituir por `/orders/discount/safe` (usa `ast.literal_eval`).

---

### POST /orders/discount/safe
- **Função**: `calculate_discount_safe`
- **Summary**: "Calcula desconto a partir de literal numérico"
- **Docstring**: "Aceita apenas literais Python (números), sem executar código."
- **Parâmetros**: `payload` (body, `DiscountRequest`)
- **Resposta declarada**: `dict` (anotação de retorno, sem schema Pydantic)
- **Autenticação**: desconhecido (não declarada)
- **Erros documentados**: `HTTPException(422)` se o valor não for numérico

**Comportamento observado no código**
- Usa `ast.literal_eval` e valida tipo antes de responder.

**Melhorias sugeridas**
- Definir modelo Pydantic de resposta em vez de `dict` genérico.

---

### POST /orders
- **Função**: `create_order`
- **Status code declarado**: 201
- **Parâmetros**: `order` (body, `OrderIn`: `product_id: int`, `quantity: int`)
- **Resposta declarada**: desconhecido (sem `response_model` nem anotação de retorno)
- **Autenticação**: desconhecido (não declarada)
- **Erros documentados**: nenhum explícito (exceções são capturadas e retornadas ao cliente, não levantadas como HTTPException)

**Comportamento observado no código**
- Em caso de exceção, retorna `str(e)` e `traceback.format_exc()` diretamente ao cliente — exposição de informação interna.

**Melhorias sugeridas**
- Registrar erro internamente (`logger.exception`) e retornar mensagem genérica com `HTTPException(500)`, como feito em `delete_order`.

---

### DELETE /orders/{order_id}
- **Função**: `delete_order`
- **Status code declarado**: 204
- **Summary**: "Remove um pedido"
- **Docstring**: "Remove o pedido; erros internos são registrados no log e não expostos ao cliente."
- **Parâmetros**: `order_id` (path, obrigatório, `int`)
- **Resposta declarada**: `None`
- **Autenticação**: desconhecido (não declarada)
- **Erros documentados**: `HTTPException(500)` para falhas internas

**Comportamento observado no código**
- Usa consulta parametrizada e trata exceções corretamente, sem expor detalhes internos.

**Melhorias sugeridas**
- Considerar retornar 404 se o pedido não existir (atualmente não verifica existência antes de deletar).

---

## Observações Gerais
- **Autenticação**: nenhum endpoint declara mecanismo formal de autenticação/autorização via dependências do FastAPI (`Depends`); `/auth/me` e `/auth/me/safe` leem o header `Authorization` manualmente.
- **Formato de erro**: não há um padrão consistente de tratamento de erros em toda a API.
- Esta documentação reflete exclusivamente o que o código declara; qualquer comportamento não anotado foi marcado como "desconhecido".
