from __future__ import annotations
import asyncio
import json
import queue
import threading
import time
import uuid
from urllib.parse import urlsplit, urlunsplit, urlencode
import aiohttp
import websockets
from .config import Settings, validate_relay
from .speech import SpeechQueue, Synthesizer


class Backend:
    def __init__(self, settings: Settings, play=None):
        if play is None:
            from .audio import play_audio
            play = play_audio
        self.play = play
        self.settings = settings
        self.events = queue.Queue(maxsize=512)
        self.loop = None
        self.room = None
        self.ws = None
        self.closing = False
        self.rotation = False
        self.speaker = None
        self.outbox = None
        self.connected = False
        self.audio_paused = False
        self.thread = threading.Thread(target=self._thread_main, daemon=True, name='CloudMic network')

    def emit(self, kind, **kwargs):
        try: self.events.put_nowait({'type': kind, **kwargs})
        except queue.Full:
            try: self.events.get_nowait()
            except queue.Empty: pass
            try: self.events.put_nowait({'type': kind, **kwargs})
            except queue.Full: pass

    def start(self): self.thread.start()

    def _thread_main(self):
        try: asyncio.run(self.run())
        except Exception as exc: self.emit('error', message=f'后台退出：{type(exc).__name__}')

    def call(self, action, *args):
        if self.loop and not self.closing:
            self.loop.call_soon_threadsafe(action, *args)

    def test(self, text):
        def enqueue():
            if self.audio_paused:
                self.status(str(uuid.uuid4()), 'failed', '正在配置虚拟麦克风，请稍等', 0)
            else:
                self.speaker.enqueue(str(uuid.uuid4()), text, self.settings)
        self.call(enqueue)

    def stop_speech(self):
        if self.speaker: self.call(self.speaker.stop)

    def rotate(self):
        def rotate_now():
            self.rotation = True
            if self.speaker: self.speaker.stop()
            async def revoke():
                if self.ws:
                    try: await self.ws.send('{"type":"revoke"}')
                    except Exception: pass
                    await self.ws.close()
            if self.ws: asyncio.create_task(revoke())
        self.call(rotate_now)

    def close(self):
        def close_now():
            self.closing = True
            if self.speaker: self.speaker.stop()
            if self.ws: asyncio.create_task(self.ws.close())
        self.call(close_now)

    def status(self, id, state, detail, ms):
        obj = {'type': 'status', 'id': id, 'state': state, 'detail': detail, 'ms': ms}
        self.emit('speech', **{k:v for k,v in obj.items() if k != 'type'})
        if self.connected:
            try: self.outbox.put_nowait(obj)
            except asyncio.QueueFull: pass

    async def create_room(self, client):
        relay = validate_relay(self.settings.relay)
        async with client.post(relay + '/api/rooms', json={}) as response:
            data = await response.json()
            if response.status != 200: raise RuntimeError(data.get('error', f'HTTP {response.status}'))
            if data.get('protocol') != 2: raise RuntimeError('中转协议不匹配，请升级客户端')
            self.room = {**data, 'relay': relay}
            self.emit('room', code=data['code'], url=data['pairUrl'], expires=data['pairExpiresAt'])

    async def reader(self, ws):
        async for raw in ws:
            if raw == 'pong': continue
            obj = json.loads(raw)
            if obj.get('type') == 'ready':
                if obj.get('protocol') != 2: raise RuntimeError('中转协议不匹配')
                self.connected = True
                self.emit('connection', state='on', message='中转已连接，等待手机')
            elif obj.get('type') == 'peers':
                self.emit('peers', phones=obj.get('phones', 0))
            elif obj.get('type') == 'say':
                if not self.connected: continue
                id = obj.get('id', '')
                if isinstance(id, str) and 8 <= len(id) <= 64:
                    if self.audio_paused:
                        self.status(id, 'failed', '正在配置虚拟麦克风，请稍等', 0)
                        continue
                    self.speaker.enqueue(id, obj.get('text', ''), self.settings)
            elif obj.get('type') == 'stop': self.speaker.stop()

    async def writer(self, ws):
        while True:
            try: obj = await asyncio.wait_for(self.outbox.get(), timeout=20)
            except TimeoutError:
                await ws.send('ping'); continue
            await ws.send(json.dumps(obj, ensure_ascii=False))

    async def run(self):
        self.loop = asyncio.get_running_loop()
        self.outbox = asyncio.Queue(maxsize=128)
        self.speaker = SpeechQueue(Synthesizer(), self.play, self.status)
        speech_task = asyncio.create_task(self.speaker.run())
        timeout = aiohttp.ClientTimeout(total=12)
        try:
            async with aiohttp.ClientSession(timeout=timeout, trust_env=True) as client:
                delay = 1
                while not self.closing:
                    tasks = []
                    try:
                        if self.rotation:
                            if self.ws and self.ws.state.name == 'OPEN': await self.ws.send('{"type":"revoke"}')
                            self.room = None; self.rotation = False
                        if not self.room or self.room['expiresAt'] <= time.time() * 1000:
                            self.emit('connection', state='wait', message='正在建立安全配对…')
                            await self.create_room(client)
                        u = urlsplit(self.room['relay'])
                        url = urlunsplit(('wss', u.netloc, '/ws', urlencode({'room': self.room['code']}), ''))
                        self.emit('connection', state='wait', message='正在连接中转…')
                        async with websockets.connect(url, open_timeout=12, ping_interval=20,
                                                      ping_timeout=15, close_timeout=3, max_size=8192) as ws:
                            self.ws = ws
                            await ws.send(json.dumps({'type': 'auth', 'role': 'host', 'key': self.room['hostKey']}))
                            tasks = [asyncio.create_task(self.reader(ws)), asyncio.create_task(self.writer(ws))]
                            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                            for task in pending: task.cancel()
                            await asyncio.gather(*pending, return_exceptions=True)
                            for task in done: task.result()
                        delay = 1
                    except websockets.exceptions.InvalidStatus as exc:
                        if exc.response.status_code in (404, 410): self.room = None
                        self.emit('connection', state='off', message='中转握手失败，正在重试…')
                    except websockets.ConnectionClosed as exc:
                        if exc.code in (4001, 4003): self.room = None
                        self.emit('connection', state='off', message='连接中断，正在重连…')
                    except Exception as exc:
                        message = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
                        self.emit('connection', state='off', message=f'连接失败：{message[:100]}，正在重试')
                    finally:
                        self.connected = False
                        self.ws = None
                        for task in tasks: task.cancel()
                        await asyncio.gather(*tasks, return_exceptions=True)
                        self.speaker.stop()
                        while not self.outbox.empty(): self.outbox.get_nowait()
                        self.emit('peers', phones=0)
                    if self.closing: break
                    # Rotation does not wait for exponential backoff.
                    if self.rotation: continue
                    for _ in range(delay * 5):
                        if self.closing or self.rotation: break
                        await asyncio.sleep(0.2)
                    delay = min(15, delay * 2)
        finally:
            self.speaker.stop()
            speech_task.cancel()
            await asyncio.gather(speech_task, return_exceptions=True)
