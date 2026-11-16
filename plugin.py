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
    from .chatgpt_maibot import APP_NAME, CLIENT_TYPE, VERSION
    from .chatgpt_maibot.auth import OpenAIPlanAuth
    from .chatgpt_maibot.errors import PluginError
    from .chatgpt_maibot.provider import PlanProvider
    from .chatgpt_maibot.store import CredentialStore
else:
    from config import OAuthConfig
    from chatgpt_maibot import APP_NAME, CLIENT_TYPE, VERSION
    from chatgpt_maibot.auth import OpenAIPlanAuth
    from chatgpt_maibot.errors import PluginError
    from chatgpt_maibot.provider import PlanProvider
    from chatgpt_maibot.store import CredentialStore


class OAuthPlugin(MaiBotPlugin):
    config_model = OAuthConfig

    async def on_load(self):
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(30, connect=15), follow_redirects=False)
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
        await self.auth.cancel_login()
        for task in (self.login_report, self.test_task):
            if task:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
        await self.client.aclose()

    async def on_config_update(self, scope, config_data, version):
        if scope == "self":
            self.auth.timeout_seconds = self.config.advanced.oauth_timeout_seconds
            self.provider.timeout_seconds = self.config.advanced.request_timeout_seconds

    def get_webui_config_schema(self, **kwargs):
        schema = super().get_webui_config_schema(**kwargs)
        schema["sections"]["plugin"].update(title="模型连接", description="账号授权与模型测试请打开插件的「账号与模型」页面。")
        schema["sections"]["advanced"].update(title="连接时间", description="默认值适合大多数部署，需要时再调整。", collapsed=True)
        schema["layout"] = {"type": "tabs", "tabs": [
            {"id": "connection", "title": "模型连接", "sections": ["plugin"], "order": 0},
            {"id": "advanced", "title": "高级设置", "sections": ["advanced"], "order": 1}]}
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

    @API("account", description="切换或退出账号", timeout_ms=90000)
    async def account(self, action: str, client_id: str):
        if self.test_task and not self.test_task.done():
            raise PluginError("模型测试正在运行，结束后再切换账号。")
        await self.cancel()
        if action == "switch":
            await self.auth.switch(client_id)
            message = "当前账号已切换，请重新读取模型列表。"
        elif action == "logout":
            confirmed = await self.auth.logout(client_id)
            message = "账号已退出。" if confirmed else "本机已退出。请在 ChatGPT 的用量设置中确认应用连接已断开。"
        else:
            raise PluginError("请选择切换账号或退出账号。")
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
    async def start_test(self, model: str):
        if not self.config.plugin.enabled:
            raise PluginError("请先在插件配置中启用模型连接。")
        if self.auth._login_task and not self.auth._login_task.done():
            raise PluginError("请先完成当前授权，再测试模型。")
        if self.test_task and not self.test_task.done():
            raise PluginError("模型测试正在运行，请稍等。")
        self.test = {"status": "running", "model": model, "started_at": time.time()}
        self.test_task = asyncio.create_task(self._test(model))
        return {"message": "正在测试模型…"}

    async def _test(self, model):
        started = time.monotonic()
        try:
            result = await self.handle_llm_provider("response", {"model_info": {"model_identifier": model},
                "message_list": [{"role": "user", "content": "请只回复：麦麦，连接成功。"}]})
            self.test.update(status="success", text=result.get("content", ""), usage=result.get("usage", {}))
        except Exception as error:
            self.test.update(status="error", message=str(error))
        finally:
            self.test["seconds"] = round(time.monotonic() - started, 1)

    @API("example", description="生成所选模型的 MaiBot 配置片段")
    async def example(self, model: str):
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
        return {"text": text}

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
