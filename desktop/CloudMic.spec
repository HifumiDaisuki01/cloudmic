# Build with: python -m PyInstaller --clean --noconfirm CloudMic.spec
from PyInstaller.utils.hooks import collect_data_files, collect_submodules
from pathlib import Path
root = Path(SPECPATH).parent
import sys
sys.path.insert(0, SPECPATH)
from cloudmic.branding import make_mark
icon = Path(SPECPATH) / 'build' / 'cloudmic.ico'
icon.parent.mkdir(exist_ok=True)
make_mark().save(icon, format='ICO', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
notices = [(str(root / 'THIRD_PARTY_NOTICES.md'), '.'), (str(root / 'LICENSE'), '.')]
a = Analysis(['main.py'], pathex=[SPECPATH],
    binaries=[], datas=collect_data_files('customtkinter') + notices + [(str(Path(SPECPATH) / 'licenses'), 'licenses')],
    hiddenimports=['PIL._tkinter_finder', 'win32com.client', 'win32timezone', 'win32cred', 'pythoncom'] + collect_submodules('pystray'),
    excludes=['numpy', 'PySide6', 'PyQt5', 'matplotlib', 'scipy', 'pandas', 'pytest', 'IPython'],
    noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='CloudMic',
    debug=False, strip=False, upx=False, console=False, disable_windowed_traceback=False,
    version='version.txt', icon=str(icon))
