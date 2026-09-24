# Documentação da API (extraída estaticamente)

> Gerada a partir de análise estática de `auth_service.py` e `order_api.py`. Tudo que o código não declara explicitamente está marcado como **desconhecido**.

---

## auth_service.py — Router `/auth` (tags: auth)

### POST /auth/login
- **Função**: `login`
- **Parâmetros**: `payload` (body, `LoginRequest`, obrigatório)
- **Resposta declarada**: desconhecido (sem `response_model` nem anotação de retorno)
- **Comportamento observado no código**:
  - Monta SQL via concatenação de string com `payload.username` (vulnerável a SQL injection).
  - Gera JWT assinado com segredo fixado no código (`JWT_SECRET`).
  - Retorna `{"access_token": token}` em caso de sucesso; `HTTPException(401)` se usuário não encontrado.
- **Autenticação**: desconhecido/nenhuma (endpoint público de login).
- **Erros**: apenas 401 documentado via `HTTPException`; demais erros (ex.: banco indisponível) não tratados.
- **Melhorias sugeridas**: usar consulta parametrizada e segredo de ambiente (ver `login_safe` como referência); declarar `response_model=TokenResponse`.

### POST /auth/login/safe
- **Função**: `login_safe`
- **Summary**: "Login com consulta parametrizada"
- **Parâmetros**: `payload` (body, `LoginRequest`, obrigatório)
- **Resposta declarada**: `TokenResponse` (`access_token: str`, `token_type: str = "bearer"`)
- **Comportamento observado no código**: consulta SQL parametrizada; segredo lido de variável de ambiente (`JWT_SECRET_FROM_ENV`).
- **Autenticação**: nenhuma (endpoint de login).
- **Erros**: `HTTPException(401)` para credenciais inválidas.
- **Melhorias sugeridas**: nenhuma crítica; considerar rate limiting contra força bruta.

### GET /auth/me
- **Função**: `me`
- **Parâmetros**: `authorization` (header, `str`, obrigatório, via `Header(...)`)
- **Resposta declarada**: desconhecido (sem `response_model` nem anotação de retorno)
- **Comportamento observado no código**: decodifica JWT **sem verificar assinatura** (`read_token_unsafe`), permitindo forjar `sub` e se passar por qualquer usuário.
- **Autenticação**: header `Authorization: Bearer <token>` esperado, mas não validado corretamente.
- **Erros**: não tratados explicitamente (falha de decode pode propagar exceção não capturada).
- **Melhorias sugeridas**: usar `read_token_safe`; tratar exceções de decode com `HTTPException(401)`.

### GET /auth/me/safe
- **Função**: `me_safe`
- **Summary**: "Dados do usuário autenticado"
- **Parâmetros**: `authorization` (header, `str`, obrigatório)
- **Resposta declarada**: `dict` (sem schema Pydantic definido — retorno tipado como `dict` genérico)
- **Comportamento observado no código**: valida assinatura do JWT com `read_token_safe` antes de confiar nas claims.
- **Autenticação**: header `Authorization: Bearer <token>`, validado corretamente.
- **Erros**: não tratados explicitamente no endpoint (decode pode lançar exceção).
- **Melhorias sugeridas**: capturar exceções de `jwt.decode` e retornar `HTTPException(401)`.

---

## order_api.py — App FastAPI (sem prefixo/tags)

### GET /orders/{order_id}
- **Função**: `get_order`
- **Parâmetros**: `order_id` (path, **tipo não declarado**)
- **Resposta declarada**: desconhecido
- **Comportamento observado no código**: monta SQL via f-string com `order_id` (vulnerável a SQL injection); acesso a `row[0]`/`row[1]` sem checar se `row` é `None` (risco de erro 500 se pedido não existir).
- **Autenticação**: desconhecido/nenhuma.
- **Melhorias sugeridas**: declarar `order_id: int`, usar consulta parametrizada, tratar caso `row is None`.

### GET /orders
- **Função**: `list_orders`
- **Summary**: "Lista pedidos por status"
- **Parâmetros**: `status` (query, `str`, opcional, default `"open"`, `max_length=20`)
- **Resposta declarada**: `list[OrderOut]` (`id: int`, `status: str`)
- **Comportamento observado no código**: consulta parametrizada segura.
- **Autenticação**: desconhecido/nenhuma.
- **Melhorias sugeridas**: nenhuma crítica identificada.

### POST /orders/discount
- **Função**: `calculate_discount`
- **Parâmetros**: `payload` (body, `DiscountRequest` com campo `expression: str`)
- **Resposta declarada**: desconhecido
- **Comportamento observado no código**: executa `eval(payload.expression)` diretamente — permite execução de código arbitrário enviado pelo cliente.
- **Autenticação**: desconhecido/nenhuma.
- **Melhorias sugeridas**: substituir por `ast.literal_eval` restrito a números, como em `calculate_discount_safe`.

### POST /orders/discount/safe
- **Função**: `calculate_discount_safe`
- **Summary**: "Calcula desconto a partir de literal numérico"
- **Parâmetros**: `payload` (body, `DiscountRequest`)
- **Resposta declarada**: `dict` (sem schema Pydantic definido)
- **Comportamento observado no código**: usa `ast.literal_eval`, valida que o resultado é `int`/`float`, senão retorna `HTTPException(422)`.
- **Autenticação**: desconhecido/nenhuma.
- **Melhorias sugeridas**: considerar declarar um modelo de resposta explícito (`DiscountResponse`).

### POST /orders
- **Função**: `create_order`
- **Parâmetros**: `order` (body, `OrderIn`: `product_id: int`, `quantity: int`)
- **Status code declarado**: 201
- **Resposta declarada**: desconhecido (sem `response_model`)
- **Comportamento observado no código**: insere pedido via SQL parametrizado (seguro); em caso de exceção, **retorna mensagem de erro e stack trace completos ao cliente** (`str(e)` + `traceback.format_exc()`), vazando detalhes internos.
- **Autenticação**: desconhecido/nenhuma.
- **Erros**: exceções capturadas mas expostas ao cliente em vez de tratadas como erro 500 genérico.
- **Melhorias sugeridas**: logar erro internamente e retornar `HTTPException(500, "Erro interno")`, como feito em `delete_order`.

### DELETE /orders/{order_id}
- **Função**: `delete_order`
- **Summary**: "Remove um pedido"
- **Parâmetros**: `order_id` (path, `int`, obrigatório)
- **Status code declarado**: 204
- **Resposta declarada**: `None` (anotação de retorno) — sem schema, consistente com 204 No Content
- **Comportamento observado no código**: remove pedido via SQL parametrizado; em exceção, loga internamente (`logger.exception`) e retorna `HTTPException(500, "Erro interno")` sem vazar detalhes — **padrão correto de tratamento de erro**.
- **Autenticação**: desconhecido/nenhuma.
- **Melhorias sugeridas**: nenhuma crítica identificada.

---

## Observações Gerais
- **Autenticação/Autorização**: nenhum dos endpoints declara mecanismo de autenticação via `Depends`/`Security` do FastAPI — considerado **desconhecido** para todos, exceto a checagem manual de JWT em `/auth/me` e `/auth/me/safe`.
- **Formato de erro padrão**: não há um handler de exceção global declarado nos arquivos; cada endpoint trata erros de forma independente (ou não trata).
- **Modelos Pydantic identificados**: `LoginRequest`, `TokenResponse`, `OrderIn`, `OrderOut`, `DiscountRequest`.
