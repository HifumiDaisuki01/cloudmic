# -*- coding: utf-8 -*-
"""验证 VB-CABLE 检测与安装逻辑"""
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
           "QHBoxLayout", "QLabel", "QLineEdit", "QMainWindow", "QMenu", "QMessageBox",
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
fake_qtc.QTimer = _cls()
fake_qtc.QTimer.singleShot = staticmethod(lambda *a, **k: None)
# ---- 注入结束 ----

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if not os.path.isfile(os.path.join(_PROJ, "gamesay.py")):
    _PROJ = os.path.join(_PROJ, "pc")
sys.path.insert(0, _PROJ)
import gamesay as g

print("cable_installed():", g.AudioEngine.cable_installed())
print("find_cable_device():", g.AudioEngine.find_cable_device())
bundle = g.AudioEngine.cable_bundle_dir()
print("bundle dir exists:", os.path.isdir(bundle))
setup = os.path.join(bundle, "VBCABLE_Setup_x64.exe")
print("setup exe exists:", os.path.isfile(setup))
# 校验核心驱动文件也在包内
print("driver files in bundle:",
      [f for f in os.listdir(bundle) if f.endswith(".sys")][:3])
