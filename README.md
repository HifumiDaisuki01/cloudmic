# 云麦 CloudMic · 无声者的声音

**为听障与言语障碍（聋哑）人士设计的辅助交流软件。**

说不出话？没关系。在手机（网页）上打字，文字经中转服务器到达电脑端，合成语音后从虚拟麦克风"开口"——
让你在**电脑软件、网络游戏**中，也能向对方发出自己的声音，实现实时、零障碍的交流。

```
┌──────────┐  文字   ┌──────────────┐  文字   ┌──────────┐  TTS+播放  ┌────────────┐
│  手机网页  │ ──────▶ │  中转服务器    │ ──────▶ │  电脑端    │ ────────▶ │ VB-CABLE  │─▶ 软件/游戏
│ (扫码配对) │ ◀────── │ (中转服务器) │ ◀────── │ (CloudMic)│           │  虚拟麦克风 │   对方
└──────────┘  回执   └──────────────┘  状态   └──────────┘           └────────────┘
```

## 🚀 立即体验

我们提供了**仅供测试**的中转服务器，无需自建、打开即用：

> **http://61.184.23.165:23777/** — 手机浏览器打开即可看到配对页，与电脑端配对后即可体验"手机打字 → 电脑发声"

> ⚠️ 测试服务器**不保证连接速度与稳定性**，高峰期可能无法访问；正式使用建议按《部署教程》自建中转服务器（约 2 分钟）。

## 📮 问题反馈

使用中遇到任何问题，欢迎邮件反馈：**FAQ@keran.cc**

## 特性


| 项 | 说明 |
|---|---|
| 配对方式 | 电脑端显示**二维码 + 4 位配对码**，手机扫码或输码即连 |
| 低延迟 | 国内中转 WebSocket 直传（约 20-50ms），传输远快于语音合成 |
| TTS | 四引擎：edge-tts（自然女声/男声 8 种）/ 讯飞 TTS / 腾讯云 TTS（800万字符免费）/ 系统 SAPI 本地极速兜底；密钥在设置中填写，自用可内置 |
| 虚拟麦 | **内置官方驱动包**：首次启动自动检测，一键静默安装 VB-CABLE（免手动下载）；软件/游戏里麦克风选 CABLE Output 即可 |
| 多手机 | 一个电脑可同时配多台手机（家人朋友都能帮你发） |
| 常驻 | 托盘运行、断线自动重连、设置持久化 |

## 目录结构

```
cloudmic/
├── server/          中转服务器（中转服务器 部署）
│   ├── server.py    WebSocket 中转 + 手机网页，单进程
│   └── index.html   手机端网页（与 server.py 同目录，改 UI 只需动它）
├── pc/              电脑端（Windows）
│   ├── gamesay.py   主程序（四 TTS 引擎 + 内置密钥）
│   ├── requirements.txt
│   └── build.bat    打包 exe（纯 ASCII）
├── 使用说明.md      面向使用者的快速手册
├── 修改说明.md      ★面向 AI/开发者的维护文档（坑位 + 改法，接手先读）
└── 部署教程.md      从零到上手的完整步骤
```

## 快速开始（3 步）

### 1. 部署中转服务器（一次性，中转服务器上执行）

```bash
cd cloudmic/server
pip3 install websockets -i https://mirrors.cloud.tencent.com/pypi/simple
# 用 systemd 托管：开机自启 + 崩溃自动拉起（推荐）
cat > /etc/systemd/system/cloudmic.service <<'EOF'
[Unit]
Description=CloudMic Relay Server
After=network.target

[Service]
WorkingDirectory=/opt/cloudmic
ExecStart=/usr/bin/python3 /opt/cloudmic/server.py --port 23777
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload && systemctl enable --now cloudmic
# 查看状态/日志
systemctl status cloudmic && journalctl -u cloudmic -f
```

验证：浏览器打开 `http://YOUR_SERVER:23777/` 能看到手机配对页。
（若 23777 已被 frps 备用占用，改端口即可，电脑端填写对应地址。）

### 2. 电脑端运行

```bash
cd cloudmic/pc
python -m pip install -r requirements.txt -i https://mirrors.cloud.tencent.com/pypi/simple
python gamesay.py          # 开发模式
# 或打包：
build.bat                  # 产出 dist/CloudMic.exe
```

### 3. 手机配对

1. 电脑端启动后，窗口显示二维码 + 4 位配对码
2. 手机浏览器打开 `http://YOUR_SERVER:23777/`（建议"添加到主屏"变 App）
3. 三种方式任选：
   - **扫码**：手机系统相机/微信扫电脑屏幕二维码，自动打开并连接
   - **网页内扫一扫**：配对页点"📷 扫一扫"对准电脑屏幕（需 HTTPS 环境；当前 http 下点击会给出引导）
   - **输码**：手动输入电脑上的 4 位配对码
4. 输入文字点发送 / 回车 → 电脑立刻"开口"，软件/游戏里的对方听到你的声音

> 软件/游戏内设置：把麦克风设备选为 **CABLE Output (VB-Audio Virtual Cable)**。

## 延迟预算

| 环节 | 耗时 |
|---|---|
| 手机 → 服务器 → 电脑（WebSocket） | 约 20-50ms |
| edge-tts 合成（中文短句） | 约 300-800ms |
| 解码 + 播放到虚拟麦 | < 100ms |
| **总计（edge-tts）** | **约 0.4-1.0s** |
| SAPI 极速模式 | 约 0.2-0.4s |

## 为什么用中转而不是 P2P

云电脑/云桌面位于数据中心 NAT 之后，几乎必然是对称 NAT，WebRTC 打洞成功率很低。
国内中转延迟 20-50ms，远低于 TTS 合成耗时，**不是瓶颈**。传输层已独立封装，
未来若需直连可替换为 WebRTC DataChannel（服务器仅作信令）。

## 安全说明

- 配对 token 为 256bit 随机数，仅存于电脑端内存与二维码；4 位码用于快捷配对
- 服务器不记录任何聊天内容，纯透传
- 明文 HTTP/WS（内网级信任场景）；如需公网强安全可自行套 TLS 反代

## 故障排查

| 现象 | 处理 |
|---|---|
| 手机显示"电脑端离线" | 确认 exe 在运行、服务器连通（日志区显示"已连接"） |
| 软件/游戏里听不到声音 | ① 确认已安装 VB-CABLE ② 软件/游戏麦克风选 CABLE Output ③ 电脑端"播放设备"选中 CABLE Input |
| edge-tts 朗读失败 | 自动回退 SAPI；网络不通时可在设置切到"系统语音 SAPI" |
| 讯飞 401 | 程序自动交换 APIKey/APISecret 重试；仍失败检查系统时间/凭据 |
| 腾讯云报资源包用完 | 免费包只含标准/精品音色；大模型/超自然音色需单独领免费额度 |
| 手机连不上页面 | 检查服务器进程与 23777 端口防火墙（`ss -tlnp | grep 23777`） |

---

© 2026 Keran Technology Co., Ltd.
