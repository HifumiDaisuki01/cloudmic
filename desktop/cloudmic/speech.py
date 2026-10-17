from __future__ import annotations
import asyncio
from collections import OrderedDict
import os
from pathlib import Path
import re
import tempfile
import threading
import time
from dataclasses import dataclass, field
from typing import Callable
import aiohttp
import edge_tts
from .config import Settings

MAX_TEXT = 500
MAX_QUEUE = 8
MAX_AGE = 30.0


def segments(text: str):
    # Read the first sentence before waiting for a long paragraph to synthesize.
    result, current = [], ''
    for part in re.split(r'(?<=[。！？!?；;\n])', text):
        while part:
            room = 80 - len(current)
            current += part[:room]
            part = part[room:]
            if len(current) >= 80 or current.endswith(('。', '！', '？', '!', '?', ';', '；', '\n')):
                if current.strip(): result.append(current.strip())
                current = ''
    if current.strip(): result.append(current.strip())
    return result


def sapi_bytes(text: str, rate: int, cancel: threading.Event) -> bytes:
    if os.name != 'nt':
        raise RuntimeError('本地语音只支持 Windows')
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    path = None
    try:
        fd, path = tempfile.mkstemp(suffix='.wav', prefix='cloudmic-')
        os.close(fd)
        voice = win32com.client.Dispatch('SAPI.SpVoice')
        voice.Rate = max(-10, min(10, rate // 5))
        stream = win32com.client.Dispatch('SAPI.SpFileStream')
        stream.Open(path, 3)
        try:
            voice.AudioOutputStream = stream
            voice.Speak(text, 1)  # Async SAPI; allow Stop to purge it.
            while not voice.WaitUntilDone(40):
                if cancel.is_set():
                    voice.Speak('', 3)
                    raise RuntimeError('已取消')
        finally:
            stream.Close()
        return Path(path).read_bytes()
    finally:
        if path: Path(path).unlink(missing_ok=True)
        pythoncom.CoUninitialize()


def azure_key():
    if os.name != 'nt': return ''
    try:
        import win32cred
        return win32cred.CredRead('CloudMicNext/Azure', win32cred.CRED_TYPE_GENERIC)['CredentialBlob'].decode('utf-16-le')
    except Exception: return ''


def save_azure_key(value):
    import win32cred
    if value:
        win32cred.CredWrite({'Type': win32cred.CRED_TYPE_GENERIC, 'TargetName': 'CloudMicNext/Azure',
                            'UserName': 'CloudMic', 'CredentialBlob': value.encode('utf-16-le'),
                            'Persist': win32cred.CRED_PERSIST_LOCAL_MACHINE}, 0)
    else:
        try: win32cred.CredDelete('CloudMicNext/Azure', win32cred.CRED_TYPE_GENERIC)
        except Exception: pass


class Synthesizer:
    def __init__(self):
        self.cache = OrderedDict()
        self.cache_bytes = 0
        self.semaphore = asyncio.Semaphore(2)

    async def synthesize(self, text: str, cfg: Settings, cancel: threading.Event):
        key = (text, cfg.engine, cfg.voice, cfg.rate, cfg.azure_region)
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        async with self.semaphore:
            if cfg.engine == 'sapi':
                result = (await asyncio.to_thread(sapi_bytes, text, cfg.rate, cancel), '本地语音')
            elif cfg.engine == 'azure':
                from xml.sax.saxutils import escape
                token = azure_key()
                if not token: raise RuntimeError('请在设置中填写 Azure Speech 密钥')
                if not re.fullmatch(r'[a-z0-9-]{2,40}', cfg.azure_region): raise RuntimeError('Azure 区域无效')
                body = f'<speak version="1.0" xml:lang="zh-CN"><voice name="{cfg.voice}"><prosody rate="{cfg.rate:+d}%">{escape(text)}</prosody></voice></speak>'
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10), trust_env=True) as client:
                    async with client.post(f'https://{cfg.azure_region}.tts.speech.microsoft.com/cognitiveservices/v1', data=body.encode(),
                                           headers={'Ocp-Apim-Subscription-Key': token, 'Content-Type': 'application/ssml+xml',
                                                    'X-Microsoft-OutputFormat': 'audio-24khz-48kbitrate-mono-mp3'}) as response:
                        if response.status != 200: raise RuntimeError(f'Azure 合成失败（HTTP {response.status}）')
                        data = await response.read()
                        if not data or len(data) > 4_000_000: raise RuntimeError('Azure 返回音频无效')
                        result = (data, 'Azure 神经语音')
            else:
                try:
                    data = bytearray()
                    async with asyncio.timeout(9):
                        comm = edge_tts.Communicate(text, cfg.voice, rate=f'{cfg.rate:+d}%',
                                                   proxy=os.environ.get('HTTPS_PROXY') or None)
                        async for chunk in comm.stream():
                            if cancel.is_set(): raise asyncio.CancelledError
                            if chunk['type'] == 'audio': data.extend(chunk['data'])
                            if len(data) > 4_000_000: raise RuntimeError('音频过大')
                    if not data: raise RuntimeError('在线服务未返回声音')
                    result = (bytes(data), '在线自然语音')
                except asyncio.CancelledError: raise
                except Exception:
                    if cfg.engine != 'auto': raise RuntimeError('在线语音暂不可用，请换网络或使用本地语音') from None
                    result = (await asyncio.to_thread(sapi_bytes, text, cfg.rate, cancel), '在线失败，已用本地语音')
        if cancel.is_set(): raise asyncio.CancelledError
        # Memory-only LRU. Conversation text/audio never written to a history file.
        self.cache[key] = result
        self.cache_bytes += len(result[0])
        while len(self.cache) > 48 or self.cache_bytes > 12_000_000:
            _, old = self.cache.popitem(last=False)
            self.cache_bytes -= len(old[0])
        return result


@dataclass
class Utterance:
    id: str
    text: str
    cfg: Settings
    created: float = field(default_factory=time.monotonic)
    cancel: threading.Event = field(default_factory=threading.Event)


class SpeechQueue:
    """One speaker; at most eight waiting messages, independent of WS receiver."""
    def __init__(self, synth: Synthesizer, play: Callable, status: Callable):
        self.synth, self.play, self.status = synth, play, status
        self.queue = asyncio.Queue(maxsize=MAX_QUEUE)
        self.current = None
        self.synthesis = None
        self.seen = OrderedDict()

    def enqueue(self, id: str, text: str, cfg: Settings):
        if id in self.seen:
            self.status(id, self.seen[id], '重复消息已忽略', 0)
            return False
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT:
            self.status(id, 'failed', '文字须为 1–500 字', 0); return False
        item = Utterance(id, text.strip(), cfg)
        try: self.queue.put_nowait(item)
        except asyncio.QueueFull:
            self.status(id, 'failed', '排队已满，请稍后再发', 0); return False
        self.remember(id, 'queued')
        self.status(id, 'queued', '', 0)
        return True

    def remember(self, id, state):
        self.seen[id] = state
        self.seen.move_to_end(id)
        while len(self.seen) > 256: self.seen.popitem(last=False)

    def stop(self):
        if self.current: self.current.cancel.set()
        if self.synthesis: self.synthesis.cancel()
        while not self.queue.empty():
            item = self.queue.get_nowait()
            self.remember(item.id, 'cancelled')
            self.status(item.id, 'cancelled', '已清空队列', 0)
            self.queue.task_done()

    async def run(self):
        while True:
            item = await self.queue.get()
            self.current = item
            try:
                if time.monotonic() - item.created > MAX_AGE:
                    self.remember(item.id, 'cancelled')
                    self.status(item.id, 'cancelled', '消息超过 30 秒，已跳过', 0)
                    continue
                self.status(item.id, 'synthesizing', '', 0)
                first = True
                parts = segments(item.text)
                for part in parts:
                    if item.cancel.is_set(): raise asyncio.CancelledError
                    self.synthesis = asyncio.create_task(self.synth.synthesize(part, item.cfg, item.cancel))
                    audio, engine = await self.synthesis
                    self.synthesis = None
                    if item.cancel.is_set(): raise asyncio.CancelledError
                    if first:
                        self.status(item.id, 'playing', engine, int((time.monotonic() - item.created) * 1000)); first = False
                    await asyncio.to_thread(self.play, audio, item.cfg.device, item.cfg.preview, item.cfg.volume, item.cancel)
                state = 'cancelled' if item.cancel.is_set() else 'done'
                self.remember(item.id, state); self.status(item.id, state, '', 0)
            except asyncio.CancelledError:
                self.remember(item.id, 'cancelled'); self.status(item.id, 'cancelled', '', 0)
                # Child synth cancellation means Stop; cancellation of the runner means shutdown.
                if asyncio.current_task().cancelling(): raise
            except Exception as exc:
                self.remember(item.id, 'failed'); self.status(item.id, 'failed', str(exc)[:160], 0)
            finally:
                self.current = None; self.synthesis = None; self.queue.task_done()
