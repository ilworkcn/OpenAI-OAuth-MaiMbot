"""模型添加、原生保存协议、任务分配和推理强度。"""
import copy
import json
import tomllib
from types import SimpleNamespace

import httpx
import pytest

from chatgpt_maibot import CLIENT_TYPE
from chatgpt_maibot.errors import PluginError
from chatgpt_maibot.mapping import build_responses_body
from host_models import HostModels, add_model, assign_tasks, catalog, reasoning_params
from test_webui import plugin


def configuration():
    return {"api_providers": [{"name": "ChatGPT-OAuth", "client_type": "openai"}],
            "models": [{"name": "old", "api_provider": "ChatGPT-OAuth", "model_identifier": "other"}],
            "model_task_config": {"replyer": {"model_list": ["old"], "temperature": 0.7, "hard_timeout": 80},
                                  "planner": {"model_list": ["old"]}, "embedding": {"model_list": ["embed"]},
                                  "voice": {"model_list": ["voice"]}, "web_search": {"model_list": ["search"]}},
            "_shared_catalog": {"revision": "r1"}, "_warnings": []}


def test_add_update_and_assign_keep_existing_settings():
    config = configuration()
    before = copy.deepcopy(config)
    name = add_model(config, "test-model", "high", 240)
    assert config["api_providers"][0] == before["api_providers"][0]
    assert config["model_task_config"] == before["model_task_config"]
    assert config["api_providers"][1]["name"] == "ChatGPT-OAuth-2"
    model = config["models"][-1]
    model["extra_params"]["body"] = {"reasoning": {"effort": "low"}, "custom": True}
    assert add_model(config, "test-model", "medium", 240) == name
    assert len(config["models"]) == 2
    assert model["extra_params"] == {"reasoning": {"effort": "medium"}, "body": {"custom": True}}
    assign_tasks(config, name, ["replyer"])
    assert config["model_task_config"]["replyer"] == {"model_list": [name], "temperature": .7, "hard_timeout": 80}
    assert config["model_task_config"]["planner"] == before["model_task_config"]["planner"]
    assert {t["id"] for t in catalog(config)["tasks"]} == {"replyer", "planner"}
    with pytest.raises(PluginError):
        assign_tasks(config, name, ["embedding"])
    with pytest.raises(PluginError):
        assign_tasks(config, "missing", ["replyer"])
    add_model(config, "test-model", "", 240)
    assert "reasoning" not in model["extra_params"]


async def test_native_login_save_reload_protocol_and_logout(monkeypatch):
    config = configuration()
    calls = []
    def handler(request):
        calls.append(request)
        if request.url.path.endswith("auth/verify"):
            assert json.loads(request.content) == {"token": "test-password"}
            return httpx.Response(200, json={"valid": True}, headers={"Set-Cookie": "maibot_host_session_test=session; Path=/; HttpOnly"})
        assert "maibot_host_session_test=session" in request.headers.get("cookie", "")
        if request.url.path.endswith("auth/logout"):
            return httpx.Response(200, json={"success": True})
        assert request.url.path == "/api/host/bots/my-bot/proxy/api/webui/config/model"
        if request.method == "GET":
            return httpx.Response(200, json={"config": config})
        assert request.url.params["catalog_revision"] == "r1"
        saved = json.loads(request.content)
        assert saved["model_task_config"] == config["model_task_config"]
        assert saved["models"][-1]["extra_params"]["reasoning"]["effort"] == "high"
        return httpx.Response(200, json={"success": True, "warnings": ["宿主提示"]})
    client_type = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: client_type(transport=httpx.MockTransport(handler), **kwargs))
    monkeypatch.setenv("MAIBOT_RUNTIME_CONTEXT", '{"bot_id":"my-bot"}')
    host = HostModels(SimpleNamespace(base_url="http://127.0.0.1:8001", token="test-password"))
    result = await host.save(lambda c: add_model(c, "test-model", "high", 240))
    assert "重载" in result["message"] and result["warnings"] == ["宿主提示"]
    assert len(calls) == 4 and calls[-1].url.path.endswith("auth/logout")


@pytest.mark.parametrize("code,detail", [(409,"公共模型配置已改变"),(500,"模型配置已保存，但运行时热重载失败")])
async def test_host_errors_preserve_actual_result(code, detail):
    host = HostModels(None)
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(code,json={"detail":detail}))) as client:
        with pytest.raises(PluginError, match=detail):
            await host.request(client, "POST", "http://localhost/model")


async def test_reasoning_test_and_manual_config_agree(plugin, monkeypatch):
    plugin.models = [{"slug": "test-model"}]
    captured = []
    async def response(operation, request):
        captured.append(build_responses_body(request)[0])
        return {"content": "成功"}
    monkeypatch.setattr(plugin, "handle_llm_provider", response)
    await plugin.start_test("test-model", "high")
    await plugin.test_task
    assert captured[0]["reasoning"] == {"effort": "high"}
    manual = tomllib.loads((await plugin.example("test-model", "high"))["text"])
    assert manual["models"][0]["extra_params"]["reasoning"]["effort"] == "high"
    assert not reasoning_params("")
    with pytest.raises(PluginError):
        await plugin.start_test("test-model", "made-up")


def test_effort_change_keeps_reasoning_summary():
    config = configuration()
    add_model(config, "test-model", "high", 240)
    model = config["models"][-1]
    model["extra_params"]["reasoning"]["summary"] = "auto"
    add_model(config, "test-model", "", 240)
    assert model["extra_params"]["reasoning"] == {"summary": "auto"}


async def test_local_credentials_and_explicit_remote_target(monkeypatch, tmp_path):
    host_dir = tmp_path / "host"
    host_dir.mkdir()
    (host_dir / "webui.json").write_text('{"access_token":"local-password"}', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MAIBOT_SHARED_MODEL_CATALOG", raising=False)
    monkeypatch.setenv("MAIBOT_RUNTIME_CONTEXT", '{"bot_id":"local-bot"}')
    calls = []
    def handler(request):
        calls.append(request)
        if request.url.path.endswith("auth/verify"):
            assert json.loads(request.content)["token"] in {"local-password", "remote-password"}
            return httpx.Response(200,json={"valid":True},headers={"Set-Cookie":"session=sample; Path=/"})
        if request.url.path.endswith("auth/logout"):
            return httpx.Response(200,json={"success":True})
        return httpx.Response(200,json={"config":configuration()})
    client_type = httpx.AsyncClient
    monkeypatch.setattr(httpx,"AsyncClient",lambda **kw:client_type(transport=httpx.MockTransport(handler),**kw))
    await HostModels(SimpleNamespace(base_url="http://127.0.0.1:8001",token="")).read()
    assert "/bots/local-bot/proxy/" in calls[1].url.path
    calls.clear()
    await HostModels(SimpleNamespace(base_url="http://remote:8001/api/host/bots/remote-bot/proxy",token="remote-password")).read()
    assert "/bots/remote-bot/proxy/" in calls[1].url.path
    with pytest.raises(PluginError,match="登录密码"):
        await HostModels(SimpleNamespace(base_url="http://remote:8001",token="")).read()


async def test_remote_requires_explicit_bot():
    with pytest.raises(PluginError, match="目标BotID"):
        await HostModels(SimpleNamespace(base_url="http://remote:8001", token="remote-password")).read()
