"""检查异常、配置回显和模型目录中的凭据。"""
import asyncio
import json
import httpx
import pytest
from types import SimpleNamespace
from test_webui import plugin
from host_models import HostModels, catalog
from chatgpt_maibot import CLIENT_TYPE
from chatgpt_maibot.errors import PluginError

async def test_unexpected_errors_hide_credentials(plugin, monkeypatch, caplog):
    secret = 'fake-sensitive-oauth-value'
    async def fail(*args, **kwargs):
        raise RuntimeError(secret)
    await plugin._watch_login(asyncio.create_task(fail()))
    monkeypatch.setattr(plugin, 'handle_llm_provider', fail)
    await plugin._test('test-model')
    assert secret not in json.dumps(await plugin.status()) + caplog.text
    assert 'RuntimeError' in plugin.test['message']

async def test_host_validation_hides_submitted_key():
    secret = 'fake-sensitive-provider-value'
    host = HostModels(SimpleNamespace(token='fake-host-password'))
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(400, json={'detail':[{'input':secret,'msg':'配置错误'}]}))) as client:
        with pytest.raises(PluginError) as result:
            await host.request(client,'POST','http://localhost/model',json={'api_providers':[{'api_key':secret}]})
    assert secret not in str(result.value)
    assert '配置错误' in str(result.value)

def test_catalog_only_returns_model_selection_fields():
    result = catalog({'api_providers':[{'name':'oauth','client_type':CLIENT_TYPE}], 'models':[{'name':'model','model_identifier':'model','api_provider':'oauth','extra_params':{'api_key':'fake-sensitive-value','reasoning':{'effort':'high'}}}]})
    assert 'fake-sensitive-value' not in json.dumps(result)
    assert result['models'][0]['extra_params']['reasoning']['effort'] == 'high'


def test_manifest_declares_page_capabilities():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "_manifest.json").read_text("utf-8"))
    pages = json.loads((root / "webui.json").read_text("utf-8"))
    assert set(pages["required_capabilities"]) <= set(manifest["capabilities"])
