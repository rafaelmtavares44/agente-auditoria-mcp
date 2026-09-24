"""Extração estática de endpoints FastAPI."""
import json

from server.endpoint_extractor import extract_endpoints

from .conftest import EXPECTED_FILE


def test_sample_endpoints_match_gabarito(tools):
    expected = json.loads(EXPECTED_FILE.read_text(encoding="utf-8"))["expected_endpoints"]
    result = tools.extract_api_endpoints()
    got = {(e.method, e.path, e.function): bool(e.documentation_gaps) for e in result.endpoints}
    want = {(e["method"], e["path"], e["function"]): e["documentation_gaps_expected"] for e in expected}
    assert got == want
    assert result.limitations


def test_parameters_and_models():
    src = '''
from fastapi import FastAPI, Query, Header
from pydantic import BaseModel
app = FastAPI()
class Item(BaseModel):
    name: str
    price: float = 0.0
@app.put("/items/{item_id}", response_model=Item, status_code=200, tags=["items"])
async def update(item_id: int, item: Item, q: str = Query(None), x_token: str = Header(...)) -> Item:
    """Atualiza."""
'''
    data = extract_endpoints(src, "m.py")
    ep = data["endpoints"][0]
    assert (ep["method"], ep["path"], ep["is_async"], ep["status_code"]) == ("PUT", "/items/{item_id}", True, 200)
    locs = {p["name"]: (p["location"], p["required"]) for p in ep["parameters"]}
    assert locs == {"item_id": ("path", True), "item": ("body", True),
                    "q": ("query", False), "x_token": ("header", True)}
    assert data["models"]["Item"][1] == {"name": "price", "type": "float", "required": False, "default": "0.0"}
    assert ep["documentation_gaps"] == []


def test_router_prefix_and_include_router():
    src = '''
from fastapi import FastAPI, APIRouter
app = FastAPI()
r = APIRouter(prefix="/v1")
@r.get("/ping")
def ping() -> dict:
    """ok"""
app.include_router(r, prefix="/api")
'''
    ep = extract_endpoints(src, "m.py")["endpoints"][0]
    assert ep["path"] == "/api/v1/ping"


def test_unsupported_constructions_are_reported():
    src = '''
from fastapi import FastAPI
app = FastAPI()
ROTA = "/dinamica"
@app.get(ROTA)
def a(): ...
@outro.get("/x")
def b(): ...
'''
    data = extract_endpoints(src, "m.py")
    assert data["endpoints"] == []
    assert len(data["unsupported"]) == 2


def test_extractor_does_not_invent_endpoints_from_plain_functions():
    assert extract_endpoints("def get(): pass\n", "m.py")["endpoints"] == []
