# -*- coding: utf-8 -*-
"""
云麦 CloudMic - 电脑端主程序
============================
手机网页输入文字 -> 中转服务器 -> 本程序 -> TTS 合成 -> 播放到虚拟麦克风（VB-CABLE）-> 软件/游戏语音

功能：
  - 启动自动配对：显示二维码 + 4 位配对码，手机扫码或输码即连
  - 收到文字自动朗读到虚拟麦克风（软件/游戏中的对方可听见）
  - TTS 引擎：edge-tts（自然，需联网）/ Windows SAPI（极速本地兜底）
  - 语速、音量可调；托盘常驻；断线自动重连

依赖（见 requirements.txt）：PySide6 edge-tts miniaudio sounddevice qrcode Pillow websockets
运行：python gamesay.py
打包：见 build.bat
"""

import asyncio
import base64
import email.utils
import hashlib
import hmac
import json
import os
import queue
import secrets
import struct
import sys
import threading
import time
import urllib.parse

# ---- 依赖导入（尽力而为，缺什么给什么提示） ----
try:
    from PySide6.QtCore import QEvent, QObject, QThread, QTimer, Qt, Signal
    from PySide6.QtGui import QAction, QCloseEvent, QIcon, QPixmap
    from PySide6.QtWidgets import (
        QApplication, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
        QMainWindow, QMenu, QMessageBox, QPushButton, QScrollArea, QSlider, QSizePolicy,
        QStyle, QSystemTrayIcon, QTextEdit, QVBoxLayout, QWidget,
    )
    HAS_QT = True
except Exception as _e:  # pragma: no cover
    HAS_QT = False
    QT_ERR = _e
    # 占位，保证模块在无 Qt 环境也能导入（供测试/CI）
    QObject = object
    Signal = lambda *a, **k: None

try:
    import qrcode
    from PIL import Image
    HAS_QR = True
except Exception:
    HAS_QR = False

try:
    import numpy as np  # noqa: F401  sounddevice 播放必需
    HAS_NUMPY = True
except Exception:
    HAS_NUMPY = False

try:
    import sounddevice as sd
    HAS_SD = True
except Exception:
    HAS_SD = False

try:
    import miniaudio
    HAS_MINI = True
except Exception:
    HAS_MINI = False

try:
    import websockets
    HAS_WS = True
except Exception:
    HAS_WS = False

APP_NAME = "云麦 CloudMic"
APP_VERSION = "1.0.0"

# 默认服务器（自备中转）与默认 TTS 音色
DEFAULT_SERVER = "ws://YOUR_SERVER:23777"
DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"
# 标准 v2/tts 在线语音合成接口（wss://tts-api.xfyun.cn/v2/tts）支持的常用音色：
# 注意：xiaoguo（小果）/x2_* 是 AIUI 大模型平台音色，普通 TTS 接口里没有！
DEFAULT_XFYUN_VOICE = "xiaoyan"

# 标准 v2/tts 常用中文音色（按 vcn 排序，对照控制台可选项）
XF_VOICE_LIST = [
    ("小燕（女·标准·默认）", "xiaoyan"),
    ("小萍（女·清晰）", "aisxping"),
    ("小宇（男·磁性）", "xiaoyu"),
    ("许久（男·沉稳）", "aisjiuxu"),
    ("小美（女·温柔）", "xiaomei"),
    ("小坤（男·浑厚）", "xiaokun"),
    ("小梦（女·活力）", "xiaomeng"),
    ("小蓉（女·四川话）", "xiaorong"),
    ("小莹（女·陕西话）", "xiaoying"),
    ("小强（男·湖南话）", "xiaoqiang"),
    ("凯瑟琳（女·美式英语）", "catherine"),
    ("小何（男·粤语）", "aisxhit"),
    ("艾伦（男·美式英语）", "ailun"),
    ("若曦（女·粤语）", "ruoxi"),
]

VOICE_LIST = [
    ("晓晓（女·清晰）", "zh-CN-XiaoxiaoNeural"),
    ("云希（男·磁性）", "zh-CN-YunxiNeural"),
    ("晓伊（女·甜美）", "zh-CN-XiaoyiNeural"),
    ("云扬（男·新闻腔）", "zh-CN-YunyangNeural"),
    ("云健（男·沉稳）", "zh-CN-YunjianNeural"),
    ("晓墨（女·活力）", "zh-CN-XiaomoNeural"),
    ("晓涵（女·温和）", "zh-CN-XiaohanNeural"),
    ("晓梦（女·软糯）", "zh-CN-XiaomengNeural"),
]

EDGE_VOICES = {cn: en for cn, en in VOICE_LIST}

# 腾讯云 TTS 音色（TextToVoice 2019-08-23，额度走"语音合成-通用"资源包）
# 控制台三类：标准语音合成-精品音色（默认，含 1xxx 标准 + 10xxxx 精品）、
#            大模型音色（501xxx/601xxx）、超自然音色（502xxx/602xxx/603xxx）
# 全部通过同一 TextToVoice 接口调用，仅 VoiceType 不同。
DEFAULT_TENCENT_CAT = "标准语音合成-精品音色"
DEFAULT_TENCENT_VOICE = "1001"
TENCENT_CATEGORIES = {
    "标准语音合成-精品音色": [
        ("智瑜（标准·情感女声·默认）", "1001"),
        ("智聆（标准·通用女声）", "1002"),
        ("智美（标准·客服女声）", "1003"),
        ("智云（标准·通用男声）", "1004"),
        ("智莉（标准·通用女声）", "1005"),
        ("智琪（标准·客服女声）", "1008"),
        ("智芸（标准·知性女声）", "1009"),
        ("智华（标准·通用男声）", "1010"),
        ("智蓉（标准·情感女声）", "1017"),
        ("智靖（标准·情感男声）", "1018"),
        ("WeJack（标准·英文男声）", "1050"),
        ("WeRose（标准·英文女声）", "1051"),
        ("智逍遥（精品·阅读男声）", "100510000"),
        ("智瑜（精品·情感女声）", "101001"),
        ("智燕（精品·新闻女声）", "101011"),
        ("智辉（精品·新闻男声）", "101013"),
        ("智萌（精品·男童声）", "101015"),
        ("智甜（精品·女童声）", "101016"),
        ("智彤（精品·粤语女声）", "101019"),
        ("智刚（精品·通用男声）", "101020"),
        ("智友（精品·通用男声）", "101054"),
        ("智付（精品·通用女声）", "101055"),
    ],
    "大模型音色": [
        ("智斌（阅读男声）", "501000"),
        ("智兰（资讯女声）", "501001"),
        ("智菊（阅读女声）", "501002"),
        ("智宇（阅读男声）", "501003"),
        ("月华（聊天女声）", "501004"),
        ("飞镜（聊天男声）", "501005"),
        ("千嶂（聊天男声）", "501006"),
        ("浅草（聊天男声）", "501007"),
        ("WeJames（英文男声）", "501008"),
        ("WeWinny（英文女声）", "501009"),
        ("爱小豪（聊天男声·多情感）", "601008"),
        ("爱小芊（聊天女声·多情感）", "601009"),
        ("爱小娇（聊天女声·多情感）", "601010"),
        ("爱小伊（阅读女声）", "601013"),
    ],
    "超自然音色": [
        ("智小柔（聊天女声）", "502001"),
        ("智小敏（聊天女声）", "502003"),
        ("智小满（营销女声）", "502004"),
        ("智小解（解说男声）", "502005"),
        ("智小悟（聊天男声）", "502006"),
        ("智小虎（聊天童声）", "502007"),
        ("爱小悠（聊天女声）", "602003"),
        ("暖心阿灿（聊天男声）", "602004"),
        ("专业梓欣（聊天女声）", "602005"),
        ("潇湘妹妹（特色女声）", "603001"),
        ("软萌心心（特色男童声）", "603002"),
        ("随和老李（聊天男声）", "603003"),
        ("温柔小柠（聊天女声）", "603004"),
        ("知心大林（聊天男声）", "603005"),
        ("沉稳青叔（聊天男声）", "603006"),
        ("邻家女孩（聊天女声）", "603007"),
    ],
}
# 扁平索引，供启动时按分类填充
TENCENT_VOICE_LIST = []
for _cat, _items in TENCENT_CATEGORIES.items():
    TENCENT_VOICE_LIST.extend(_items)

# ---------------------------------------------------------------------------
# 配置持久化（用户目录 json）
# ---------------------------------------------------------------------------
def cfg_path():
    base = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "CloudMic")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "config.json")


def load_cfg():
    try:
        with open(cfg_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_cfg(cfg):
    try:
        with open(cfg_path(), "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 内置默认凭据（公开版：留空，需在程序设置中自行填写讯飞/腾讯云密钥）
# 自用版可把下方值填上你的密钥，启动即自动写入配置、打开即用
# ---------------------------------------------------------------------------
BUILTIN_CREDENTIALS = {
    # ---- 讯飞（在线语音合成-流式版）：在讯飞控制台-语音合成服务页获取 ----
    "xfyun_appid": "",
    "xfyun_apikey": "",       # APIKey
    "xfyun_apisecret": "",    # APISecret
    "xfyun_voice": "xiaoyan",
    # ---- 腾讯云 TTS（语音合成-通用资源包）：在腾讯云控制台-访问管理 CAM-API 密钥管理获取 ----
    "tx_secret_id": "",
    "tx_secret_key": "",
    "tx_cat": "标准语音合成-精品音色",
    "tx_voice": "1001",
}


def ensure_builtin_cfg(cfg):
    """启动时把内置凭据写入 cfg（缺失或空时补默认，已有值不覆盖），返回是否变更"""
    changed = False
    for k, v in BUILTIN_CREDENTIALS.items():
        if v and cfg.get(k) != v:
            cfg[k] = v
            changed = True
    # 讯飞 Key/Secret 防呆：若发现反序（apikey 里存的是 APISecret），强制纠正
    if cfg.get("xfyun_apikey", "").startswith("MDBhNDRl") and cfg.get("xfyun_apisecret", "").startswith("05126c9c"):
        cfg["xfyun_apikey"], cfg["xfyun_apisecret"] = cfg["xfyun_apisecret"], cfg["xfyun_apikey"]
        changed = True
    if changed:
        save_cfg(cfg)
    return cfg


# ---------------------------------------------------------------------------
# 音频引擎：TTS 合成 + 播放（运行在后台 asyncio 线程内）
# ---------------------------------------------------------------------------
class AudioEngine:
    """负责 TTS 合成与播放，全部在后台线程调用"""

    def __init__(self, log_fn):
        self.log = log_fn
        self._sapi_ready = False
        self._sapi = None
        if sys.platform == "win32":
            try:
                import pythoncom  # noqa
                import win32com.client  # noqa
                self._sapi_ready = True
            except Exception:
                self._sapi_ready = False

    # ---- VB-CABLE 设备检测 ----
    @staticmethod
    def decode_wav_mono(wav_path, force_rate=None):
        """按 WAV 真实头信息解码为 1D 单声道 float32。
        关键：miniaudio.decode_file 不指定参数时默认转 44100Hz 立体声（L,R 交织），
        直接当单声道播放会慢一倍且声音错乱。这里强制 nchannels=1 + 真实采样率。
        返回 (samples_1d_float32, sample_rate)
        """
        import wave as _wave
        try:
            with _wave.open(wav_path, "rb") as wf:
                real_sr = wf.getframerate() or 16000
        except Exception:
            real_sr = force_rate or 16000
        sr = force_rate or real_sr
        dec = miniaudio.decode_file(
            wav_path,
            output_format=miniaudio.SampleFormat.FLOAT32,
            nchannels=1,
            sample_rate=sr,
            dither=miniaudio.DitherMode.NONE,
        )
        s = dec.samples
        if not isinstance(s, np.ndarray):
            s = np.asarray(s, dtype=np.float32)
        if s.ndim > 1:
            s = s.reshape(-1)
        return s, sr

    @staticmethod
    def find_cable_device():
        """返回 (输出设备名, 索引)；找不到返回 (None, None)"""
        if not HAS_SD:
            return None, None
        try:
            devs = sd.query_devices()
            for i, d in enumerate(devs):
                name = str(d.get("name", ""))
                if "CABLE Input" in name and d.get("max_output_channels", 0) > 0:
                    return name, i
        except Exception:
            pass
        return None, None

    # ---- VB-CABLE 驱动自动安装（内置官方驱动包，静默安装） ----
    @staticmethod
    def cable_bundle_dir():
        """定位内置 VB-CABLE 驱动包目录（PyInstaller 打包后为 _MEIPASS/vbcable）"""
        if getattr(sys, "frozen", False):
            return os.path.join(sys._MEIPASS, "vbcable")
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "vbcable")

    @staticmethod
    def cable_installed():
        """检测 VB-CABLE 驱动是否已装（查驱动文件 + 音频设备）"""
        if AudioEngine.find_cable_device()[1] is not None:
            return True
        # 驱动文件兜底（设备枚举有时需重启音频服务才刷新）
        try:
            drv = os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "System32", "drivers", "vbaudio_cable64_win7.sys")
            return os.path.isfile(drv)
        except Exception:
            return False

    @staticmethod
    def install_cable(log_fn=None):
        """释放内置驱动包并静默安装（VBCABLE_Setup_x64.exe -i -h）。
        注意：驱动安装需要管理员权限，非管理员时会触发一次 UAC 确认。
        返回 (ok, message)
        """
        def _log(m):
            if log_fn:
                try:
                    log_fn(m)
                except Exception:
                    pass

        bundle = AudioEngine.cable_bundle_dir()
        setup = os.path.join(bundle, "VBCABLE_Setup_x64.exe")
        if not os.path.isfile(setup):
            return False, f"内置驱动包缺失：{setup}"

        # 1) 复制驱动包到可写目录（避免 exe 目录/Program Files 只读）
        dest = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "CloudMic", "vbcable")
        try:
            import shutil
            if os.path.isdir(dest):
                shutil.rmtree(dest, ignore_errors=True)
            os.makedirs(dest, exist_ok=True)
            for name in os.listdir(bundle):
                src = os.path.join(bundle, name)
                if os.path.isfile(src):
                    shutil.copy2(src, os.path.join(dest, name))
        except Exception as e:
            # 复制失败则直接使用原目录（只读也能运行，仅个别系统会失败）
            dest = bundle
            _log(f"[VB-CABLE] 复制驱动包失败({e})，尝试直接从内置目录运行")

        setup_dest = os.path.join(dest, "VBCABLE_Setup_x64.exe")
        if not os.path.isfile(setup_dest):
            setup_dest = setup
        _log("[VB-CABLE] 正在安装虚拟麦克风驱动（约 5~15 秒，首次会弹一次系统权限确认）…")

        # 2) 静默安装：先直接跑（已是管理员则成功），失败再用 ShellExecute 提权（弹 UAC）
        import subprocess
        try:
            r = subprocess.run([setup_dest, "-i", "-h"], timeout=120)
            if r.returncode != 0:
                raise OSError(f"returncode={r.returncode}")
        except Exception as e:
            _log(f"[VB-CABLE] 常规启动失败({e})，尝试提权安装…")
            # ShellExecuteW runas -> 弹 UAC 确认
            import ctypes
            res = ctypes.windll.shell32.ShellExecuteW(
                None, "runas", setup_dest, "-i -h", dest, 0  # SW_HIDE
            )
            if res <= 32:
                _log(f"[VB-CABLE] 提权启动失败（代码 {res}），可能被取消")
                return False, f"安装未完成（代码 {res}）：需要管理员权限，请以管理员身份运行本程序后重试"

        # 3) 轮询等待安装完成（最多 60s）：驱动文件出现 + 设备枚举到 CABLE Input
        import time as _t
        drv = os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "System32", "drivers", "vbaudio_cable64_win7.sys")
        deadline = _t.time() + 60
        while _t.time() < deadline:
            if os.path.isfile(drv) or AudioEngine.find_cable_device()[1] is not None:
                _t.sleep(2)  # 给设备枚举一点时间
                if AudioEngine.find_cable_device()[1] is not None or os.path.isfile(drv):
                    _log("[VB-CABLE] 驱动安装完成 ✓ 已检测到 CABLE 虚拟麦克风")
                    return True, "安装成功，已检测到 CABLE 虚拟麦克风"
            _t.sleep(1)
        if os.path.isfile(drv):
            _log("[VB-CABLE] 驱动已写入，但设备枚举需刷新；请重启程序或重启电脑后使用")
            return True, "驱动已安装（设备可能需重启电脑后出现）"
        return False, "安装超时：未检测到驱动，请手动运行 vbcable\\VBCABLE_Setup_x64.exe"

    @staticmethod
    def list_output_devices():
        if not HAS_SD:
            return []
        try:
            devs = sd.query_devices()
            return [
                (str(d.get("name", f"设备 {i}")), i)
                for i, d in enumerate(devs)
                if d.get("max_output_channels", 0) > 0
            ]
        except Exception:
            return []

    # ---- SAPI 本地合成（Windows） ----
    def _sapi_speak_to_file(self, text, wav_path, rate):
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
        speaker = win32com.client.Dispatch("SAPI.SpVoice")
        stream = win32com.client.Dispatch("SAPI.SpFileStream")
        stream.Open(wav_path, 3)  # SSFMCreateForWrite
        speaker.AudioOutputStream = stream
        speaker.Rate = max(-10, min(10, int(rate * 2)))  # 界面 0.5~1.5 -> -10~10
        speaker.Speak(text)
        stream.Close()
        return True

    # ---- 讯飞 TTS（国内稳定，需 APPID/APIKey/APISecret） ----
    @staticmethod
    def pcm16_to_wav(pcm_bytes, sr=16000, ch=1):
        """16bit PCM -> WAV bytes"""
        n = len(pcm_bytes) // 2
        hdr = struct.pack(
            "<4sI4s4sIHHIIHH4sI",
            b"RIFF", 36 + n * 2, b"WAVE",
            b"fmt ", 16, 1, ch, sr, sr * ch * 2, ch * 2, 16,
            b"data", n * 2,
        )
        return hdr + pcm_bytes

    async def _xfyun_speak_to_file(self, text, wav_path, appid, apikey, apisecret, voice="xiaoyan", speed=50, volume=50, pitch=50):
        """讯飞标准 TTS 外壳：HTTP 401 时自动交换 APIKey/APISecret 重试一次（防填反）"""
        try:
            return await self._xfyun_core(text, wav_path, appid, apikey, apisecret, voice, speed, volume, pitch, swapped=False)
        except RuntimeError as e:
            if "401" not in str(e):
                raise
            # 疑似 Key/Secret 填反：交换后重试一次
            self.log("[讯飞] HTTP 401 -> 检测到 APIKey/APISecret 疑似填反，自动交换重试…")
            return await self._xfyun_core(text, wav_path, appid, apisecret, apikey, voice, speed, volume, pitch, swapped=True)

    async def _xfyun_core(self, text, wav_path, appid, apikey, apisecret, voice="xiaoyan", speed=50, volume=50, pitch=50, swapped=False):
        """讯飞标准 TTS（WebSocket v2，URL: wss://tts-api.xfyun.cn/v2/tts）
        注意：仅支持标准 v2/tts 音色（xiaoyan/aisxping/xiaoyu 等）。
        超拟人/AIUI 音色（小果 x2_xiaoguo、聆小琪 x4_lingxiaoqi_oral、x5_/x6_* 等）
        走的是另一套"超拟人合成"接口（cbm01.cn-huabei-1.xf-yun.com/v1/private/...），
        不在本函数支持范围内。
        """
        if not (appid and apikey and apisecret):
            raise RuntimeError("讯飞凭据未配置：请在设置中填写 APPID/APIKey/APISecret")
        if not text.strip():
            raise RuntimeError("讯飞合成文本为空")
        import websockets as _ws
        host = "tts-api.xfyun.cn"
        # RFC 1123 格式（如 "Thu, 01 Aug 2019 01:53:21 GMT"），与官方一致
        date = email.utils.formatdate(usegmt=True)
        # 参与签名字段：host, date, request-line（注意冒号后空格、\n 换行）
        sig_origin = f"host: {host}\ndate: {date}\nGET /v2/tts HTTP/1.1"
        sig = base64.b64encode(
            hmac.new(apisecret.encode("utf-8"), sig_origin.encode("utf-8"), hashlib.sha256).digest()
        ).decode("utf-8")
        auth_origin = (
            f'api_key="{apikey}", algorithm="hmac-sha256", '
            f'headers="host date request-line", signature="{sig}"'
        )
        auth = base64.b64encode(auth_origin.encode("utf-8")).decode("utf-8")
        url = (
            f"wss://{host}/v2/tts"
            f"?authorization={urllib.parse.quote(auth)}"
            f"&date={urllib.parse.quote(date)}"
            f"&host={host}"
        )
        payload = {
            "common": {"app_id": appid},
            "business": {
                # aue=raw 输出 PCM；audio/L16;rate=16000 即 16kHz/16bit/单声道
                "aue": "raw", "auf": "audio/L16;rate=16000",
                "vcn": voice, "speed": int(speed), "volume": int(volume), "pitch": int(pitch),
                "tte": "UTF8",
            },
            "data": {"status": 2, "text": base64.b64encode(text.encode("utf-8")).decode("utf-8")},
        }
        pcm = bytearray()
        # 兼容 websockets 13+：不再支持 open_timeout，使用 wait_for 包裹 connect
        try:
            ws = await asyncio.wait_for(_ws.connect(url, ping_interval=10, ping_timeout=10), timeout=10)
        except Exception as e:
            _msg = str(e)
            _hint = ""
            if "401" in _msg:
                _hint = (
                    "\n     → HTTP 401 = 鉴权失败（已自动尝试交换 APIKey/APISecret 重试，仍失败）。"
                    "\n       请检查："
                    "\n       ① 控制台里复制时是否带多余空格/换行"
                    "\n       ② APIKey 和 APISecret 是否正确（两串都是 32 位，易混淆）"
                    "\n       ③ 系统时间是否准确（和真实时间差超 5 分钟会导致签名校验失败）"
                )
            elif "Timed out" in _msg or "timed out" in _msg or "timeout" in _msg.lower():
                _hint = "\n     → 连接超时：检查网络是否能访问 tts-api.xfyun.cn（443 端口）"
            raise RuntimeError(f"讯飞连接失败: {e}{_hint}") from e
        try:
            await ws.send(json.dumps(payload))
            while True:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=30)
                except asyncio.TimeoutError:
                    raise RuntimeError("讯飞合成超时（30s 无响应）")
                msg = json.loads(raw)
                if msg.get("code") != 0:
                    code = msg.get("code")
                    msg_text = msg.get("message", "")
                    # 10005=非法参数/无效发音人；11200=未授权发音人；11201=套餐次数超限；100018=权限不足
                    hint = ""
                    if code in (10005, 10163, 11200):
                        hint = (
                            f"\n     → 当前 voice='{voice}' 不在 v2/tts 接口支持列表里。"
                            f"\n     → 如果你要用小果/聆小琪/超拟人音色，需要开通讯飞『超拟人合成』服务"
                            f"\n        并切换到 cbm01.cn-huabei-1.xf-yun.com 接口（本程序暂不支持）。"
                            f"\n     → 标准 v2/tts 常用：{', '.join(v for _, v in XF_VOICE_LIST[:6])} ..."
                        )
                    elif code in (10010, 100013):
                        hint = "\n     → APPID/APIKey/APISecret 不匹配或在控制台未开启『在线语音合成（流式版）』服务"
                    elif code == 11201:
                        hint = "\n     → 当日调用次数已用完（默认 500 次/天）"
                    raise RuntimeError(f"讯飞错误 code={code} {msg_text}{hint}")
                d = msg.get("data") or {}
                if d.get("audio"):
                    pcm += base64.b64decode(d["audio"])
                if d.get("status") == 2:
                    break
        finally:
            try:
                await ws.close()
            except Exception:
                pass
        if not pcm:
            raise RuntimeError("讯飞未返回音频数据")
        with open(wav_path, "wb") as f:
            f.write(self.pcm16_to_wav(bytes(pcm)))
        return True

    # ---- 腾讯云 TTS（TextToVoice 2019-08-23，走"语音合成-通用"资源包 800万字符免费） ----
    @staticmethod
    def _tencent_tc3_sign(secret_id, secret_key, payload_bytes, host="tts.tencentcloudapi.com", service="tts", region="ap-guangzhou", action="TextToVoice", version="2019-08-23", now=None):
        """腾讯云 API 3.0 TC3-HMAC-SHA256 签名，返回 (headers, url)"""
        import urllib.request
        now = now or int(time.time())
        date = time.strftime("%Y-%m-%d", time.gmtime(now))
        payload_hash = hashlib.sha256(payload_bytes).hexdigest()
        canonical_headers = (
            f"content-type:application/json; charset=utf-8\n"
            f"host:{host}\n"
        )
        signed_headers = "content-type;host"
        canonical_request = (
            "POST\n/\n\n" + canonical_headers + "\n" + signed_headers + "\n" + payload_hash
        )
        credential_scope = f"{date}/{service}/tc3_request"
        string_to_sign = (
            "TC3-HMAC-SHA256\n"
            f"{now}\n{credential_scope}\n" + hashlib.sha256(canonical_request.encode()).hexdigest()
        )
        def _hmac(key, msg):
            return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()
        secret_date = _hmac(("TC3" + secret_key).encode("utf-8"), date)
        secret_service = _hmac(secret_date, service)
        secret_signing = _hmac(secret_service, "tc3_request")
        signature = hmac.new(secret_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
        authorization = (
            f"TC3-HMAC-SHA256 Credential={secret_id}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )
        headers = {
            "Authorization": authorization,
            "Content-Type": "application/json; charset=utf-8",
            "Host": host,
            "X-TC-Action": action,
            "X-TC-Version": version,
            "X-TC-Timestamp": str(now),
            "X-TC-Region": region,
        }
        return headers

    async def _tencent_speak_to_file(self, text, wav_path, secret_id, secret_key, voice_type="1001", speed=0, volume=5):
        """腾讯云 TTS 合成到 wav 文件（TextToVoice 接口）"""
        if not (secret_id and secret_key):
            raise RuntimeError("腾讯云凭据未配置：请在设置中填写 SecretId/SecretKey（访问管理 CAM -> API 密钥管理）")
        if not text.strip():
            raise RuntimeError("腾讯云合成文本为空")
        # 腾讯云 TTS 单次限 150 汉字，超长截断
        if len(text) > 150:
            text = text[:150]
        import urllib.request
        host = "tts.tencentcloudapi.com"
        session_id = f"cloudmic-{os.getpid()}-{int(time.time()*1000)}"
        # wav 输出，16kHz（后续统一走 decode_wav_mono 解码）
        body = json.dumps({
            "Text": text,
            "SessionId": session_id,
            "VoiceType": int(voice_type),
            "Volume": int(volume),
            "Speed": float(speed),
            "ModelType": 1,
            "PrimaryLanguage": 1,
            "SampleRate": 16000,
            "Codec": "wav",
        }, ensure_ascii=False).encode("utf-8")
        headers = self._tencent_tc3_sign(secret_id, secret_key, body)
        req = urllib.request.Request(
            f"https://{host}/",
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read()
        except Exception as e:
            raise RuntimeError(f"腾讯云请求失败: {e}") from e
        try:
            r = json.loads(raw.decode("utf-8"))
        except Exception:
            raise RuntimeError(f"腾讯云返回非 JSON: {raw[:200]}")
        resp_body = r.get("Response", r)
        err = resp_body.get("Error")
        if err:
            code = err.get("Code", "?")
            msg = err.get("Message", "")
            hint = ""
            if code in ("AuthFailure.SignatureFailure", "AuthFailure.SecretIdNotFound", "AuthFailure.MFAFailure"):
                hint = "\n     → SecretId/SecretKey 有误：去『访问管理 CAM → API 密钥管理』核对（不是资源包页面的信息！）"
            elif code in ("AuthFailure.SignatureExpire", "AuthFailure.Expired"):
                hint = "\n     → 签名过期：系统时间不准，请校对系统时间"
            elif code == "UnsupportedOperation.ServerNotOpen":
                hint = "\n     → 未开通腾讯云语音合成服务：去 TTS 控制台开通（免费，800 万字符包）"
            elif code == "UnsupportedOperation.PkgExhausted":
                vt = str(voice_type)
                if vt.startswith(("502", "602", "603")):
                    hint = "\n     → 当前音色属『超自然音色』：你的免费资源包只含标准/精品音色，超自然音色需单独领取免费额度或购买资源包"
                elif vt.startswith(("501", "601")) or (len(vt) == 6 and vt.startswith(("50", "60"))):
                    hint = "\n     → 当前音色属『大模型音色』：你的免费资源包只含标准/精品音色，大模型音色需单独领取免费额度或购买资源包"
                else:
                    hint = "\n     → 资源包已用完或欠费"
            elif code == "InvalidParameterValue.VoiceType":
                hint = f"\n     → 音色 VoiceType={voice_type} 无效"
            raise RuntimeError(f"腾讯云 TTS 错误 {code}: {msg}{hint}")
        audio_b64 = resp_body.get("Audio")
        if not audio_b64:
            raise RuntimeError("腾讯云未返回音频数据")
        try:
            import base64 as _b64
            audio = _b64.b64decode(audio_b64)
        except Exception as e:
            raise RuntimeError(f"腾讯云音频解码失败: {e}") from e
        with open(wav_path, "wb") as f:
            f.write(audio)
        return True

    # ---- 播放 PCM 到指定设备 ----
    @staticmethod
    def _play(samples, samplerate, device_idx, volume):
        if not HAS_SD:
            return False
        if not HAS_NUMPY:
            raise RuntimeError(
                "缺少 numpy：请先安装依赖。在项目目录运行 "
                "python -m pip install numpy -i https://mirrors.cloud.tencent.com/pypi/simple"
            )
        # miniaudio 解码输出可能是 array.array，统一转 numpy
        if not isinstance(samples, np.ndarray):
            samples = np.asarray(samples, dtype=np.float32)
        # 拉成 1D 单声道：edge/讯飞都是 mono，miniaudio 偶发返回 (N,1) 会被 sd 当成多声道压扁
        if samples.ndim > 1:
            samples = samples.reshape(-1)
        if volume != 1.0:
            samples = samples * volume
        sd.play(samples, samplerate, device=device_idx)
        sd.wait()
        return True

    # ---- 统一入口：文字 -> 播放 ----
    async def speak(self, text, engine, voice, rate, volume, device_idx, xfyun=None, tencent=None):
        t0 = time.time()
        pcm = None
        sr = 24000
        xfyun = xfyun or {}
        tencent = tencent or {}

        if engine == "edge":
            try:
                import edge_tts
                # edge-tts 7.x rate 必须是 +N% / -N% 形式（绝对值 <= 100）
                # 滑条 50~150 -> edge 百分比 -50%~+50%
                edge_rate = max(-100, min(100, int(round(float(str(rate).strip("%").replace("+", "")) or 0))))
                comm = edge_tts.Communicate(
                    text, voice,
                    rate=f"{edge_rate:+d}%",
                )
                chunks = []
                async for c in comm.stream():
                    if c["type"] == "audio":
                        chunks.append(c["data"])
                if not chunks:
                    raise RuntimeError("edge-tts 未返回音频（服务端无响应）")
                mp3 = b"".join(chunks)
                if not HAS_MINI:
                    raise RuntimeError("缺少 miniaudio 解码器")
                # miniaudio 1.7x 用 decode(bytes)，旧版用 decode_bytes
                dec_fn = miniaudio.decode if hasattr(miniaudio, "decode") else miniaudio.decode_bytes
                # 关键：edge-tts 固定输出 24kHz/mono mp3，强制告诉 miniaudio，
                # 否则按默认 44100 回放会音调/速度失真（听起来"低沉/快/怪"）
                dec = dec_fn(
                    mp3,
                    output_format=miniaudio.SampleFormat.FLOAT32,
                    nchannels=1,
                    sample_rate=24000,
                    dither=miniaudio.DitherMode.NONE,
                )
                samples = dec.samples
                # 兜底：统一转 numpy + 拉成 1D 单声道（避免 (N,1) 被 sd 当多声道压扁）
                if not isinstance(samples, np.ndarray):
                    samples = np.asarray(samples, dtype=np.float32)
                if samples.ndim > 1:
                    samples = samples.reshape(-1)
                pcm, sr = samples, dec.sample_rate
                self.log(f"[TTS] edge-tts 合成 {len(mp3)//1024}KB 耗时 {time.time()-t0:.2f}s sr={sr}")
            except Exception as e:
                import edge_tts as _et
                self.log(
                    f"[TTS] edge-tts 失败({e})\n"
                    f"      版本 {getattr(_et, '__version__', '?')} | 建议升级: pip install -U edge-tts（需 >=7.2.8）\n"
                    f"      或改用讯飞引擎（设置→朗读引擎→讯飞 TTS）"
                )
                engine = "sapi"

        if engine == "xfyun":
            try:
                wav = os.path.join(
                    os.environ.get("TEMP", "."),
                    f"cloudmic_xf_{os.getpid()}_{int(time.time()*1000)}.wav",
                )
                try:
                    # 把界面语速 50~150% 映射到讯飞 0~100 档（50=默认）
                    # edge 风格 N%  -> 讯飞 50 + N/2（例 0% -> 50，+50% -> 75，-50% -> 25）
                    try:
                        _pct = int(str(rate).strip("%").replace("+", "")) or 0
                    except Exception:
                        _pct = 0
                    xf_speed = max(0, min(100, 50 + _pct // 2))
                    xf_volume = max(0, min(100, int(round(volume * 50))))
                    await self._xfyun_speak_to_file(
                        text, wav,
                        xfyun.get("appid", ""), xfyun.get("apikey", ""), xfyun.get("apisecret", ""),
                        xfyun.get("voice") or DEFAULT_XFYUN_VOICE,
                        speed=xf_speed, volume=xf_volume, pitch=50,
                    )
                    if not HAS_MINI:
                        raise RuntimeError("缺少 miniaudio 解码器")
                    # 强制按 WAV 真实头解码（16k/mono），避免 miniaudio 默认转 44.1k 立体声导致慢一倍/声音错乱
                    pcm, sr = self.decode_wav_mono(wav)
                    self.log(f"[TTS] 讯飞合成完成 耗时 {time.time()-t0:.2f}s sr={sr}")
                finally:
                    try:
                        os.remove(wav)
                    except Exception:
                        pass
            except Exception as e:
                self.log(f"[TTS] 讯飞失败({e})，回退 SAPI")
                engine = "sapi"

        if engine == "tencent":
            try:
                wav = os.path.join(
                    os.environ.get("TEMP", "."),
                    f"cloudmic_tx_{os.getpid()}_{int(time.time()*1000)}.wav",
                )
                try:
                    # 界面语速 50~150% -> 腾讯 Speed -2~+2（0=1.0x 正常，1=1.2x，2=1.5x）
                    try:
                        _pct = int(str(rate).strip("%").replace("+", "")) or 0
                    except Exception:
                        _pct = 0
                    tx_speed = max(-2.0, min(2.0, round(_pct / 25.0, 1)))
                    await self._tencent_speak_to_file(
                        text, wav,
                        tencent.get("secret_id", ""), tencent.get("secret_key", ""),
                        tencent.get("voice") or DEFAULT_TENCENT_VOICE,
                        speed=tx_speed, volume=5,
                    )
                    if not HAS_MINI:
                        raise RuntimeError("缺少 miniaudio 解码器")
                    pcm, sr = self.decode_wav_mono(wav)
                    self.log(f"[TTS] 腾讯云合成完成 耗时 {time.time()-t0:.2f}s sr={sr}")
                finally:
                    try:
                        os.remove(wav)
                    except Exception:
                        pass
            except Exception as e:
                self.log(f"[TTS] 腾讯云失败({e})，回退 SAPI")
                engine = "sapi"

        if engine == "sapi":
            if not self._sapi_ready:
                self.log("[TTS] SAPI 不可用，且 edge-tts 失败，跳过播放")
                return False
            wav = os.path.join(os.environ.get("TEMP", "."), f"cloudmic_{os.getpid()}_{int(time.time()*1000)}.wav")
            try:
                self._sapi_speak_to_file(text, wav, rate_num(rate))
                if not HAS_MINI:
                    raise RuntimeError("缺少 miniaudio 解码器")
                # 同样按 WAV 真实头解码，避免默认 44.1k 立体声错乱
                pcm, sr = self.decode_wav_mono(wav)
                self.log(f"[TTS] SAPI 合成完成 耗时 {time.time()-t0:.2f}s sr={sr}")
            except Exception as e:
                self.log(f"[TTS] SAPI 失败: {e}")
                return False
            finally:
                try:
                    os.remove(wav)
                except Exception:
                    pass

        if pcm is None:
            return False
        try:
            self._play(pcm, sr, device_idx, volume)
            self.log(f"[播放] 朗读完成（共 {time.time()-t0:.2f}s）")
            return True
        except Exception as e:
            self.log(f"[播放] 失败: {e}")
            return False


def rate_num(rate_str):
    """edge-tts 风格 "+20%" 转 SAPI 数值 -10~10"""
    try:
        v = int(rate_str.strip("%+"))
        return max(-10, min(10, v // 5))
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# 后台任务：WS 连接 + 消息处理（独立线程跑 asyncio）
# ---------------------------------------------------------------------------
class Backend(QObject):
    sig_status = Signal(str, str)     # (state, text)  state: on/off/wait
    sig_log = Signal(str)
    sig_code = Signal(str)            # 配对码
    sig_qr_url = Signal(str)          # 二维码内容（URL）
    sig_playing = Signal(bool)

    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.token = secrets.token_hex(16)
        self.code = "".join(secrets.choice("0123456789") for _ in range(4))
        self._loop = None
        self._ws = None
        self._stop = False
        self.audio = AudioEngine(self._log)
        self._send_q = queue.Queue()  # UI -> 后台指令
        self._device_idx = None

    # ---- UI 线程调用 ----
    def start(self):
        self.sig_code.emit(self.code)
        base = self.cfg.get("server", DEFAULT_SERVER)
        url = f"{base}/ws?tk={self.token}&role=pc&code={self.code}"
        self.sig_qr_url.emit(f"{base.replace('ws://','http://')}/#tk={self.token}")
        t = threading.Thread(target=self._run, args=(url,), daemon=True)
        t.start()

    def stop(self):
        """优雅停止：关闭 WS，后台线程自然退出"""
        self._stop = True
        if self._loop:
            try:
                async def _close():
                    if self._ws is not None:
                        try:
                            await self._ws.close()
                        except Exception:
                            pass
                self._loop.call_soon_threadsafe(
                    lambda: asyncio.ensure_future(_close())
                )
            except Exception:
                pass

    def _log(self, msg):
        self.sig_log.emit(msg)

    def send_ui(self, obj):
        """UI 线程发送消息到后台"""
        if self._loop:
            self._loop.call_soon_threadsafe(self._send_q.put, obj)

    # ---- 后台线程 ----
    def _run(self, url):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._worker(url))
        except Exception as e:
            self._log(f"[后台] 退出: {e}")

    async def _worker(self, url):
        self.sig_status.emit("wait", "正在连接中转服务器…")
        while not self._stop:
            try:
                self._ws = await websockets.connect(
                    url,
                    ping_interval=15, ping_timeout=15,
                    max_size=65536,
                    open_timeout=8,
                )
                self.sig_status.emit("on", "已连接 · 等待手机配对")
                self._log("[连接] 中转服务器已连接")
                # 接收任务 + UI 指令任务并行
                await asyncio.gather(
                    self._reader(),
                    self._ui_loop(),
                )
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._log(f"[连接] 断开({e})，2 秒后重连")
                self.sig_status.emit("off", "连接断开 · 重连中…")
                if self._stop:
                    break
                await asyncio.sleep(2)

    async def _ui_loop(self):
        """处理 UI 发来的指令（测试、设置变更等）"""
        while not self._stop:
            try:
                obj = self._send_q.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.1)
                continue
            mtype = obj.get("type")
            if mtype == "test":
                await self._do_speak(obj.get("text", "测试"))
            elif mtype == "set-device":
                self._device_idx = obj.get("idx")
                self._log(f"[设置] 播放设备 -> {obj.get('name','')}")

    async def _reader(self):
        """接收服务器消息"""
        try:
            async for raw in self._ws:
                try:
                    obj = json.loads(raw)
                except Exception:
                    continue
                if obj.get("type") == "say":
                    self.sig_status.emit("on", "正在朗读…")
                    self.sig_playing.emit(True)
                    await self._do_speak(obj.get("text", ""))
                    self.sig_playing.emit(False)
                    self.sig_status.emit("on", "已连接 · 输入内容即读")
        except Exception:
            pass

    async def _do_speak(self, text):
        text = (text or "").strip()
        if not text:
            return
        engine = self.cfg.get("engine", "edge")
        voice = self.cfg.get("voice", DEFAULT_VOICE)
        rate = self.cfg.get("rate", "+0%")
        volume = float(self.cfg.get("volume", 1.0))
        # 设备：配置指定 -> 自动 CABLE -> 默认设备
        idx = self._device_idx
        if idx is None:
            _, idx = self.audio.find_cable_device()
        self._log(f"[指令] 朗读: {text}")
        xfyun = {
            "appid": self.cfg.get("xfyun_appid", ""),
            "apikey": self.cfg.get("xfyun_apikey", ""),
            "apisecret": self.cfg.get("xfyun_apisecret", ""),
            "voice": self.cfg.get("xfyun_voice", DEFAULT_XFYUN_VOICE) or DEFAULT_XFYUN_VOICE,
        }
        tencent = {
            "secret_id": self.cfg.get("tx_secret_id", ""),
            "secret_key": self.cfg.get("tx_secret_key", ""),
            "voice": self.cfg.get("tx_voice", DEFAULT_TENCENT_VOICE) or DEFAULT_TENCENT_VOICE,
        }
        ok = await self.audio.speak(text, engine, voice, rate, volume, idx, xfyun=xfyun, tencent=tencent)
        if not ok and not self.audio.find_cable_device()[1]:
            self._log("[提示] 未检测到虚拟麦克风 VB-CABLE，声音可能未送达软件/游戏中的对方")


# ---------------------------------------------------------------------------
# 主窗口
# ---------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self, cfg, backend):
        super().__init__()
        self.cfg = cfg
        self.backend = backend
        self.setWindowTitle(APP_NAME)
        # 默认开窗就够大，内容完整显示（右侧下拉不被裁剪）
        self.setMinimumSize(520, 700)
        self.resize(560, 800)
        self.setStyleSheet(STYLE)
        self._build_ui()
        self._link_signals()
        self._load_cfg_to_ui()
        # 首次启动延迟检测虚拟麦克风（给窗口让出焦点，1.5s 后询问是否自动安装）
        QTimer.singleShot(1500, self._maybe_auto_install_cable)

    # ---------- UI ----------
    def _build_ui(self):
        cw = QWidget()
        root = QVBoxLayout(cw)
        root.setContentsMargins(18, 18, 18, 14)
        root.setSpacing(12)

        # 顶部标题
        head = QHBoxLayout()
        logo = QLabel("云麦 <b style='color:#3fb950'>CloudMic</b>")
        logo.setTextFormat(Qt.RichText)
        logo.setStyleSheet("font-size:20px;font-weight:700;")
        self.stDot = QLabel("●")
        self.stDot.setStyleSheet("color:#d29922;font-size:13px;")
        self.stText = QLabel("初始化…")
        self.stText.setStyleSheet("color:#8b98a9;font-size:13px;")
        head.addWidget(logo)
        head.addStretch(1)
        head.addWidget(self.stDot)
        head.addWidget(self.stText)
        root.addLayout(head)

        # 配对卡片
        pairCard = self._card()
        pairLayout = QVBoxLayout(pairCard)
        pairLayout.setContentsMargins(16, 14, 16, 14)
        pairLayout.setSpacing(10)

        # 配对码（放在最上方大字显示，避免被二维码遮挡）
        codeCaption = QLabel("配 对 码")
        codeCaption.setAlignment(Qt.AlignCenter)
        codeCaption.setStyleSheet("color:#8b98a9;font-size:11px;letter-spacing:3px;")
        codeRow = QHBoxLayout()
        codeRow.addStretch(1)
        self.codeLabel = QLabel("----")
        self.codeLabel.setStyleSheet(
            "font-size:46px;font-weight:800;color:#3fb950;"
            "letter-spacing:10px;background:#0d1117;border:1px dashed #2ea043;"
            "border-radius:12px;padding:6px 22px;"
        )
        codeRow.addWidget(self.codeLabel)
        codeRow.addStretch(1)
        # 操作提示：放在二维码上方，呼吸空间更足
        hint = QLabel("手机打开下方地址，扫码或输入上方 4 位配对码即可连接")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#8b98a9;font-size:12px;")
        hint.setAlignment(Qt.AlignCenter)
        self.qrLabel = QLabel()
        self.qrLabel.setAlignment(Qt.AlignCenter)
        self.qrLabel.setFixedSize(150, 150)
        self.serverEdit = QLineEdit()
        self.serverEdit.setPlaceholderText("中转服务器地址（ws://ip:port）")
        self.serverEdit.setStyleSheet(INPUT_STYLE)
        # 顺序：配对码 → 提示 → 二维码 → 服务器
        pairLayout.addWidget(codeCaption)
        pairLayout.addLayout(codeRow)
        pairLayout.addWidget(hint)
        pairLayout.addWidget(self.qrLabel, 0, Qt.AlignCenter)
        pairLayout.addWidget(self.serverEdit)
        root.addWidget(pairCard)

        # 设置卡片
        setCard = self._card()
        setLayout = QVBoxLayout(setCard)
        setLayout.setContentsMargins(16, 14, 16, 14)
        setLayout.setSpacing(8)

        # TTS 引擎
        engRow = QHBoxLayout()
        engRow.addWidget(self._label("朗读引擎"))
        self.engineCombo = QComboBox()
        self.engineCombo.addItem("edge-tts（自然·需联网）", "edge")
        self.engineCombo.addItem("讯飞 TTS（国内·需填凭据）", "xfyun")
        self.engineCombo.addItem("腾讯云 TTS（800万字符免费）", "tencent")
        self.engineCombo.addItem("系统语音 SAPI（极速·本地）", "sapi")
        self.engineCombo.setStyleSheet(INPUT_STYLE)
        engRow.addWidget(self.engineCombo, 1)
        setLayout.addLayout(engRow)

        # 讯飞凭据（选讯飞引擎时显示）
        self.xfBox = QFrame()
        xfLay = QVBoxLayout(self.xfBox)
        xfLay.setContentsMargins(8, 6, 8, 6)
        xfLay.setSpacing(6)
        self.xfAppid = QLineEdit(); self.xfAppid.setPlaceholderText("讯飞 APPID")
        self.xfKey = QLineEdit(); self.xfKey.setPlaceholderText("讯飞 APIKey")
        self.xfSecret = QLineEdit(); self.xfSecret.setPlaceholderText("讯飞 APISecret")
        # 发音人改为下拉（标准 v2/tts 音色）；同时给一个手动输入入口，照顾用户自定义
        xfVoiceRow = QHBoxLayout()
        xfVoiceRow.setSpacing(6)
        self.xfVoice = QComboBox()
        self.xfVoice.setEditable(True)
        for cn, vcn in XF_VOICE_LIST:
            self.xfVoice.addItem(f"{cn}  [{vcn}]", vcn)
        self.xfVoice.setStyleSheet(INPUT_STYLE)
        self.xfVoiceHint = QLabel("⚠ xiaoguo/小果 属『超拟人』，需另开服务（本程序走 v2/tts 标准接口）")
        self.xfVoiceHint.setStyleSheet("color:#d29922;font-size:11px;")
        self.xfVoiceHint.setWordWrap(True)
        xfVoiceRow.addWidget(self.xfVoice, 1)
        for w in (self.xfAppid, self.xfKey, self.xfSecret):
            w.setStyleSheet(INPUT_STYLE)
        xfLay.addWidget(self.xfAppid)
        xfLay.addWidget(self.xfKey)
        xfLay.addWidget(self.xfSecret)
        xfLay.addLayout(xfVoiceRow)
        xfLay.addWidget(self.xfVoiceHint)
        setLayout.addWidget(self.xfBox)

        # 腾讯云凭据（选腾讯云引擎时显示）
        self.txBox = QFrame()
        txLay = QVBoxLayout(self.txBox)
        txLay.setContentsMargins(8, 6, 8, 6)
        txLay.setSpacing(6)
        self.txSecretId = QLineEdit(); self.txSecretId.setPlaceholderText("腾讯云 SecretId（CAM API 密钥管理）")
        self.txSecretKey = QLineEdit(); self.txSecretKey.setPlaceholderText("腾讯云 SecretKey")
        self.txSecretKey.setEchoMode(QLineEdit.Password)
        for w in (self.txSecretId, self.txSecretKey):
            w.setStyleSheet(INPUT_STYLE)
        # 音色分类下拉（标准精品 / 大模型 / 超自然），切换时联动刷新音色列表
        txCatRow = QHBoxLayout()
        txCatRow.setSpacing(6)
        txCatRow.addWidget(self._label("音色类型"))
        self.txCatCombo = QComboBox()
        for cat in TENCENT_CATEGORIES:
            self.txCatCombo.addItem(cat, cat)
        self.txCatCombo.setStyleSheet(INPUT_STYLE)
        txCatRow.addWidget(self.txCatCombo, 1)
        # 具体音色下拉
        self.txVoice = QComboBox()
        self.txVoice.setStyleSheet(INPUT_STYLE)
        txVoiceRow = QHBoxLayout()
        txVoiceRow.setSpacing(6)
        txVoiceRow.addWidget(self._label("音色"))
        txVoiceRow.addWidget(self.txVoice, 1)
        self.txHint = QLabel("密钥获取：腾讯云控制台 → 访问管理 CAM → API 密钥管理 → 新建密钥（非资源包页面）。\n注：免费资源包只覆盖标准/精品音色，大模型/超自然音色需单独领取免费额度或购买。")
        self.txHint.setStyleSheet("color:#d29922;font-size:11px;")
        self.txHint.setWordWrap(True)
        txLay.addWidget(self.txSecretId)
        txLay.addWidget(self.txSecretKey)
        txLay.addLayout(txCatRow)
        txLay.addLayout(txVoiceRow)
        txLay.addWidget(self.txHint)
        setLayout.addWidget(self.txBox)

        # 音色
        voiceRow = QHBoxLayout()
        voiceRow.addWidget(self._label("音色"))
        self.voiceCombo = QComboBox()
        for cn, en in VOICE_LIST:
            self.voiceCombo.addItem(cn, en)
        self.voiceCombo.setStyleSheet(INPUT_STYLE)
        voiceRow.addWidget(self.voiceCombo, 1)
        setLayout.addLayout(voiceRow)

        # 语速
        rateRow = QHBoxLayout()
        rateRow.addWidget(self._label("语速"))
        self.rateSlider = QSlider(Qt.Horizontal)
        self.rateSlider.setRange(50, 150)
        self.rateSlider.setValue(100)
        self.rateVal = QLabel("100%")
        self.rateVal.setStyleSheet("color:#8b98a9;font-size:12px;width:44px;")
        rateRow.addWidget(self.rateSlider, 1)
        rateRow.addWidget(self.rateVal)
        setLayout.addLayout(rateRow)

        # 音量
        volRow = QHBoxLayout()
        volRow.addWidget(self._label("音量"))
        self.volSlider = QSlider(Qt.Horizontal)
        self.volSlider.setRange(10, 200)
        self.volSlider.setValue(100)
        self.volVal = QLabel("100%")
        self.volVal.setStyleSheet("color:#8b98a9;font-size:12px;width:44px;")
        volRow.addWidget(self.volSlider, 1)
        volRow.addWidget(self.volVal)
        setLayout.addLayout(volRow)

        # 播放设备
        devRow = QHBoxLayout()
        devRow.addWidget(self._label("播放设备"))
        self.devCombo = QComboBox()
        self.devCombo.setStyleSheet(INPUT_STYLE)
        self.refreshDevBtn = QPushButton("刷新")
        self.refreshDevBtn.setStyleSheet(BTN_SMALL)
        # 虚拟麦克风一键安装（内置 VB-CABLE 驱动包）
        self.installCableBtn = QPushButton("💿 装虚拟麦")
        self.installCableBtn.setStyleSheet(BTN_SMALL)
        self.installCableBtn.setToolTip("未检测到虚拟麦克风时，一键静默安装 VB-CABLE 驱动（约 10 秒，首次弹一次系统权限确认）")
        devRow.addWidget(self.devCombo, 1)
        devRow.addWidget(self.refreshDevBtn)
        devRow.addWidget(self.installCableBtn)
        setLayout.addLayout(devRow)

        # 按钮行
        btnRow = QHBoxLayout()
        self.testBtn = QPushButton("🔊 测试朗读")
        self.testBtn.setStyleSheet(BTN_PRIMARY)
        self.minBtn = QPushButton("最小化到托盘")
        self.minBtn.setStyleSheet(BTN_GHOST)
        btnRow.addWidget(self.testBtn, 1)
        btnRow.addWidget(self.minBtn, 1)
        setLayout.addLayout(btnRow)
        root.addWidget(setCard)

        # 日志
        logCard = self._card()
        logLayout = QVBoxLayout(logCard)
        logLayout.setContentsMargins(12, 10, 12, 10)
        self.logView = QTextEdit()
        self.logView.setReadOnly(True)
        self.logView.setStyleSheet(LOG_STYLE)
        self.logView.setFixedHeight(130)
        logLayout.addWidget(QLabel("运行日志"))
        logLayout.addWidget(self.logView)
        root.addWidget(logCard, 1)

        # 用滚动区域包裹：内容超出窗口时滚动，永不挤压
        cw.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(cw)
        self.setCentralWidget(scroll)

    # ---------- 工具 ----------
    def eventFilter(self, obj, event):
        """吞掉鼠标滚轮事件：防止悬停在下拉框上滚动页面时误切选项"""
        if event.type() == QEvent.Wheel and isinstance(obj, QComboBox):
            return True
        return super().eventFilter(obj, event)

    def _no_wheel(self, *widgets):
        """给控件安装滚轮拦截过滤器（可编辑下拉的内部输入框也一并拦截）"""
        for w in widgets:
            if w is None:
                continue
            w.installEventFilter(self)
            try:
                le = w.lineEdit()
                if le is not None:
                    le.installEventFilter(self)
            except Exception:
                pass

    def _card(self):
        c = QFrame()
        c.setStyleSheet("QFrame{background:#161b22;border:1px solid #2a3342;border-radius:14px;}")
        return c

    def _label(self, t):
        l = QLabel(t)
        l.setStyleSheet("color:#8b98a9;font-size:13px;")
        l.setFixedWidth(64)
        return l

    def _load_cfg_to_ui(self):
        if self.cfg.get("server"):
            self.serverEdit.setText(self.cfg["server"])
        ei = self.engineCombo.findData(self.cfg.get("engine", "edge"))
        if ei >= 0:
            self.engineCombo.setCurrentIndex(ei)
        vi = self.voiceCombo.findData(self.cfg.get("voice", "zh-CN-XiaoxiaoNeural"))
        if vi >= 0:
            self.voiceCombo.setCurrentIndex(vi)
        self.xfAppid.setText(self.cfg.get("xfyun_appid", ""))
        self.xfKey.setText(self.cfg.get("xfyun_apikey", ""))
        self.xfSecret.setText(self.cfg.get("xfyun_apisecret", ""))
        saved_xf_voice = self.cfg.get("xfyun_voice", DEFAULT_XFYUN_VOICE) or DEFAULT_XFYUN_VOICE
        # 优先按 vcn 匹配下拉项；不在下拉里就用手动输入
        idx = self.xfVoice.findData(saved_xf_voice)
        if idx >= 0:
            self.xfVoice.setCurrentIndex(idx)
        else:
            self.xfVoice.setEditText(saved_xf_voice)
        # 腾讯云
        self.txSecretId.setText(self.cfg.get("tx_secret_id", ""))
        self.txSecretKey.setText(self.cfg.get("tx_secret_key", ""))
        saved_tx_cat = self.cfg.get("tx_cat", DEFAULT_TENCENT_CAT)
        cidx = self.txCatCombo.findData(saved_tx_cat)
        if cidx < 0:
            cidx = 0
        self.txCatCombo.setCurrentIndex(cidx)
        self._fill_tx_voice(saved_tx_cat)
        saved_tx_voice = self.cfg.get("tx_voice", DEFAULT_TENCENT_VOICE) or DEFAULT_TENCENT_VOICE
        tidx = self.txVoice.findData(saved_tx_voice)
        if tidx >= 0:
            self.txVoice.setCurrentIndex(tidx)
        self.rateSlider.setValue(int(self.cfg.get("rate_val", 100)))
        self.volSlider.setValue(int(self.cfg.get("volume_val", 100)))
        self._update_xf_visible()
        self.refresh_devices(initial=True)
        # 关键：主动规范化一次 cfg（修正早期版本写入的字段，比如旧的 rate 公式）
        # 这里必须在 UI 设值完成后才调用，否则滑条 value 还没更新会被覆盖
        self._save_cfg()

    # ---------- 信号 ----------
    def _link_signals(self):
        b = self.backend
        b.sig_status.connect(self._on_status)
        b.sig_log.connect(self._on_log)
        b.sig_code.connect(self._on_code)
        b.sig_qr_url.connect(self._on_qr_url)
        b.sig_playing.connect(self._on_playing)

        self.testBtn.clicked.connect(self._on_test)
        self.minBtn.clicked.connect(self.hide)
        self.serverEdit.editingFinished.connect(self._save_cfg)
        self.engineCombo.currentIndexChanged.connect(self._on_engine_change)
        self.voiceCombo.currentIndexChanged.connect(self._save_cfg)
        self.rateSlider.valueChanged.connect(self._on_rate)
        self.volSlider.valueChanged.connect(self._on_vol)
        self.refreshDevBtn.clicked.connect(lambda: self.refresh_devices())
        self.installCableBtn.clicked.connect(self._on_install_cable)
        self.devCombo.currentIndexChanged.connect(self._on_dev_change)
        self.xfAppid.editingFinished.connect(self._save_cfg)
        self.xfKey.editingFinished.connect(self._save_cfg)
        self.xfSecret.editingFinished.connect(self._save_cfg)
        # xfVoice：下拉选择用 currentIndexChanged，手动输入用 editingFinished
        self.xfVoice.currentIndexChanged.connect(self._save_cfg)
        if self.xfVoice.isEditable() and self.xfVoice.lineEdit() is not None:
            self.xfVoice.lineEdit().editingFinished.connect(self._save_cfg)
        self.txSecretId.editingFinished.connect(self._save_cfg)
        self.txSecretKey.editingFinished.connect(self._save_cfg)
        # 分类切换 -> 刷新音色下拉 + 保存
        self.txCatCombo.currentIndexChanged.connect(self._on_tx_cat_change)
        self.txVoice.currentIndexChanged.connect(self._save_cfg)

        # 所有下拉框禁用滚轮切换（防误触）
        self._no_wheel(
            self.engineCombo, self.voiceCombo, self.devCombo,
            self.xfVoice, self.txCatCombo, self.txVoice,
        )

    def _update_xf_visible(self):
        eng = self.engineCombo.currentData()
        self.xfBox.setVisible(eng == "xfyun")
        self.txBox.setVisible(eng == "tencent")

    def _fill_tx_voice(self, cat):
        """按分类填充腾讯云音色下拉"""
        self.txVoice.blockSignals(True)
        self.txVoice.clear()
        items = TENCENT_CATEGORIES.get(cat, [])
        for cn, vt in items:
            self.txVoice.addItem(f"{cn}  [{vt}]", vt)
        self.txVoice.blockSignals(False)

    def _on_engine_change(self):
        self._update_xf_visible()
        self._save_cfg()

    def _on_tx_cat_change(self):
        """腾讯云音色分类切换：刷新音色下拉并保存"""
        cat = self.txCatCombo.currentData() or DEFAULT_TENCENT_CAT
        self._fill_tx_voice(cat)
        # 默认选中该分类第一个音色
        if self.txVoice.count() > 0:
            self.txVoice.setCurrentIndex(0)
        self._save_cfg()

    # ---------- 槽 ----------
    def _on_status(self, state, text):
        color = {"on": "#3fb950", "off": "#f85149", "wait": "#d29922"}.get(state, "#8b98a9")
        self.stDot.setStyleSheet(f"color:{color};font-size:13px;")
        self.stText.setText(text)

    def _on_log(self, msg):
        self.logView.append(time.strftime("%H:%M:%S ") + msg)
        sb = self.logView.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_code(self, code):
        self.codeLabel.setText(code)

    def _on_qr_url(self, url):
        if HAS_QR:
            try:
                img = qrcode.make(url)
                img = img.convert("RGB")
                tmp = os.path.join(os.environ.get("TEMP", "."), "cloudmic_qr.png")
                img.save(tmp)
                self.qrLabel.setPixmap(QPixmap(tmp).scaled(150, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                self._on_log(f"[配对] 二维码已生成，手机扫码或输码 {self.codeLabel.text()}")
                return
            except Exception as e:
                self._on_log(f"[二维码] 生成失败: {e}")
        self.qrLabel.setText("二维码不可用\n请用配对码连接")
        self._on_log(f"[配对] 手机访问 {url}")

    def _on_playing(self, playing):
        self.stDot.setStyleSheet("color:#3fb950;font-size:13px;")

    def _on_rate(self, v):
        self.rateVal.setText(f"{v}%")
        self._save_cfg()

    def _on_vol(self, v):
        self.volVal.setText(f"{v}%")
        self._save_cfg()

    def _on_test(self):
        self._save_cfg()
        self.backend.send_ui({"type": "test", "text": "你好，我是云麦，正在测试虚拟麦克风。"})
        self._on_log("[测试] 已发送测试指令")

    def _save_cfg(self):
        self.cfg["server"] = self.serverEdit.text().strip() or DEFAULT_SERVER
        self.cfg["engine"] = self.engineCombo.currentData()
        self.cfg["voice"] = self.voiceCombo.currentData()
        # 滑条 50~150 映射到 edge-tts 百分比 -50%~+50%（edge-tts 7.x 要求 +-N% 格式）
        #   滑条 50  -> -50% (慢一半)
        #   滑条 100 ->  +0% (正常)
        #   滑条 150 -> +50% (快一半)
        edge_rate_pct = self.rateSlider.value() - 100
        self.cfg["rate"] = f"{edge_rate_pct:+d}%"
        self.cfg["rate_val"] = self.rateSlider.value()
        self.cfg["volume"] = self.volSlider.value() / 100.0
        self.cfg["volume_val"] = self.volSlider.value()
        self.cfg["xfyun_appid"] = self.xfAppid.text().strip()
        self.cfg["xfyun_apikey"] = self.xfKey.text().strip()
        self.cfg["xfyun_apisecret"] = self.xfSecret.text().strip()
        # 保存 vcn：优先 currentData（下拉命中），否则保存 currentText（用户手输）
        vcn = self.xfVoice.currentData() or self.xfVoice.currentText().strip()
        self.cfg["xfyun_voice"] = vcn or DEFAULT_XFYUN_VOICE
        # 腾讯云
        self.cfg["tx_secret_id"] = self.txSecretId.text().strip()
        self.cfg["tx_secret_key"] = self.txSecretKey.text().strip()
        self.cfg["tx_cat"] = self.txCatCombo.currentData() or DEFAULT_TENCENT_CAT
        self.cfg["tx_voice"] = self.txVoice.currentData() or DEFAULT_TENCENT_VOICE
        save_cfg(self.cfg)

    def refresh_devices(self, initial=False):
        self.devCombo.blockSignals(True)
        cur = self.devCombo.currentData()
        self.devCombo.clear()
        devs = AudioEngine.list_output_devices()
        for name, idx in devs:
            tag = "（虚拟麦）" if "CABLE" in name else ""
            self.devCombo.addItem(f"{name}{tag}", idx)
        cable_name, cable_idx = AudioEngine.find_cable_device()
        if cur is not None:
            i = self.devCombo.findData(cur)
            if i >= 0:
                self.devCombo.setCurrentIndex(i)
            else:
                self.devCombo.setCurrentIndex(0)
        elif cable_idx is not None:
            i = self.devCombo.findData(cable_idx)
            if i >= 0:
                self.devCombo.setCurrentIndex(i)
        self.devCombo.blockSignals(False)
        # 有 CABLE 则隐藏"装虚拟麦"按钮，没有则高亮提示
        has_cable = cable_idx is not None or AudioEngine.cable_installed()
        self.installCableBtn.setVisible(not has_cable)
        # 后台同步设备
        self._on_dev_change()

    def _on_install_cable(self):
        """一键静默安装 VB-CABLE 虚拟麦克风驱动"""
        if AudioEngine.cable_installed():
            self._on_log("[VB-CABLE] 已安装虚拟麦克风，刷新设备列表")
            self.refresh_devices()
            return
        ret = QMessageBox.question(
            self, "安装虚拟麦克风",
            "未检测到 VB-CABLE 虚拟麦克风驱动。\n\n"
            "将自动静默安装（官方免费驱动，约 10 秒）：\n"
            "• 首次会弹出一次系统权限(UAC)确认，请点“是”\n"
            "• 安装完成后无需重启，可直接使用\n\n"
            "现在安装吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if ret != QMessageBox.Yes:
            return
        self.installCableBtn.setEnabled(False)
        self.installCableBtn.setText("⏳ 安装中…")
        self._on_log("[VB-CABLE] 开始安装…")
        ok, msg = AudioEngine.install_cable(self._on_log)
        self.installCableBtn.setEnabled(True)
        self.installCableBtn.setText("💿 装虚拟麦")
        self.refresh_devices()
        if ok:
            QMessageBox.information(self, "安装完成", f"{msg}\n\n请在“播放设备”下拉确认选中 CABLE Input。")
        else:
            QMessageBox.warning(self, "安装未完成", f"{msg}")

    def _maybe_auto_install_cable(self):
        """首次启动检测：没有虚拟麦克风时提示一键安装（延迟执行，避免抢窗口焦点）"""
        if AudioEngine.cable_installed():
            return
        ret = QMessageBox.question(
            self, "检测到未安装虚拟麦克风",
            "要让软件/游戏里的对方听到你的声音，需要 VB-CABLE 虚拟麦克风驱动。\n\n"
            "已内置官方驱动包，一键静默安装（约 10 秒，弹一次系统权限确认）。\n\n"
            "现在安装吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if ret == QMessageBox.Yes:
            self._on_install_cable()

    def _on_dev_change(self):
        idx = self.devCombo.currentData()
        name = self.devCombo.currentText()
        if idx is not None:
            self.backend.send_ui({"type": "set-device", "idx": idx, "name": name})

    def closeEvent(self, event: QCloseEvent):
        """关闭按钮 -> 最小化到托盘"""
        event.ignore()
        self.hide()
        if self.tray:
            self.tray.showMessage(APP_NAME, "已最小化到托盘，双击图标恢复", QSystemTrayIcon.Information, 1500)

    # 供托盘使用
    def attach_tray(self, tray):
        self.tray = tray


# ---------------------------------------------------------------------------
# 样式
# ---------------------------------------------------------------------------
STYLE = """
QMainWindow{background:#0d1117;}
QWidget{color:#e6edf3;font-family:'Microsoft YaHei','PingFang SC',sans-serif;font-size:13px;}
QLabel{background:transparent;}
QLineEdit,QComboBox,QTextEdit{background:#1c2330;border:1px solid #2a3342;border-radius:8px;padding:6px 8px;color:#e6edf3;selection-background-color:#238636;}
QLineEdit:focus,QComboBox:focus{border-color:#3fb950;}
QComboBox QAbstractItemView{background:#161b22;border:1px solid #2a3342;color:#e6edf3;selection-background-color:#238636;}
QSlider::groove:horizontal{height:4px;background:#2a3342;border-radius:2px;}
QSlider::handle:horizontal{width:16px;height:16px;margin:-6px 0;border-radius:8px;background:#3fb950;}
QSlider::sub-page:horizontal{background:#3fb950;border-radius:2px;}
QPushButton{border:none;border-radius:9px;padding:9px 12px;font-weight:600;}
"""
INPUT_STYLE = "QLineEdit,QComboBox{background:#1c2330;border:1px solid #2a3342;border-radius:8px;padding:6px 8px;color:#e6edf3;}"
BTN_PRIMARY = "QPushButton{background:linear-gradient(135deg,#238636,#2ea043);color:#fff;}"
BTN_PRIMARY += "QPushButton:hover{background:#2ea043;}"
BTN_PRIMARY += "QPushButton:pressed{background:#1f6f3a;}"
BTN_GHOST = "QPushButton{background:#1c2330;border:1px solid #2a3342;color:#8b98a9;}"
BTN_GHOST += "QPushButton:hover{border-color:#3fb950;color:#e6edf3;}"
BTN_SMALL = "QPushButton{background:#1c2330;border:1px solid #2a3342;color:#8b98a9;border-radius:7px;padding:6px 10px;font-size:12px;}"
BTN_SMALL += "QPushButton:hover{border-color:#3fb950;color:#e6edf3;}"
LOG_STYLE = "QTextEdit{background:#0d1117;border:1px solid #2a3342;border-radius:8px;color:#8b98a9;font-family:Consolas,'Courier New',monospace;font-size:11px;}"


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def main():
    if not HAS_QT:
        print(f"缺少 PySide6：pip install PySide6  ({QT_ERR})")
        sys.exit(1)
    if not HAS_WS:
        print("缺少 websockets：pip install websockets")
        sys.exit(1)
    if not (HAS_SD and HAS_MINI):
        print("缺少 sounddevice/miniaudio：pip install sounddevice miniaudio")
        sys.exit(1)
    if not HAS_NUMPY:
        print("缺少 numpy：pip install numpy  （sounddevice 播放必需）")
        sys.exit(1)

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)

    cfg = load_cfg()
    # 内置凭据自动填充：打开即用（无需手动输入讯飞/腾讯云密钥）
    cfg = ensure_builtin_cfg(cfg)
    backend = Backend(cfg)

    win = MainWindow(cfg, backend)

    # 托盘
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.png")
    app_icon = QIcon(icon_path) if os.path.exists(icon_path) else app.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
    tray = QSystemTrayIcon(app_icon, app)
    tray.setToolTip(APP_NAME)
    menu = QMenu()
    act_show = QAction("打开面板", menu)
    act_show.triggered.connect(lambda: (win.showNormal(), win.raise_(), win.activateWindow()))
    act_quit = QAction("退出", menu)
    act_quit.triggered.connect(app.quit)
    menu.addAction(act_show)
    menu.addSeparator()
    menu.addAction(act_quit)
    tray.setContextMenu(menu)
    tray.activated.connect(lambda reason: win.showNormal() if reason == QSystemTrayIcon.DoubleClick else None)
    tray.show()
    win.attach_tray(tray)

    backend.start()

    # 定时刷新设备列表（检测 VB-CABLE 是否后装）
    timer = QTimer()
    timer.timeout.connect(lambda: win.refresh_devices() if not win.isVisible() else None)
    timer.start(5000)

    app.aboutToQuit.connect(backend.stop)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
