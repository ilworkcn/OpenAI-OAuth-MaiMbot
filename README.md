<div align="center">

# OpenAI OAuth · 麦麦账号连接

**把 ChatGPT 接到麦麦身边。**

登录账号，选好模型，再交给麦麦聊天、规划和看图。

![版本](https://img.shields.io/badge/版本-0.1.1-557b62)
![MaiBot](https://img.shields.io/badge/MaiBot-1.4.x-65758b)
![部署](https://img.shields.io/badge/部署-Docker%20%7C%20NAS%20%7C%20本机-b68b5e)
[![许可证](https://img.shields.io/badge/许可证-GPL--3.0-7c7193)](LICENSE)

[下载插件](https://github.com/ilworkcn/OpenAI-OAuth-MaiMbot/releases/latest) · [配置与使用](docs/配置与使用.md) · [Docker 部署](docs/Docker部署.md) · [更新记录](CHANGELOG.md)

</div>

---

## 🌿 连上以后，可以做什么？

| 功能 | 用起来是什么样 |
| --- | --- |
| 账号授权 | 在浏览器登录 ChatGPT，把授权结果粘回插件页面 |
| 模型选择 | 读取账号可用模型，测试回复、耗时和推理强度 |
| 自动添加 | 一键加入 MaiBot；同一个模型再次保存时更新设置 |
| 分配任务 | 看清各任务当前用的模型，再选择用于回复、规划或图片理解 |
| 账号管理 | 保存多个账号，随时切换；已退出的旧记录可以删除 |
| 网络配置 | 为 OpenAI 请求单独设置 HTTP 代理，适合 Docker 和 NAS |

支持文本、模型图片输入、工具调用与 JSON 结构化输出。模型内置网页搜索可在插件配置中开启。

## 📦 安装

需要 **MaiBot 1.4.x**、**插件 SDK 2.23.x** 和 **Python 3.12+**。

从 [Releases](https://github.com/ilworkcn/OpenAI-OAuth-MaiMbot/releases/latest) 下载插件 ZIP，在 MaiBot 的插件扩展页面导入，并按宿主提示加载。也可以将源码放入 `plugins/OpenAI-OAuth-MaiMbot`。

宿主支持自动安装插件依赖时，沿用其安装流程。手动安装请使用 **运行 MaiBot 的 Python 环境**：

```sh
python -m pip install -r plugins/OpenAI-OAuth-MaiMbot/requirements.txt
```

安装完成后，打开插件的 **账号与模型** 页面。

## 🔑 三步接好

### 1. 连接账号

点击 **Continue with ChatGPT**，再点击 **复制链接，去新标签页授权**。在 Firefox、Edge 等浏览器新标签页打开链接，登录并完成授权。

将最后跳转的完整地址粘回插件页面，点击 **完成连接**。

> Docker 部署时，最后一页可能显示无法连接 `127.0.0.1`。直接复制地址栏中的完整地址即可，容器会继续处理授权。

### 2. 选择模型

点击 **读取模型列表**，选择模型和推理强度，先 **测试模型**，再 **添加到 MaiBot**。

推理强度默认由模型决定；可选档位取决于具体模型。修改已有模型的强度后，点击保存即可生效。

### 3. 分配任务

在 **分配任务** 中选择已添加的模型，查看各任务当前配置，勾选要使用它的任务，再点击 **应用到选中任务**。

选中任务的模型列表会替换为所选模型，其他任务继续使用原配置。保存后由宿主校验并热重载。

<details>
<summary>想手动填写模型配置？</summary>

“分配任务”卡片底部保留了配置片段，可生成后复制到 MaiBot 的模型配置中。

服务商客户端类型为 `openai_oauth_maimbot`，认证方式为 `none`，API Key 留空。模型请求使用插件保存的账号授权。

</details>

## 🐳 Docker 与 NAS

| 需要调整什么 | 在哪里处理 |
| --- | --- |
| OpenAI 请求使用代理 | 插件配置 → 模型连接 → OpenAI 网络 |
| 自定义 WebUI 端口或远程宿主 | 插件配置 → 高级设置 → 自动添加模型 |
| 授权或模型请求等待时间 | 插件配置 → 高级设置 → 连接时间 |
| 重建容器后保留账号 | 持久化页面显示的插件数据目录 |

代理地址填写容器能访问的地址，例如 `http://192.168.1.5:7890`。需要认证时使用 `http://用户名:密码@地址:端口`。留空沿用容器环境代理。

浏览器负责登录，容器负责交换授权和请求模型，回调无需额外映射端口。同机添加模型会读取宿主登录凭据；远程宿主需填写对应 WebUI 地址和登录密码。

详细步骤见 [Docker 部署指南](docs/Docker部署.md)。

## 📖 继续了解

- **账号与套餐**：模型列表和可用权限以账号返回结果为准。用量与应用授权可在 [ChatGPT 用量设置](https://chatgpt.com/settings/usage) 查看。
- **其他插件**：通过 MaiBot 原生模型任务调用的插件，可继续使用这些任务，例如 MaiWeave 的生活规划。向量模型和语音转写使用各自对应的服务。
- **日常操作**：账号切换、旧记录删除、推理强度和任务设置见 [配置与使用](docs/配置与使用.md)。

## 🌼 来源与许可证

基于 [Caeruvis/ChatGPT-MaiBot-connect-plugin](https://github.com/Caeruvis/ChatGPT-MaiBot-connect-plugin) 的账号授权与模型适配代码开发，参考 [OpenAI 官方授权文档](https://developers.openai.com/siwc/token-sharing-open-source/sign-in)。感谢原作者的实现。

项目采用 [GPL-3.0](LICENSE)，复用部分的原 MIT 版权与许可保留在 [第三方许可](licenses/ChatGPT-MaiBot-connect-plugin-MIT.txt)。
