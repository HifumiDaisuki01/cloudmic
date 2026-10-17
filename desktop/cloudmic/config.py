from __future__ import annotations
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlsplit

DEFAULT_RELAY = 'https://cloudmic-next.keran.workers.dev'
VOICES = {
    '晓晓 · 温柔自然': 'zh-CN-XiaoxiaoNeural',
    '云希 · 清晰青年': 'zh-CN-YunxiNeural',
    '晓伊 · 轻快亲切': 'zh-CN-XiaoyiNeural',
    '云健 · 沉稳有力': 'zh-CN-YunjianNeural',
    '晓臻 · 台湾女声': 'zh-TW-HsiaoChenNeural',
    '晓曼 · 粤语女声': 'zh-HK-HiuMaanNeural',
    'Jenny · English': 'en-US-JennyNeural',
}

def data_dir() -> Path:
    p = Path(os.environ.get('LOCALAPPDATA') or Path.home() / '.local' / 'share') / 'CloudMicNext'
    p.mkdir(parents=True, exist_ok=True)
    return p


def validate_relay(value: str) -> str:
    value = value.strip().rstrip('/')
    u = urlsplit(value)
    if u.scheme != 'https' or not u.hostname or u.username or u.password or u.query or u.fragment or u.path:
        raise ValueError('中转地址必须是 HTTPS 根地址，例如 https://cloudmic.example.com')
    return value


@dataclass(frozen=True)
class Settings:
    relay: str = DEFAULT_RELAY
    voice: str = 'zh-CN-XiaoxiaoNeural'
    engine: str = 'auto'
    rate: int = 0
    volume: float = 0.85
    device: str = ''
    preview: bool = False
    appearance: str = 'light'
    azure_region: str = 'eastasia'
    # Optional key is kept out of settings.json, in Windows Credential Manager.

    @classmethod
    def load(cls):
        try:
            obj = json.loads((data_dir() / 'settings.json').read_text('utf-8'))
            obj = {k: v for k, v in obj.items() if k in cls.__dataclass_fields__}
            s = cls(**obj)
            validate_relay(s.relay)
            if s.voice not in VOICES.values() or s.engine not in ('auto', 'edge', 'sapi', 'azure'):
                raise ValueError('Invalid settings')
            return cls(**{**asdict(s), 'rate': max(-50, min(50, int(s.rate))), 'volume': max(0.0, min(1.0, float(s.volume)))})
        except (OSError, ValueError, TypeError):
            return cls()

    def save(self):
        target = data_dir() / 'settings.json'
        fd, name = tempfile.mkstemp(dir=target.parent, suffix='.tmp')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(asdict(self), f, ensure_ascii=False, indent=2)
            os.replace(name, target)
        finally:
            Path(name).unlink(missing_ok=True)
