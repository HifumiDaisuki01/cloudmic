# -*- coding: utf-8 -*-
"""验证 gamesay.py 的 _xfyun_speak_to_file 外壳：凭据填反时自动交换重试"""
import asyncio, os, sys, tempfile

# ---- 注入假 PySide6（本测试只用到 AudioEngine，不需要真实 Qt） ----
import types
fake_qt = types.ModuleType("PySide6")
fake_qtc = types.ModuleType("PySide6.QtCore")
fake_qtg = types.ModuleType("PySide6.QtGui")
fake_qtw = types.ModuleType("PySide6.QtWidgets")
for _name, _mod in [("PySide6", fake_qt), ("PySide6.QtCore", fake_qtc),
                    ("PySide6.QtGui", fake_qtg), ("PySide6.QtWidgets", fake_qtw)]:
    sys.modules.setdefault(_name, _mod)

def _cls(*a, **k):
    return type("Fake", (), {"__init__": lambda self, *x, **y: None,
                             "addItem": lambda self, *x, **y: None,
                             "setEditable": lambda self, *x: None,
                             "isEditable": lambda self: False,
                             "currentData": lambda self: None,
                             "currentText": lambda self: "",
                             "setStyleSheet": lambda self, *x: None,
                             "setText": lambda self, *x: None,
                             "setCurrentIndex": lambda self, *x: None,
                             "setEditText": lambda self, *x: None,
                             "lineEdit": lambda self: None,
                             "text": lambda self: "",
                             "setPlaceholderText": lambda self, *x: None,
                             "setVisible": lambda self, *x: None,
                             "setFixedWidth": lambda self, *x: None,
                             "setFixedSize": lambda self, *x: None,
                             "setFixedHeight": lambda self, *x: None,
                             "setWordWrap": lambda self, *x: None,
                             "setAlignment": lambda self, *x: None,
                             "setReadOnly": lambda self, *x: None,
                             "setMinimumSize": lambda self, *x: None,
                             "setRange": lambda self, *x: None,
                             "setValue": lambda self, *x: None,
                             "value": lambda self: 100,
                             "currentIndexChanged": lambda self: None,
                             "editingFinished": lambda self: None,
                             "clicked": lambda self: None,
                             "valueChanged": lambda self: None,
                             "currentIndex": lambda self: 0,
                             "clear": lambda self: None,
                             "blockSignals": lambda self, *x: None,
                             "verticalScrollBar": lambda self: None,
                             "setWidgetResizable": lambda self, *x: None,
                             "setFrameShape": lambda self, *x: None,
                             "setWidget": lambda self, *x: None,
                             "setCentralWidget": lambda self, *x: None,
                             "setSizePolicy": lambda self, *x: None,
                             "setContentsMargins": lambda self, *x: None,
                             "setSpacing": lambda self, *x: None,
                             "addWidget": lambda self, *x: None,
                             "addLayout": lambda self, *x: None,
                             "addStretch": lambda self, *x: None,
                             "setObjectName": lambda self, *x: None,
                             })()

# 让类引用可用
for _n in ["QEvent", "QObject", "QThread", "QTimer", "QApplication", "QComboBox", "QFrame",
           "QHBoxLayout", "QLabel", "QLineEdit", "QMainWindow", "QMenu",
           "QPushButton", "QScrollArea", "QSlider", "QSizePolicy", "QStyle",
           "QSystemTrayIcon", "QTextEdit", "QVBoxLayout", "QWidget", "QAction",
           "QCloseEvent", "QIcon", "QPixmap"]:
    setattr(fake_qtc, _n, _cls())
    setattr(fake_qtg, _n, _cls())
    setattr(fake_qtw, _n, _cls())
# Qt / Signal 需要特别处理
fake_qtc.Signal = lambda *a, **k: None
fake_qtc.Qt = types.SimpleNamespace(
    AlignCenter=0, AlignHCenter=0, RichText=0, Horizontal=0,
    KeepAspectRatio=0, SmoothTransformation=0, NoFrame=0,
    Preferred=0, StandardPixmap=0, DoubleClick=0, Information=0,
    ComputerIcon=0,
)
fake_qtw.QStyle = fake_qtw
# ---- 注入结束 ----

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if not os.path.isfile(os.path.join(_PROJ, "gamesay.py")):
    _PROJ = os.path.join(_PROJ, "pc")
sys.path.insert(0, _PROJ)
import gamesay

APPID = "YOUR_XFYUN_APPID"
APIKEY = "YOUR_XFYUN_APIKEY"
APISECRET = "YOUR_XFYUN_APISECRET"


def make_engine():
    logs = []
    return gamesay.AudioEngine(lambda m: logs.append(m)), logs


async def run(swapped):
    engine, logs = make_engine()
    wav = os.path.join(tempfile.gettempdir(), "xf_auto_swap_test.wav")
    try:
        os.remove(wav)
    except Exception:
        pass
    # 模拟填反
    if swapped:
        apikey, apisecret = APISECRET, APIKEY
        tag = "swapped(wrong)"
    else:
        apikey, apisecret = APIKEY, APISECRET
        tag = "correct"
    try:
        await engine._xfyun_speak_to_file(
            "自动交换测试，一二三。", wav,
            APPID, apikey, apisecret,
            voice="xiaoyan",
        )
        size = os.path.getsize(wav) if os.path.exists(wav) else 0
        print(f"[{tag}] SUCCESS wav={size}B")
        print("   logs:", logs[:3])
        return True
    except Exception as e:
        print(f"[{tag}] FAIL: {e}")
        print("   logs:", logs[:3])
        return False


async def main():
    # 1) 正确凭据
    ok1 = await run(swapped=False)
    # 2) 填反凭据 -> 外壳应自动交换重试成功
    ok2 = await run(swapped=True)
    print()
    print("correct-cred: ", "PASS" if ok1 else "FAIL")
    print("auto-swap   : ", "PASS" if ok2 else "FAIL")


if __name__ == "__main__":
    asyncio.run(main())
