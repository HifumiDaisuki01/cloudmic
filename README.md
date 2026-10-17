# CloudMic Next · 云麦下一代

**完全重置的 CloudMic 2.0。当前桌面版 2.0.1，新增内置虚拟麦克风自动安装。** 为言语障碍人士、需要文字发声的人，以及不方便开口的玩家提供更简单的交流方式。

手机打字，电脑发声，让游戏和聊天软件里的对方听见你。

[下载 Windows 版](https://github.com/HifumiDaisuki01/cloudmic/releases/latest) · [手机配对页](https://cloudmic-next.keran.workers.dev/) · [使用说明](使用说明.md) · [自行部署](部署教程.md)

![CloudMic Next Windows 桌面](https://github.com/HifumiDaisuki01/cloudmic/releases/download/v2.0.1/windows-smoke.png)

## 这是一次重建

2.0 重新设计了桌面客户端、手机网页、配对协议、语音队列和云端中转。**不是旧版换皮，也不兼容 1.x 的配对服务器。**

- **无需自备服务器**：手机网页与文字中转运行在 Cloudflare Workers / SQLite Durable Objects。
- **独立 Windows EXE**：无需安装 Python、Qt、Node.js 或 FFmpeg。没有 Electron / WebView；使用轻量桌面 UI，开发依赖已经随成品打包。
- **统一的新界面**：浅色桌面、清晰的音色与设备选择；手机适配窄屏与系统深色模式。
- **扫码或 8 位码配对**：电脑与手机身份分离；新设备配对 10 分钟过期，房间最长 24 小时。刷新配对会撤销旧连接。
- **明确的朗读状态**：电脑接收 → 排队 → 合成 → 播放 → 完成 / 失败，转发成功不再冒充朗读成功。
- **声音不打架**：有界队列、重复消息抑制、停止并清空、超过 30 秒的排队消息自动跳过。断线不自动重发旧文字。
- **自然语音与离线兜底**：默认在线神经语音；网络不可用时回退 Windows 本地语音，也可使用自备密钥的 Azure Speech。
- **为延迟优化**：短句按句合成、内存音频缓存、独立网络与播放线程。界面显示电脑接收至开始播放的实际耗时。

## 立即使用

1. 从 Releases 下载 `CloudMic-2.0.1-windows-x64.zip`，解压后运行 `CloudMic.exe`。也可单独下载 EXE，许可证和使用说明在 ZIP 中更齐全。
2. 先打开“扬声器试听”，点“试听 / 测试朗读”，确认声音正常。
3. 手机扫描电脑二维码，或打开配对页输入电脑上的 **8 位码**。
4. 输入文字或点击快捷短语，即可发声。手机与电脑可以在不同网络中。

### 让游戏听见声音

**2.0.1 已内置官方 VB-CABLE Pack45 完整包（1.29 MB），终端用户无需另外下载。**

1. 首次启动若没有 CABLE Input，自动解压并启动官方静默安装器，无需点击应用内安装确认。
2. Windows 若请求管理员权限，点一次“是”；已经以管理员身份运行时通常不再需要这一步。应用不绕过系统 UAC。
3. 安装后自动重新检测音频设备；设备可用时切到 CABLE Input 并关闭扬声器试听。驱动要求重启而设备尚未出现时，会提示重启，并避免本次开机期间反复安装。
4. 游戏或聊天软件的麦克风选 **CABLE Output**。按键说话、语音激活仍在游戏内设置。

已有 VB-CABLE 就跳过安装。取消管理员确认、安装失败或超时会显示结果，可点“安装虚拟麦 · VB-Audio”重试；不会自动重启电脑。

VB-CABLE 由 **VB-Audio / Vincent Burel** 提供，属于 **donationware，欢迎支持原作者**。[官网与捐助](https://vb-audio.com/Cable/) · [当前分发许可](https://vb-audio.com/Services/licensing.htm)。只包含标准 VB-CABLE，不包含 A+B / C+D；驱动保留原作者许可，不能按 CloudMic 的 MIT 许可重新授权。

Windows 内核驱动仍需管理员权限，受限云电脑若禁止安装，需联系环境提供者或使用已有设备。

## 语音与延迟

| 模式 | 特点 | 条件 |
|---|---|---|
| 自然语音（默认） | 晓晓、云希等神经音色，免填写密钥；失败回退本地 | 需要访问在线语音服务；第三方接口无商业 SLA |
| 仅在线自然语音 | 在线失败时直接报告，不切换声音 | 网络可用 |
| 本地语音 | 不需要联网，响应通常更直接 | 音质和语言取决于 Windows 已安装的语音包 |
| Azure Speech | 官方接口，使用个人订阅 | 在设置中填写区域和密钥；费用由你的订阅承担 |

在线语音并非换一个 Worker 就能保证更快。网络、服务合成、文字长度与音频设备都会影响延迟；本项目**不承诺固定毫秒数或所有网络下的可达性**。界面的 `ms` 是电脑接收文字至开始播放的时间，不包含手机到电脑的传输，也不证明对方已听见。

免费托管中转有平台配额，不保证持续可用；Cloudflare 在中国大陆的可达性需要在实际网络中验证。中转只传文字和状态，**不在 Worker 上运行语音模型，也不中转语音音频**。

## 隐私与安全

- 配对全程 HTTPS/WSS，身份凭据在 WebSocket 首条认证消息中传输，不放在 URL 查询参数。
- 8 位码使用 32 字符字母表（40 bit），服务器保留碰撞检测；电脑与手机各自使用独立随机 256 bit 凭据。
- IP 级创建 / 配对限速、连接数限制、认证超时、单条最多 500 字。
- 中转不主动保存聊天正文；房间凭据的哈希及过期时间保存在 Durable Objects，过期删除。Cloudflare 仍处理请求元数据。
- 默认在线朗读会把文字发送给 Microsoft 的语音服务；Azure 模式发送给你配置的 Azure 区域。本地模式不发送文字给语音服务。
- 手机会话凭据放在 `sessionStorage`，快捷短语放在 `localStorage`；对话记录只保存在当前页面内存。
- 桌面偏好保存在 `%LOCALAPPDATA%\CloudMicNext\settings.json`。Azure 密钥使用 Windows 凭据管理器，不写入仓库或普通 JSON。
- 音频缓存只在进程内存；SAPI 的短暂 WAV 文件在合成后删除。关闭程序会清除内存缓存。

## 项目结构与开发

```text
worker/                 Workers + Durable Objects + 无依赖手机网页
  src/                  房间、认证、限速与转发
  public/               HTML / CSS / JavaScript
  test/                 协议单元测试
desktop/
  cloudmic/             UI、配置、传输、语音队列、音频输出
  main.py               Windows 启动入口
  requirements*.txt     固定的运行 / 构建依赖
  CloudMic.spec         独立 EXE 打包配置
tests/                  桌面队列与取消等回归测试
scripts/                中转集成检查与许可证收集
.github/workflows/      Windows 构建、EXE 启动检查与 Release 发布
```

Windows 开发使用 Python 3.12，运行 `desktop/build.bat`。运行测试：

```bash
python -m pip install -r desktop/requirements-dev.txt
python -m pytest -q
cd worker
npm ci
npm test
npx wrangler deploy --dry-run
```

完整部署和维护说明见 [部署教程](部署教程.md) 与 [修改说明](修改说明.md)。旧版实现可从 Git 历史及旧 Releases 获取；不会删除旧 release。

## 兼容与验证边界

目标平台为 Windows 10/11 x64。Windows Server、受限云桌面、蓝牙音频、游戏内按键说话和特定虚拟驱动需要在实际设备中验证。自动检查覆盖消息队列、取消、状态传递、配对认证、断线恢复，以及 Windows 打包程序启动，**不代替真人音质试听、虚拟麦克风端到端听音和国内网络测试**。具体范围见 [验证记录](docs/VALIDATION.md)。

MIT（应用与中转）；依赖保留各自许可，参见 [第三方声明](THIRD_PARTY_NOTICES.md)。反馈：FAQ@keran.cc。

© 2026 Keran Technology
