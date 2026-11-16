"""通过 MaiBot 原生 WebUI 接口保存模型与任务，保存后由宿主热重载。"""
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx

try:
    from .chatgpt_maibot import CLIENT_TYPE
    from .chatgpt_maibot.errors import PluginError, redact_credentials
except ImportError:
    from chatgpt_maibot import CLIENT_TYPE
    from chatgpt_maibot.errors import PluginError, redact_credentials

EFFORTS = ("", "none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra")
TASK_LABELS = {"replyer": "聊天回复", "planner": "行为规划", "utils": "辅助处理", "utils_small": "轻量辅助", "fast_model": "快速处理", "vlm": "图片理解", "memory": "记忆整理", "learner": "学习", "emoji": "表情理解"}
EXCLUDED_TASKS = {"embedding", "image_embedding", "voice", "web_search", "rerank"}


def reasoning_params(effort):
    if effort not in EFFORTS:
        raise PluginError("请选择列表中的推理强度。")
    return {"reasoning": {"effort": effort}} if effort else {}


def model_entry(model, name, provider, effort):
    return {"model_identifier": model, "name": name, "api_provider": provider,
            "model_type": "llm", "visual": True, "send_temperature": False,
            "price_in": 0.0, "price_out": 0.0, "extra_params": reasoning_params(effort)}


def add_model(config, model, effort, timeout):
    providers = config.setdefault("api_providers", [])
    oauth_names = {p["name"] for p in providers if p.get("client_type") == CLIENT_TYPE}
    existing = next((m for m in config.get("models", []) if m.get("api_provider") in oauth_names and m.get("model_identifier") == model), None)
    provider = next((p for p in providers if p["name"] == existing["api_provider"]), None) if existing else next((p for p in providers if p.get("client_type") == CLIENT_TYPE), None)
    if provider is None:
        names = {p["name"] for p in providers}
        name = unique_name("ChatGPT-OAuth", names)
        provider = {"name": name, "base_url": "https://api.openai.com/v1", "api_key": "",
                    "auth_type": "none", "client_type": CLIENT_TYPE, "max_retry": 0,
                    "timeout": timeout, "retry_interval": 4}
        providers.append(provider)
    models = config.setdefault("models", [])
    item = next((m for m in models if m.get("api_provider") == provider["name"] and m.get("model_identifier") == model), None)
    if item is None:
        name = unique_name("chatgpt-" + model, {m["name"] for m in models})
        item = model_entry(model, name, provider["name"], effort)
        models.append(item)
    else:
        extra = item.setdefault("extra_params", {})
        reasoning = dict(extra.pop("reasoning", {}))
        if isinstance(extra.get("body"), dict):
            reasoning.update(extra["body"].pop("reasoning", {}))
        reasoning.pop("effort", None)
        if effort:
            reasoning.update(reasoning_params(effort)["reasoning"])
        if reasoning:
            extra["reasoning"] = reasoning
    return item["name"]


def unique_name(base, names):
    name, index = base, 2
    while name in names:
        name = f"{base}-{index}"
        index += 1
    return name


def catalog(config):
    providers = {p["name"] for p in config.get("api_providers", []) if p.get("client_type") == CLIENT_TYPE}
    return {"models": [{"name": m["name"], "model_identifier": m["model_identifier"], "extra_params": reasoning_params(m.get("extra_params", {}).get("body", {}).get("reasoning", {}).get("effort") or m.get("extra_params", {}).get("reasoning", {}).get("effort", ""))} for m in config.get("models", []) if m.get("api_provider") in providers],
            "tasks": [{"id": key, "label": TASK_LABELS.get(key, key), "models": task.get("model_list", [])}
                      for key, task in config.get("model_task_config", {}).items()
                      if key not in EXCLUDED_TASKS and isinstance(task, dict) and "model_list" in task]}


def assign_tasks(config, model_name, tasks):
    current = catalog(config)
    if model_name not in {m["name"] for m in current["models"]}:
        raise PluginError("请先将这个模型添加到 MaiBot。")
    allowed = {t["id"] for t in current["tasks"]}
    if not tasks or any(t not in allowed for t in tasks):
        raise PluginError("请选择当前列表中的聊天模型任务。")
    for task in tasks:
        config["model_task_config"][task]["model_list"] = [model_name]


class HostModels:
    def __init__(self, settings):
        self.settings = settings

    @asynccontextmanager
    async def connection(self):
        base = self.settings.base_url.rstrip("/")
        address = urlsplit(base)
        origin = f"{address.scheme}://{address.netloc}"
        token = self.settings.token
        if not token:
            if address.hostname not in {"localhost", "127.0.0.1", "::1"}:
                raise PluginError("请在高级设置填写目标 WebUI 的登录密码。")
            shared = os.environ.get("MAIBOT_SHARED_MODEL_CATALOG")
            path = Path(shared).parent / "webui.json" if shared else Path.cwd() / "host/webui.json"
            if not path.is_file():
                raise PluginError("未找到宿主登录凭据，请在高级设置填写 WebUI 登录密码。")
            token = json.loads(path.read_text("utf-8"))["access_token"]
        if "/api/host/bots/" not in base:
            if address.hostname not in {"localhost", "127.0.0.1", "::1"}:
                raise PluginError("远程 WebUI 地址请包含 /api/host/bots/目标BotID/proxy。")
            bot_id = json.loads(os.environ.get("MAIBOT_RUNTIME_CONTEXT", "{}" )).get("bot_id")
            if bot_id:
                base += "/api/host/bots/" + quote(bot_id, safe="") + "/proxy"
        async with httpx.AsyncClient(timeout=45, follow_redirects=False) as client:
            result = await self.request(client, "POST", origin + "/api/webui/auth/verify", json={"token": token})
            if not result.get("valid"):
                raise PluginError("MaiBot 登录失败，请检查高级设置中的 WebUI 密码。")
            try:
                yield client, base + "/api/webui/config/model"
            finally:
                await client.post(origin + "/api/webui/auth/logout")

    async def request(self, client, method, url, **kwargs):
        try:
            response = await client.request(method, url, **kwargs)
        except httpx.HTTPError:
            raise PluginError("MaiBot 配置接口连接失败，请检查宿主地址和网络。") from None
        credentials = {"token": getattr(self.settings, "token", ""), "config": kwargs.get("json")}
        if response.is_error:
            try:
                detail = redact_credentials(response.json().get("detail", ""), credentials)
            except ValueError:
                detail = ""
            raise PluginError(f"MaiBot 配置接口返回 {response.status_code}：{detail or '请检查宿主日志'}")
        result = response.json()
        return redact_credentials(result, credentials) if method != "GET" else result

    async def read(self):
        async with self.connection() as (client, url):
            return catalog((await self.request(client, "GET", url))["config"])

    async def save(self, change):
        async with self.connection() as (client, url):
            config = (await self.request(client, "GET", url))["config"]
            revision = config.get("_shared_catalog", {}).get("revision")
            value = change(config)
            result = await self.request(client, "POST", url, json=config,
                                        params={"catalog_revision": revision} if revision is not None else {})
            if not result.get("success"):
                raise PluginError(result.get("message") or "MaiBot 配置保存失败。")
            return {"name": value, "message": "已保存，宿主已完成模型配置重载。", "warnings": result.get("warnings", [])}
