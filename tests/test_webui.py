"""Docker 回调提交、原生配置表单和账号页面流程。"""
import asyncio
import json
import logging
import tomllib
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest
from conftest import ACCESS, CLIENT_ID, save_account
from chatgpt_maibot.errors import PluginError
from plugin import OAuthPlugin


@pytest.fixture
async def plugin(env, tmp_path):
    p = OAuthPlugin()
    p.set_plugin_config(p.get_default_config())
    p._set_context(SimpleNamespace(paths=SimpleNamespace(data_dir=str(tmp_path)), logger=logging.getLogger("oauth-test")))
    await p.on_load()
    await p.client.aclose()
    p.client, p.store, p.auth, p.provider = env.client, env.store, env.auth, env.provider
    yield p
    await p.on_unload()


def callback_url(env, url, **values):
    params = {k:v[0] for k,v in parse_qs(urlsplit(url).query).items()}
    env.state.nonce = params["nonce"]
    return params["redirect_uri"]+"?"+urlencode({"code":"fake-code", "state":params["state"], "client_id":CLIENT_ID, **values})


async def test_docker_paste_completes_login_and_survives_restart(plugin, env):
    login = await plugin.begin_login()
    url = callback_url(env, login["url"])
    result = await plugin.callback(url)
    assert "已连接" in result["message"]
    state = await plugin.status()
    assert state["login"]["status"] == "connected"
    assert state["accounts"]["accounts"][0]["connected"]
    assert ACCESS not in json.dumps(state) and "url" not in state["login"]
    assert env.store.account()["client_id"] == CLIENT_ID
    from chatgpt_maibot.store import CredentialStore
    assert CredentialStore(env.store.data_dir).account()["access_token"] == ACCESS
    assert not env.auth._server.is_serving()


async def test_bad_paste_can_be_corrected(plugin, env):
    login = await plugin.begin_login()
    wrong = callback_url(env, login["url"], state="other-login")
    with pytest.raises(PluginError, match="另一次"):
        await plugin.callback(wrong)
    assert plugin.login["status"] == "waiting" and not env.state.requests
    await plugin.callback(callback_url(env, login["url"]))
    with pytest.raises(PluginError, match="新的授权"):
        await plugin.callback(callback_url(env, login["url"]))


async def test_denial_timeout_and_cancel(plugin, env):
    login = await plugin.begin_login()
    with pytest.raises(PluginError):
        await plugin.callback(callback_url(env, login["url"], error="access_denied"))
    await plugin.login_report
    assert plugin.login["status"] == "error"
    env.auth.timeout_seconds = .02
    await plugin.begin_login()
    await plugin.login_report
    assert "超时" in plugin.login["message"]
    await plugin.begin_login()
    await plugin.cancel()
    assert plugin.login["status"] == "idle"


async def test_missing_plan_permission_shown(plugin, env):
    env.state.token_overrides["scope"] = "openid profile email"
    login = await plugin.begin_login()
    await plugin.callback(callback_url(env, login["url"]))
    state = await plugin.status()
    assert not state["accounts"]["accounts"][0]["plan_enabled"]
    assert "允许使用套餐" in state["login"]["message"]


async def test_models_test_and_copyable_toml(plugin, env):
    await save_account(env)
    result = await plugin.list_models()
    assert result["models"][0]["slug"] == "test-model"
    await plugin.start_test("test-model")
    await plugin.test_task
    assert plugin.test["status"] == "success" and plugin.test["text"] == "Hello"
    assert plugin.test["usage"] and plugin.test["seconds"] >= 0
    text = (await plugin.example("test-model"))["text"]
    cfg = tomllib.loads(text)
    assert cfg["api_providers"][0]["client_type"] == "openai_oauth_maimbot"
    assert cfg["api_providers"][0]["auth_type"] == "none"
    assert cfg["models"][0]["model_identifier"] == "test-model"
    assert ACCESS not in text


async def test_unknown_model_and_disabled_provider(plugin, env):
    await save_account(env)
    with pytest.raises(PluginError):
        await plugin.example("unknown")
    plugin.config.plugin.enabled = False
    with pytest.raises(PluginError, match="启用"):
        await plugin.start_test("test-model")
    with pytest.raises(PluginError, match="关闭"):
        await plugin.handle_llm_provider("response", {})


async def test_resume_and_logout_clear_ui_models(plugin, env):
    await save_account(env)
    await plugin.list_models()
    await plugin.provider._usage_pause(CLIENT_ID, paused=True)
    assert (await plugin.status())["accounts"]["accounts"][0]["usage_paused"]
    await plugin.resume()
    assert not env.store.account()["usage_paused"]
    await plugin.account("logout", CLIENT_ID)
    assert not env.store.account().get("access_token") and plugin.models == []


async def test_native_schema_and_manifest_bindings(plugin):
    schema = plugin.get_webui_config_schema()
    assert [t["title"] for t in schema["layout"]["tabs"]] == ["模型连接", "高级设置"]
    assert schema["sections"]["plugin"]["fields"]["enabled"]["label"] == "启用模型连接"
    manifest = json.loads(Path("_manifest.json").read_text("utf-8"))
    assert manifest["id"] == "ilworkcn.openai-oauth"
    page = json.loads(Path("webui.json").read_text("utf-8"))["pages"][0]
    assert Path(page["entry"]).is_file()
    for action in page["actions"].values():
        assert action["version"] == "1"
    assert plugin.get_default_config()["plugin"]["config_version"] == manifest["version"]
