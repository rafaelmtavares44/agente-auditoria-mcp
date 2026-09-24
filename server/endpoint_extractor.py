"""Extração estática de endpoints FastAPI (somente AST, sem importar o código).

Construções SUPORTADAS:
- `app = FastAPI(...)` e `router = APIRouter(prefix="/x", tags=[...])` em nível de módulo;
- decoradores `@app.get/post/put/patch/delete/head/options("/rota", ...)` e o mesmo com `router`;
- rota como 1º argumento posicional ou `path="..."`, desde que seja texto literal;
- argumentos do decorador: response_model, status_code, summary, description, tags, deprecated;
- parâmetros da função: tipo anotado, valor padrão, Query/Path/Body/Header/Cookie/Form/Depends;
- `app.include_router(router, prefix="/x")` no MESMO arquivo;
- modelos Pydantic (`class X(BaseModel)`) definidos no mesmo arquivo.

NÃO suportado (vira limitação no resultado): rotas montadas dinamicamente, `add_api_route`,
roteadores importados de outros arquivos, `Annotated[...]` complexos, middlewares e
dependências globais, respostas de erro/autenticação não declaradas.
"""

from __future__ import annotations

import ast
import re

from server.sanitizer import sanitize_text

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}
PARAM_SOURCES = {"Query": "query", "Path": "path", "Body": "body", "Header": "header",
                 "Cookie": "cookie", "Form": "form", "File": "form", "Depends": "dependency",
                 "Security": "dependency"}
SIMPLE_TYPES = {"str", "int", "float", "bool", "bytes", "datetime", "date", "UUID"}

LIMITATIONS = [
    "Análise estática: somente construções listadas como suportadas são reconhecidas.",
    "Respostas de erro, autenticação e cabeçalhos só aparecem se declarados explicitamente no código.",
    "Tipos de retorno sem response_model/anotação são desconhecidos.",
    "Roteadores definidos em outros arquivos não recebem prefixo de include_router.",
]


def _src(node: ast.AST | None) -> str | None:
    return None if node is None else ast.unparse(node)


def _const(node: ast.AST | None):
    return node.value if isinstance(node, ast.Constant) else None


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Call):
        f = node.func
        return f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
    return None


def _kw(call: ast.Call, name: str) -> ast.AST | None:
    return next((k.value for k in call.keywords if k.arg == name), None)


def _collect_models(tree: ast.Module) -> dict[str, list[dict]]:
    models: dict[str, list[dict]] = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and any(_src(b) in ("BaseModel", "pydantic.BaseModel") for b in node.bases):
            fields = []
            for stmt in node.body:
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                    fields.append({"name": stmt.target.id, "type": _src(stmt.annotation),
                                   "required": stmt.value is None,
                                   "default": sanitize_text(_src(stmt.value)) if stmt.value is not None else None})
            models[node.name] = fields
    return models


def _collect_apps(tree: ast.Module) -> dict[str, dict]:
    """Variáveis FastAPI/APIRouter e seus prefixos."""
    apps: dict[str, dict] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            kind = _call_name(node.value)
            if kind in ("FastAPI", "APIRouter"):
                prefix = _const(_kw(node.value, "prefix")) or ""
                tags = _const_list(_kw(node.value, "tags"))
                apps[node.targets[0].id] = {"kind": kind, "prefix": prefix, "tags": tags}
    # include_router no mesmo arquivo
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "include_router" and node.args and isinstance(node.args[0], ast.Name):
            name = node.args[0].id
            extra = _const(_kw(node, "prefix")) or ""
            if name in apps and extra:
                apps[name]["prefix"] = extra + apps[name]["prefix"]
    return apps


def _const_list(node: ast.AST | None) -> list:
    if isinstance(node, (ast.List, ast.Tuple)):
        return [e.value for e in node.elts if isinstance(e, ast.Constant)]
    return []


def _params(fn: ast.FunctionDef | ast.AsyncFunctionDef, route: str, models: dict) -> list[dict]:
    path_names = set(re.findall(r"{(\w+)(?::\w+)?}", route))
    args = fn.args.args + fn.args.kwonlyargs
    defaults: list[ast.AST | None] = [None] * (len(fn.args.args) - len(fn.args.defaults)) + list(fn.args.defaults)
    defaults += list(fn.args.kw_defaults)
    result = []
    for arg, default in zip(args, defaults):
        if arg.arg in ("self", "cls"):
            continue
        annotation = _src(arg.annotation)
        marker = _call_name(default) if isinstance(default, ast.Call) else None
        if marker in PARAM_SOURCES:
            location, how = PARAM_SOURCES[marker], "explicit"
        elif arg.arg in path_names:
            location, how = "path", "inferred"
        elif annotation and annotation.split("[")[0] in models:
            location, how = "body", "inferred"
        elif annotation is None or annotation.split("[")[0].split("|")[0].strip() in SIMPLE_TYPES | {"list", "Optional"}:
            location, how = "query", "inferred"
        else:
            location, how = "unknown", "inferred"
        if marker in PARAM_SOURCES and default.args:
            first = default.args[0]
            required = isinstance(first, ast.Constant) and first.value is Ellipsis
        else:
            required = default is None
        result.append({
            "name": arg.arg, "location": location, "location_source": how,
            "type": annotation, "required": required,
            "default": sanitize_text(_src(default)) if default is not None else None,
        })
    return result


def extract_endpoints(source: str, rel_path: str) -> dict:
    tree = ast.parse(source, filename=rel_path)
    models = _collect_models(tree)
    apps = _collect_apps(tree)
    endpoints, unsupported = [], []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)
                    and dec.func.attr in HTTP_METHODS and isinstance(dec.func.value, ast.Name)):
                continue
            owner = dec.func.value.id
            if owner not in apps:
                unsupported.append({"line": dec.lineno, "reason": f"objeto '{owner}' não é FastAPI/APIRouter conhecido no arquivo"})
                continue
            path_node = dec.args[0] if dec.args else _kw(dec, "path")
            path = _const(path_node)
            if not isinstance(path, str):
                unsupported.append({"line": dec.lineno, "reason": "rota não é texto literal"})
                continue
            full_path = apps[owner]["prefix"] + path
            docstring = ast.get_docstring(node)
            response_model = _src(_kw(dec, "response_model"))
            returns = _src(node.returns)
            params = _params(node, full_path, models)
            summary = _const(_kw(dec, "summary"))

            gaps = []
            if not docstring and not summary and not _kw(dec, "description"):
                gaps.append("sem docstring, summary ou description")
            if not response_model and not returns:
                gaps.append("tipo de resposta não declarado (sem response_model nem anotação de retorno)")
            untyped = [p["name"] for p in params if p["type"] is None and p["location"] != "dependency"]
            if untyped:
                gaps.append("parâmetros sem tipo: " + ", ".join(untyped))

            endpoints.append({
                "method": dec.func.attr.upper(),
                "path": full_path,
                "function": node.name,
                "is_async": isinstance(node, ast.AsyncFunctionDef),
                "file": rel_path,
                "line": node.lineno,
                "summary": sanitize_text(summary) if summary else None,
                "docstring": sanitize_text(docstring)[:500] if docstring else None,
                "tags": _const_list(_kw(dec, "tags")) or apps[owner]["tags"],
                "status_code": _const(_kw(dec, "status_code")),
                "response_model": response_model,
                "return_annotation": returns,
                "deprecated": _const(_kw(dec, "deprecated")) is True,
                "parameters": params,
                "documentation_gaps": gaps,
            })

    endpoints.sort(key=lambda e: e["line"])
    return {"file": rel_path, "endpoints": endpoints, "models": models,
            "unsupported": unsupported, "limitations": LIMITATIONS}
