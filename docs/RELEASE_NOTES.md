# CloudMic 2.0.0 · 完全重置的下一代

这是对旧版 CloudMic 的整体重建：全新桌面 UI、手机网页、配对协议、语音队列与 Cloudflare Workers 中转。不兼容 1.x 服务端。

- Windows 独立 EXE，无需 Python、Qt、Node.js、FFmpeg。
- 默认托管中转，无需自备服务器；扫码或 8 位码配对，HTTPS/WSS 身份分离。
- 自然语音、Windows 本地回退与可选 Azure Speech；分句合成、内存缓存。
- 排队 / 合成 / 播放 / 完成 / 失败回执、停止清空、断线恢复与重复消息抑制。
- 新版不捆绑虚拟麦克风驱动：游戏输入仍需一次性配置兼容虚拟音频设备；已有设备直接选用。

下载 ZIP 解压运行 CloudMic.exe；也可单独下载 EXE。手机页：https://cloudmic-next.keran.workers.dev/

自动检查包含队列取消、协议验证、中转端到端请求及 Windows EXE 启动。附带截图与启动报告；它们不证明实际虚拟麦听音已通过。音质、真实游戏输入、国内网络与实际延迟需在目标设备验证，不承诺固定延迟。免费托管服务受平台配额限制。

EXE 未购买代码签名证书，Windows 可能显示发布者未知；请核对本 release 的 SHA256。旧 Releases 保留。

许可见 ZIP 内 THIRD_PARTY_NOTICES.md 和 licenses。LGPL 对应依赖源码附在 third-party-sources.zip；应用完整源码可由本 tag 源码包获得并重新构建。
