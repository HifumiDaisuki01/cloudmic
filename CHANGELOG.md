# Changelog

## 2.0.1 — 内置虚拟麦克风

完整官方 VB-CABLE Pack45 内置在 EXE；首次缺少设备时自动静默安装，保留系统 UAC。安装后刷新设备并自动选择，待重启标记避免重复安装，支持取消/失败后重试。根据当前官网许可保留 VB-Audio 来源、donationware 说明与捐助入口。

## 2.0.0 — CloudMic Next

完全重置的下一代。重建轻量桌面端、手机网页、Workers / SQLite Durable Objects 中转、配对认证、消息状态和语音队列。

移除旧版 Qt 单文件客户端、自备 Python 中转部署要求、内置云服务凭据机制与集成驱动安装。1.x 的代码和发布记录保留在 Git 历史及旧 Releases。

本版本针对 Windows 10/11 x64。自动测试不代替真实音质、虚拟麦克风和网络验收；详情见 README。
