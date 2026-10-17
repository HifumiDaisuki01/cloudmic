"""Offline, integrity-checked launch of the original VB-Audio driver installer.

No UAC bypass. Windows asks for elevation when the process is not elevated.
Only the official -i -h arguments are supplied; no automatic system reboot.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import zipfile
from .config import data_dir

ARCHIVE_NAME='VBCABLE_Driver_Pack45.zip'
ARCHIVE_SHA256='b950e39f01af1d04ea623c8f6d8eb9b6ea5c477c637295fabf20631c85116bfb'
SOURCE='https://vb-audio.com/Cable/'
LICENSE_URL='https://vb-audio.com/Services/licensing.htm'
NOTICE='VB-CABLE 由 VB-Audio 提供，是 donationware；欢迎支持原作者。'

@dataclass(frozen=True)
class InstallResult:
    state: str
    message: str
    exit_code: int | None = None


def archive_path():
    root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))
    return root/'vendor'/ARCHIVE_NAME


def prepare_installer(archive: Path | None = None, directory: Path | None = None):
    """Retain every file. Installing with just the setup EXE does not work."""
    archive=archive or archive_path()
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=ARCHIVE_SHA256:
        raise RuntimeError('内置 VB-CABLE 安装包校验失败，请重新下载 CloudMic')
    directory=directory or data_dir()/'drivers'/'VB-CABLE-Pack45'
    directory.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive) as package:
        for member in package.infolist():
            target=(directory/member.filename).resolve()
            if not target.is_relative_to(directory.resolve()):raise RuntimeError('驱动包路径无效')
        package.extractall(directory)
        for member in package.infolist():
            if not member.is_dir() and (directory/member.filename).read_bytes()!=package.read(member):
                raise RuntimeError('驱动包解压校验失败')
    setup=directory/'VBCABLE_Setup_x64.exe'
    if not setup.is_file():raise RuntimeError('内置驱动安装器缺失')
    return setup


def boot_id():
    if os.name!='nt':return 0
    import ctypes
    ticks=ctypes.windll.kernel32.GetTickCount64
    ticks.restype=ctypes.c_ulonglong
    return int(time.time()-ticks()/1000)


def pending_reboot():
    try:
        state=json.loads((data_dir()/'driver-state.json').read_text('utf-8'))
        return state.get('installed') is True and abs(state.get('boot',0)-boot_id())<120
    except (OSError,ValueError,TypeError):return False


def record_install():
    (data_dir()/'driver-state.json').write_text(json.dumps({'installed':True,'boot':boot_id()}),encoding='utf-8')


def clear_pending():
    (data_dir()/'driver-state.json').unlink(missing_ok=True)


def is_windows():
    return os.name=='nt'


def launch_elevated(setup: Path):
    """Launch silent install and wait on its actual elevated process handle."""
    if not is_windows():raise RuntimeError('驱动安装只支持 Windows')
    from win32com.shell import shell, shellcon
    import pywintypes
    import win32api
    import win32event
    import win32process
    try:
        info=shell.ShellExecuteEx(fMask=shellcon.SEE_MASK_NOCLOSEPROCESS,
            lpVerb='runas',lpFile=str(setup),lpParameters='-i -h',
            lpDirectory=str(setup.parent),nShow=0)
    except pywintypes.error as exc:
        if getattr(exc,'winerror',exc.args[0])==1223:return InstallResult('cancelled','管理员确认已取消，可点击“安装虚拟麦”重试。')
        raise
    handle=info.get('hProcess')
    if not handle:raise RuntimeError('无法取得驱动安装进程')
    try:
        # A long install isn't killed; avoid leaving the UI stuck indefinitely.
        if win32event.WaitForSingleObject(handle,180000)==win32event.WAIT_TIMEOUT:
            return InstallResult('timeout','安装程序仍在运行，请稍后刷新设备，或按系统提示重启。')
        code=win32process.GetExitCodeProcess(handle)
    finally:
        if hasattr(handle,'Close'):handle.Close()
        else:win32api.CloseHandle(handle)
    if code not in (0,3010,1641):
        return InstallResult('failed',f'VB-CABLE 安装器返回 {code}，可点击“安装虚拟麦”重试。',code)
    record_install()
    return InstallResult('installed','驱动安装完成，正在重新检测音频设备…',code)


def install():
    try:return launch_elevated(prepare_installer())
    except Exception as exc:return InstallResult('failed',str(exc)[:180])


def install_api_available():
    """Import/packaging check only. Does not elevate or install anything."""
    if not is_windows():return False
    from win32com.shell import shell, shellcon
    import win32api, win32event, win32process
    return (callable(shell.ShellExecuteEx) and bool(shellcon.SEE_MASK_NOCLOSEPROCESS)
        and callable(win32event.WaitForSingleObject) and callable(win32process.GetExitCodeProcess)
        and callable(win32api.CloseHandle))
