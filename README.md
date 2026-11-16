# OpenAI OAuth · 麦麦账号连接

在 MaiBot WebUI 登录 ChatGPT，选择账号可用的模型，让麦麦用它聊天。

适用于 Docker、NAS 和本机部署。授权、账号切换、模型测试都在插件页面完成。

| 你想做什么 | 在哪里操作 |
| --- | --- |
| 连接 ChatGPT 账号 | 账号与模型 → 连接账号 |
| 查看能用哪些模型 | 读取模型列表 |
| 确认模型能正常回复 | 选择模型 → 测试模型 |
| 用于麦麦的回复和规划 | 添加到 MaiBot → 分配任务 |
| 允许回复时联网搜索 | 插件配置 → 模型连接 |
| 调整授权或请求等待时间 | 插件配置 → 高级设置 |

## 开始使用

需要 MaiBot **1.4.0+**、插件 SDK **2.23.0+**、Python **3.12+**。

1. 将本项目放入 MaiBot 的 `plugins/OpenAI-OAuth-MaiMbot`，在 MaiBot 使用的 Python 环境安装 `requirements.txt`。使用支持插件依赖安装的宿主时，可由宿主安装清单中的依赖。
2. 在 MaiBot WebUI 启用插件，打开 **账号与模型**。
3. 点击 **Continue with ChatGPT**，再打开授权链接，在 ChatGPT 页面完成授权。
4. 将浏览器最后跳转的完整地址粘回插件页面，点击 **完成连接**。Docker 下最后一页可能显示无法连接，复制地址栏即可。
5. 读取模型列表，选择模型和推理强度，测试后点击 **添加到 MaiBot**。
6. 在 **分配任务** 中查看当前模型，勾选回复、规划等用途，再点击 **应用到选中任务**。保存后宿主自动重载。

同机部署会读取宿主登录凭据；自定义端口或远程部署在插件高级设置填写 WebUI 地址与登录密码。手动配置片段保留在“分配任务”卡片底部。

模型服务商的客户端类型为 `openai_oauth_maimbot`，认证方式为 `none`，API Key 留空。请求使用插件保存的账号授权。

## Docker 部署

授权无需增加端口映射。浏览器在你的电脑上完成登录，容器通过粘贴的回调地址交换授权结果。

保留 MaiBot 分配的插件数据目录，其中的 `accounts.json` 和 `host_id.txt` 用于重启后恢复账号。官方 Compose 已映射插件数据目录时，沿用现有挂载。

详细操作见 [Docker 部署](docs/Docker部署.md) 和 [配置与使用](docs/配置与使用.md)。

## 支持哪些能力

- 文本聊天、模型支持的图片输入。
- MaiBot 工具调用、工具结果续接与 JSON 结构化输出。
- 模型内置网页搜索，可在配置里开启。
- 多账号保存与切换、授权到期自动刷新、账号退出。
- 模型测试结果、耗时和原生模型用量返回。

模型列表和套餐权限以账号返回结果为准。使用情况与应用授权可在 [ChatGPT 用量设置](https://chatgpt.com/settings/usage) 查看。向量模型、语音转写继续使用 MaiBot 中对应的服务。

## 来源与许可证

本项目基于 [Caeruvis/ChatGPT-MaiBot-connect-plugin](https://github.com/Caeruvis/ChatGPT-MaiBot-connect-plugin) 的账号授权与模型适配代码开发，并参考 [OpenAI 官方授权文档](https://developers.openai.com/siwc/token-sharing-open-source/sign-in)。

项目采用 [GPL-3.0](LICENSE)。复用部分的原 MIT 版权与许可见 [第三方许可](licenses/ChatGPT-MaiBot-connect-plugin-MIT.txt)。
