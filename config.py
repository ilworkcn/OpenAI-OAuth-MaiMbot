"""插件配置与中文表单说明。"""
from maibot_sdk import Field, PluginConfigBase


def setting(label, **kwargs):
    return Field(json_schema_extra={"label": label, "hint": kwargs.get("description", "")}, **kwargs)


class PluginSettings(PluginConfigBase):
    __ui_label__ = "模型连接"
    config_version: str = Field(default="0.1.0", json_schema_extra={"hidden": True})
    enabled: bool = setting("启用模型连接", default=True, description="让 MaiBot 通过已授权的 ChatGPT 账号调用模型。账号授权在插件页面完成。")
    enable_web_search: bool = setting("允许模型联网搜索", default=False, description="回复时可使用模型自带的网页搜索，是否可用取决于账号和所选模型。")
    enable_tool_controls: bool = setting("使用工具选择参数", default=False, description="开启后传递模型配置中的 tool_choice 和 parallel_tool_calls。常规工具调用保持可用。")


class AdvancedSettings(PluginConfigBase):
    __ui_label__ = "连接时间"
    oauth_timeout_seconds: int = setting("授权等待时间（秒）", default=600, ge=60, le=1800, description="从开始授权到提交回调地址的时间。过期后重新点击登录即可。")
    request_timeout_seconds: int = setting("模型请求超时（秒）", default=240, ge=30, le=900, description="包括模型推理和生成回复的总时间；MaiBot 对应模型任务的超时建议设为相同或更长。")


class OAuthConfig(PluginConfigBase):
    plugin: PluginSettings = Field(default_factory=PluginSettings)
    advanced: AdvancedSettings = Field(default_factory=AdvancedSettings)
