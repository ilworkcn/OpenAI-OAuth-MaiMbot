"""通过原生模型适配器连接 ChatGPT，账号操作集中在 WebUI。"""
import asyncio
import json
import time
from contextlib import suppress
from typing import Any

import httpx
from maibot_sdk import API, LLMProvider, MaiBotPlugin

if __package__:
    from .config import OAuthConfig
    from .host_models import HostModels, reasoning_params, add_model, assign_tasks
    from .chatgpt_maibot import APP_NAME, CLIENT_TYPE, VERSION
    from .chatgpt_maibot.auth import OpenAIPlanAuth
    from .chatgpt_maibot.errors import PluginError
    from .chatgpt_maibot.provider import PlanProvider
    from .chatgpt_maibot.store import CredentialStore
else:
    from config import OAuthConfig
    from host_models import HostModels, reasoning_params, add_model, assign_tasks
    from chatgpt_maibot import APP_NAME, CLIENT_TYPE, VERSION
    from chatgpt_maibot.auth import OpenAIPlanAuth
    from chatgpt_maibot.errors import PluginError
    from chatgpt_maibot.provider import PlanProvider
    from chatgpt_maibot.store import CredentialStore


class OAuthPlugin(MaiBotPlugin):
    config_model = OAuthConfig

    def __init__(self):
        super().__init__()
        self.client = None
        self.auth = None
        self.provider = None
        self.login_report = None
        self.test_task = None

    async def on_load(self):
        self.applied_proxy = self.config.network.proxy_url
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(30, connect=15), follow_redirects=False, proxy=self.applied_proxy or None)
        self.store = CredentialStore(self.ctx.paths.data_dir)
        self.auth = OpenAIPlanAuth(self.store, self.client, self.config.advanced.oauth_timeout_seconds)
        self.provider = PlanProvider(self.auth, self.client, timeout_seconds=self.config.advanced.request_timeout_seconds)
        self.login = {"status": "idle", "message": "点击登录，将 ChatGPT 账号连接到麦麦。"}
        self.test = {"status": "idle"}
        self.models = []
        self.login_report = None
        self.test_task = None
        await self.auth.initialize()
        self.ctx.logger.info("%s 已加载，请在插件页面管理账号", APP_NAME)

    async def on_unload(self):
        if self.auth is not None:
            await self.auth.cancel_login()
        for task in (self.login_report, self.test_task):
            if task:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
        if self.client is not None:
            await self.client.aclose()

    async def on_config_update(self, scope, config_data, version):
        if scope == "self" and self.auth is not None:
            if self.config.network.proxy_url != self.applied_proxy:
                await self.on_unload()
                await self.on_load()
                return
            self.auth.timeout_seconds = self.config.advanced.oauth_timeout_seconds
            self.provider.timeout_seconds = self.config.advanced.request_timeout_seconds

    def get_webui_config_schema(self, **kwargs):
        schema = super().get_webui_config_schema(**kwargs)
        schema["sections"]["plugin"].update(title="模型连接", description="账号授权与模型测试请打开插件的「账号与模型」页面。")
        schema["sections"]["network"].update(title="OpenAI 网络", description="代理只用于访问 OpenAI；宿主模型配置接口仍使用内网连接。")
        schema["sections"]["advanced"].update(title="连接时间", description="默认值适合大多数部署，需要时再调整。", collapsed=True)
        schema["sections"]["host"].update(title="自动添加模型", description="使用宿主原生配置接口保存并重载。同机部署自动读取登录凭据。", collapsed=True)
        schema["layout"] = {"type": "tabs", "tabs": [
            {"id": "connection", "title": "模型连接", "sections": ["plugin", "network"], "order": 0},
            {"id": "advanced", "title": "高级设置", "sections": ["host", "advanced"], "order": 1}]}
        return schema

    @API("status", description="账号、授权进度与模型测试结果")
    async def status(self):
        return {"accounts": await self.auth.accounts(), "login": self.login, "models": self.models,
                "test": self.test, "enabled": self.config.plugin.enabled, "data_dir": str(self.ctx.paths.data_dir),
                "request_timeout": self.config.advanced.request_timeout_seconds}

    @API("login", description="开始 ChatGPT 授权")
    async def begin_login(self, new: bool = False, consent: bool = False):
        if self.test_task and not self.test_task.done():
            raise PluginError("模型测试正在运行，结束后再切换账号。")
        attempt = await self.auth.begin_login(new=new, consent=consent)
        self.login = {"status": "waiting", "url": attempt.url,
                      "expires_at": time.time() + self.auth.timeout_seconds,
                      "message": "打开授权链接，完成后将浏览器地址栏中的回调地址粘贴到下方。"}
        self.login_report = asyncio.create_task(self._watch_login(attempt.task))
        return self.login

    async def _watch_login(self, task):
        try:
            account = await task
            self.models = []
            self.login = {"status": "connected", "message": "账号已连接，可以读取模型列表。" if account["plan_enabled"] else "账号已登录。请点击「允许使用套餐」完成模型调用授权。"}
        except asyncio.CancelledError:
            self.login = {"status": "idle", "message": "本次授权已取消。"}
            raise
        except Exception as error:
            self.login = {"status": "error", "message": str(error)}
            self.ctx.logger.warning("ChatGPT 授权失败：%s", error)

    @API("callback", description="提交浏览器回调地址", timeout_ms=90000)
    async def callback(self, url: str):
        await self.auth.submit_callback(url)
        await self.login_report
        return {"message": self.login["message"]}

    @API("cancel", description="取消本次授权")
    async def cancel(self):
        await self.auth.cancel_login()
        if self.login_report:
            with suppress(asyncio.CancelledError):
                await self.login_report
        return {"message": "本次授权已取消。"}

    @API("account", description="切换、退出或删除账号记录", timeout_ms=90000)
    async def account(self, action: str, client_id: str):
        if self.test_task and not self.test_task.done():
            raise PluginError("模型测试正在运行，结束后再切换账号。")
        if action == "delete":
            await self.auth.delete(client_id)
            return {"message": "已删除这条账号记录。"}
        await self.cancel()
        if action == "switch":
            await self.auth.switch(client_id)
            message = "当前账号已切换，请重新读取模型列表。"
        elif action == "logout":
            confirmed = await self.auth.logout(client_id)
            message = "账号已退出。" if confirmed else "本机已退出。请在 ChatGPT 的用量设置中确认应用连接已断开。"
        else:
            raise PluginError("请选择切换账号、退出账号或删除记录。")
        self.models = []
        self.test = {"status": "idle"}
        return {"message": message}

    @API("resume", description="恢复套餐用量暂停后的模型调用")
    async def resume(self):
        await self.provider.resume()
        return {"message": "已恢复调用，可测试模型确认当前额度。"}

    @API("models", description="读取当前账号的模型", timeout_ms=90000)
    async def list_models(self):
        self.models = await self.provider.models()
        return {"models": self.models, "message": f"已读取 {len(self.models)} 个可用模型。"}

    @API("test", description="向所选模型发送一条测试消息")
    async def start_test(self, model: str, effort: str = ""):
        reasoning_params(effort)
        if not self.config.plugin.enabled:
            raise PluginError("请先在插件配置中启用模型连接。")
        if self.auth._login_task and not self.auth._login_task.done():
            raise PluginError("请先完成当前授权，再测试模型。")
        if self.test_task and not self.test_task.done():
            raise PluginError("模型测试正在运行，请稍等。")
        self.test = {"status": "running", "model": model, "started_at": time.time()}
        self.test_task = asyncio.create_task(self._test(model, effort))
        return {"message": "正在测试模型…"}

    async def _test(self, model, effort=""):
        started = time.monotonic()
        try:
            result = await self.handle_llm_provider("response", {"model_info": {"model_identifier": model, "extra_params": reasoning_params(effort)},
                "message_list": [{"role": "user", "content": "请只回复：麦麦，连接成功。"}]})
            self.test.update(status="success", text=result.get("content", ""), usage=result.get("usage", {}))
        except Exception as error:
            self.test.update(status="error", message=str(error))
        finally:
            self.test["seconds"] = round(time.monotonic() - started, 1)

    @API("example", description="生成所选模型的 MaiBot 配置片段")
    async def example(self, model: str, effort: str = ""):
        reasoning_params(effort)
        if model not in {item["slug"] for item in self.models}:
            raise PluginError("请先读取模型列表并选择一个模型。")
        quoted = json.dumps(model, ensure_ascii=False)
        timeout = self.config.advanced.request_timeout_seconds
        text = f'''[[api_providers]]
name = "ChatGPT-OAuth"
base_url = "https://api.openai.com/v1"
api_key = ""
auth_type = "none"
client_type = "{CLIENT_TYPE}"
max_retry = 0
timeout = {timeout}
retry_interval = 4

[[models]]
model_identifier = {quoted}
name = "chatgpt-oauth"
api_provider = "ChatGPT-OAuth"
model_type = "llm"
visual = true
send_temperature = false
price_in = 0.0
price_out = 0.0
price_periods = []

# 将下方模型名加入希望使用它的任务，例如 replyer 或 planner。
# 在现有任务中修改 model_list，保留其他任务设置。
# model_list = ["chatgpt-oauth"]
# hard_timeout = {timeout}.0
'''
        if effort:
            text += "\n[models.extra_params.reasoning]\neffort = " + json.dumps(effort) + "\n"
        return {"text": text}

    @API("host_models", description="读取已添加的模型和任务", timeout_ms=60000)
    async def host_models(self):
        return await HostModels(self.config.host).read()

    @API("add_model", description="添加模型并保存推理强度", timeout_ms=60000)
    async def add_to_host(self, model: str, effort: str = ""):
        reasoning_params(effort)
        if model not in {m["slug"] for m in self.models}:
            raise PluginError("请先读取账号模型列表并选择模型。")
        return await HostModels(self.config.host).save(lambda config: add_model(config, model, effort, self.config.advanced.request_timeout_seconds))

    @API("assign_tasks", description="将已添加的模型用于选中任务", timeout_ms=60000)
    async def assign_to_tasks(self, model_name: str, tasks: list[str]):
        return await HostModels(self.config.host).save(lambda config: assign_tasks(config, model_name, tasks))

    @LLMProvider(CLIENT_TYPE, name="ChatGPT 账号授权", description="使用已授权的 ChatGPT 账号调用模型", version=VERSION)
    async def handle_llm_provider(self, operation: str, request: dict[str, Any]):
        if not self.config.plugin.enabled:
            raise PluginError("模型连接已关闭，请在插件配置中开启。")
        if operation != "response":
            raise PluginError("该连接用于聊天和图片理解。语音转写与向量模型请使用对应的服务。")
        return await self.provider.response(request, enable_web_search=self.config.plugin.enable_web_search,
                                            enable_tool_controls=self.config.plugin.enable_tool_controls)


def create_plugin():
    return OAuthPlugin()
