"""Teste OPCIONAL com a API REAL da Anthropic (gera custo).

Roda somente com:  RUN_REAL_API=1  +  ANTHROPIC_API_KEY  +  ANTHROPIC_MODEL.
Ele verifica que o ciclo funciona com um modelo real; não mede qualidade da auditoria
(isso é feito na etapa 4 contra o gabarito).
"""
import os

import pytest

from agent.config import AgentSettings
from agent.orchestrator import AnthropicBackend, AuditAgent

pytestmark = [
    pytest.mark.real_api,
    pytest.mark.skipif(os.environ.get("RUN_REAL_API") != "1",
                       reason="API real desativada (defina RUN_REAL_API=1 e configure a chave)"),
]


@pytest.mark.anyio
async def test_real_model_completes_audit(workspace):
    settings = AgentSettings.from_env(require_api_key=True)
    backend = AnthropicBackend(settings.api_key, settings.limits.max_retries)
    agent = AuditAgent(settings, backend, workspace / "legacy_sample", workspace / "output",
                       workspace / "logs", run_id="real_api_test")
    result = await agent.run("Faça a auditoria estática e documente a API, gerando os quatro artefatos.")
    print(f"\n[API REAL] status={result.status} iter={result.iterations} tools={result.tool_calls} "
          f"tokens_in={result.input_tokens} tokens_out={result.output_tokens} ms={result.duration_ms}")
    assert result.tool_calls > 0, "o modelo deveria ter pedido ferramentas"
    assert result.status == "completed", result.reason
