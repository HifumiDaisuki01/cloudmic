import hashlib
import json
from pathlib import Path
import sys
import types
import zipfile
import pytest
from cloudmic import driver


def archive(tmp_path,monkeypatch,unsafe=False):
    path=tmp_path/'driver.zip'
    with zipfile.ZipFile(path,'w') as z:
        z.writestr('VBCABLE_Setup_x64.exe',b'MZ-test-installer')
        z.writestr('driver.inf',b'inf')
        z.writestr('driver.sys',b'sys')
        z.writestr('readme.txt',b'original license')
        if unsafe:z.writestr('../outside.txt',b'bad')
    monkeypatch.setattr(driver,'ARCHIVE_SHA256',hashlib.sha256(path.read_bytes()).hexdigest())
    return path


def test_complete_package_is_verified_and_extracted(tmp_path,monkeypatch):
    bundle=archive(tmp_path,monkeypatch)
    setup=driver.prepare_installer(bundle,tmp_path/'out')
    assert setup.name=='VBCABLE_Setup_x64.exe'
    assert (setup.parent/'driver.inf').read_bytes()==b'inf'
    assert (setup.parent/'driver.sys').read_bytes()==b'sys'
    assert (setup.parent/'readme.txt').read_bytes()==b'original license'


def test_modified_archive_is_rejected_before_extraction(tmp_path,monkeypatch):
    bundle=archive(tmp_path,monkeypatch)
    bundle.write_bytes(bundle.read_bytes()+b'changed')
    with pytest.raises(RuntimeError,match='校验失败'):driver.prepare_installer(bundle,tmp_path/'out')
    assert not (tmp_path/'out').exists()


def test_archive_path_traversal_is_rejected(tmp_path,monkeypatch):
    bundle=archive(tmp_path,monkeypatch,unsafe=True)
    with pytest.raises(RuntimeError,match='路径无效'):driver.prepare_installer(bundle,tmp_path/'out')
    assert not (tmp_path/'outside.txt').exists()


def test_success_marker_suppresses_install_until_reboot(tmp_path,monkeypatch):
    monkeypatch.setattr(driver,'data_dir',lambda:tmp_path)
    monkeypatch.setattr(driver,'boot_id',lambda:1000000)
    assert not driver.pending_reboot()
    driver.record_install();assert driver.pending_reboot()
    monkeypatch.setattr(driver,'boot_id',lambda:1005000)
    assert not driver.pending_reboot()
    driver.clear_pending();assert not (tmp_path/'driver-state.json').exists()


def windows_api(monkeypatch,exit_code=0,timeout=False,cancel=False):
    calls={}
    class WinError(Exception):
        winerror=1223
    def execute(**kwargs):
        calls.update(kwargs)
        if cancel:raise WinError(1223,'cancelled')
        return {'hProcess':123}
    monkeypatch.setattr(driver,'is_windows',lambda:True)
    package=types.ModuleType('win32com');package.__path__=[]
    shell=types.ModuleType('win32com.shell')
    shell.shell=types.SimpleNamespace(ShellExecuteEx=execute)
    shell.shellcon=types.SimpleNamespace(SEE_MASK_NOCLOSEPROCESS=64)
    modules={
        'win32com':package,'win32com.shell':shell,
        'pywintypes':types.SimpleNamespace(error=WinError),
        'win32api':types.SimpleNamespace(CloseHandle=lambda h:calls.update(closed=h)),
        'win32event':types.SimpleNamespace(WaitForSingleObject=lambda h,t:258 if timeout else 0,WAIT_TIMEOUT=258),
        'win32process':types.SimpleNamespace(GetExitCodeProcess=lambda h:exit_code),
    }
    for name,module in modules.items():monkeypatch.setitem(sys.modules,name,module)
    monkeypatch.setattr(driver,'record_install',lambda:calls.update(recorded=True))
    return calls


@pytest.mark.parametrize('code',[0,3010])
def test_silent_install_uses_uac_and_complete_working_directory(monkeypatch,tmp_path,code):
    calls=windows_api(monkeypatch,exit_code=code)
    setup=tmp_path/'VBCABLE_Setup_x64.exe'
    result=driver.launch_elevated(setup)
    assert result.state=='installed'
    assert calls['lpVerb']=='runas'
    assert calls['lpParameters']=='-i -h'
    assert calls['lpDirectory']==str(tmp_path)
    assert calls['recorded'] and calls['closed']==123


def test_cancelled_uac_is_reported_without_bypass(monkeypatch,tmp_path):
    calls=windows_api(monkeypatch,cancel=True)
    assert driver.launch_elevated(tmp_path/'setup.exe').state=='cancelled'
    assert 'recorded' not in calls


def test_timeout_does_not_claim_success_or_kill_installer(monkeypatch,tmp_path):
    calls=windows_api(monkeypatch,timeout=True)
    assert driver.launch_elevated(tmp_path/'setup.exe').state=='timeout'
    assert 'recorded' not in calls
    assert calls['closed']==123


def test_error_exit_is_not_saved_as_installed(monkeypatch,tmp_path):
    calls=windows_api(monkeypatch,exit_code=1)
    assert driver.launch_elevated(tmp_path/'setup.exe').state=='failed'
    assert 'recorded' not in calls
