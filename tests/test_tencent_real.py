# -*- coding: utf-8 -*-
"""用用户真实密钥实测腾讯云 TTS 合成（标准音色 1001）"""
import asyncio, os, sys, tempfile, types

# ---- 假 PySide6 注入 ----
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
                             "text": lambda self: "",
                             "setEchoMode": lambda self, *x: None,
                             "setCurrentIndex": lambda self, *x: None,
                             "lineEdit": lambda self: None,
                             "setPlaceholderText": lambda self, *x: None,
                             "setVisible": lambda self, *x: None,
                             "setWordWrap": lambda self, *x: None,
                             "currentIndexChanged": lambda self: None,
                             "editingFinished": lambda self: None,
                             "valueChanged": lambda self: None,
                             "currentIndex": lambda self: 0,
                             "count": lambda self: 0,
                             "setRange": lambda self, *x: None,
                             "setValue": lambda self, *x: None,
                             "value": lambda self: 100,
                             })()

for _n in ["QEvent", "QObject", "QThread", "QTimer", "QApplication", "QComboBox", "QFrame",
           "QHBoxLayout", "QLabel", "QLineEdit", "QMainWindow", "QMenu",
           "QPushButton", "QScrollArea", "QSlider", "QSizePolicy", "QStyle",
           "QSystemTrayIcon", "QTextEdit", "QVBoxLayout", "QWidget", "QAction",
           "QCloseEvent", "QIcon", "QPixmap"]:
    setattr(fake_qtc, _n, _cls())
    setattr(fake_qtg, _n, _cls())
    setattr(fake_qtw, _n, _cls())
fake_qtc.Signal = lambda *a, **k: None
fake_qtc.Qt = types.SimpleNamespace(
    AlignCenter=0, AlignHCenter=0, RichText=0, Horizontal=0,
    KeepAspectRatio=0, SmoothTransformation=0, NoFrame=0,
    Preferred=0, StandardPixmap=0, DoubleClick=0, Information=0, ComputerIcon=0,
)
fake_qtc.QLineEdit = _cls()
fake_qtc.QLineEdit.Password = 1
fake_qtw.QLineEdit.Password = 1
fake_qtw.QLineEdit = fake_qtc.QLineEdit
fake_qtw.QStyle = fake_qtw
# ---- 注入结束 ----

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if not os.path.isfile(os.path.join(_PROJ, "gamesay.py")):
    _PROJ = os.path.join(_PROJ, "pc")
sys.path.insert(0, _PROJ)
import gamesay

SECRET_ID = "YOUR_TENCENT_SECRET_ID"
SECRET_KEY = "YOUR_TENCENT_SECRET_KEY"


async def test_voice(vt, label):
    engine = gamesay.AudioEngine(lambda m: None)
    wav = os.path.join(tempfile.gettempdir(), f"tx_{vt}.wav")
    try:
        os.remove(wav)
    except Exception:
        pass
    try:
        await engine._tencent_speak_to_file(
            "大家好，我是云麦，正在测试腾讯云语音合成。", wav,
            SECRET_ID, SECRET_KEY, voice_type=str(vt), speed=0, volume=5,
        )
        size = os.path.getsize(wav) if os.path.exists(wav) else 0
        import wave
        with wave.open(wav, "rb") as w:
            sr, ch, frames = w.getframerate(), w.getnchannels(), w.getnframes()
        dur = frames / sr
        print(f"[OK] {label} vt={vt}: {size}B, {sr}Hz/{ch}ch, {dur:.2f}s")
        return True
    except Exception as e:
        print(f"[FAIL] {label} vt={vt}: {str(e)[:200]}")
        return False


async def main():
    print("=== 标准音色 ===")
    ok1 = await test_voice(1001, "智瑜(标准)")
    ok2 = await test_voice(1018, "智靖(标准)")
    ok3 = await test_voice(100510000, "智逍遥(精品)")
    print("=== 大模型音色 ===")
    ok4 = await test_voice(501000, "智斌(大模型)")
    print("=== 超自然音色 ===")
    ok5 = await test_voice(502001, "智小柔(超自然)")
    print()
    passed = sum([ok1, ok2, ok3, ok4, ok5])
    print(f"通过 {passed}/5")


if __name__ == "__main__":
    asyncio.run(main())
