# -*- coding: utf-8 -*-
"""测试 ensure_builtin_cfg：空配置自动填充 + 讯飞 Key/Secret 反序自动纠正"""
import os, sys, types

# ---- 完整假 PySide6 注入 ----
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
                             "setEditText": lambda self, *x: None,
                             "lineEdit": lambda self: None,
                             "setPlaceholderText": lambda self, *x: None,
                             "setVisible": lambda self, *x: None,
                             "setWordWrap": lambda self, *x: None,
                             "setFixedWidth": lambda self, *x: None,
                             "setFixedSize": lambda self, *x: None,
                             "setFixedHeight": lambda self, *x: None,
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
                             "count": lambda self: 0,
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
import gamesay as g

# ---- 配置隔离：测试不碰真实 config.json，全部写入临时文件 ----
import tempfile
g.cfg_path = lambda: os.path.join(tempfile.gettempdir(), "cloudmic_test_config.json")

# 场景1：空 cfg（全新机器首次启动）
# 公开版：内置密钥为空，只补默认配置项（音色分类等），密钥留给用户填
cfg1 = {}
cfg1 = g.ensure_builtin_cfg(cfg1)
print("scene1 empty cfg ->")
print("  xfyun_appid:", repr(cfg1.get("xfyun_appid", "<unset>")))
print("  tx_secret_id:", repr(cfg1.get("tx_secret_id", "<unset>")))
print("  tx_cat:", cfg1["tx_cat"], "| tx_voice:", cfg1["tx_voice"])
assert not cfg1.get("xfyun_appid")           # 公开版不内置密钥（空或未设置）
assert not cfg1.get("tx_secret_id")          # 公开版不内置密钥
assert cfg1["tx_cat"] == "标准语音合成-精品音色"
assert cfg1["tx_voice"] == "1001"

# 场景2：讯飞 Key/Secret 反序（UI 填反写回的旧 config）——用 mock 值模拟（前缀触发防呆）
cfg2 = {
    "xfyun_apikey": "MDBhNDRlMOCKKEY0123456789abcdef",
    "xfyun_apisecret": "05126c9cMOCKSECRET0123456789abcdef",
}
cfg2 = g.ensure_builtin_cfg(cfg2)
print("scene2 swapped creds ->")
print("  apikey now:", cfg2["xfyun_apikey"][:12], "| apisecret now:", cfg2["xfyun_apisecret"][:12])
assert cfg2["xfyun_apikey"] == "05126c9cMOCKSECRET0123456789abcdef"
assert cfg2["xfyun_apisecret"] == "MDBhNDRlMOCKKEY0123456789abcdef"

print()
print("ALL ASSERTIONS PASSED")
