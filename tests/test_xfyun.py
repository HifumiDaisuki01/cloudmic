# -*- coding: utf-8 -*-
"""讯飞 v2/tts 连通性测试：用用户给的凭据完整走一遍握手+合成"""
import asyncio, base64, hashlib, hmac, json, email.utils, urllib.parse, sys, os, struct

APPID = "YOUR_XFYUN_APPID"
APIKEY = "YOUR_XFYUN_APIKEY"
APISECRET = "YOUR_XFYUN_APISECRET"

HOST = "tts-api.xfyun.cn"
PATH = "/v2/tts"


def build_url(apisecret=None, date_override=None):
    apisecret = apisecret or APISECRET
    date = date_override or email.utils.formatdate(usegmt=True)
    print(f"[date] {date!r}")
    sig_origin = f"host: {HOST}\ndate: {date}\nGET {PATH} HTTP/1.1"
    print(f"[sig_origin] {sig_origin!r}")
    sig = base64.b64encode(
        hmac.new(apisecret.encode("utf-8"), sig_origin.encode("utf-8"), hashlib.sha256).digest()
    ).decode("utf-8")
    auth_origin = (
        f'api_key="{APIKEY}", algorithm="hmac-sha256", '
        f'headers="host date request-line", signature="{sig}"'
    )
    print(f"[auth_origin] {auth_origin}")
    auth = base64.b64encode(auth_origin.encode("utf-8")).decode("utf-8")
    url = (f"wss://{HOST}{PATH}"
           f"?authorization={urllib.parse.quote(auth)}"
           f"&date={urllib.parse.quote(date)}"
           f"&host={HOST}")
    return url


def pcm16_to_wav(pcm, sr=16000):
    n = len(pcm) // 2
    hdr = struct.pack("<4sI4s4sIHHIIHH4sI", b"RIFF", 36 + n * 2, b"WAVE",
                      b"fmt ", 16, 1, 1, sr, sr * 2, 2, 16, b"data", n * 2)
    return hdr + pcm


async def test():
    import websockets
    print(f"websockets {websockets.__version__}")
    url = build_url()
    try:
        ws = await asyncio.wait_for(websockets.connect(url, ping_interval=10, ping_timeout=10), timeout=10)
        print("[connect] OK, handshake success!")
    except Exception as e:
        print(f"[connect] FAILED: {type(e).__name__}: {e}")
        # 尝试拿到响应体细节
        for attr in ("status_code", "status", "headers", "body"):
            v = getattr(e, attr, None)
            if v is not None:
                try:
                    print(f"  {attr} = {v}")
                except Exception:
                    pass
        # websockets 13+ 的 InvalidStatus 里有 response
        resp = getattr(e, "response", None)
        if resp is not None:
            try:
                print(f"  response.status = {resp.status_code}")
                print(f"  response.headers = {resp.headers}")
                print(f"  response.body = {getattr(resp, 'body', None)!r}")
            except Exception as ex:
                print(f"  (resp parse err {ex})")
        return False
    # 发请求
    payload = {
        "common": {"app_id": APPID},
        "business": {
            "aue": "raw", "auf": "audio/L16;rate=16000",
            "vcn": "xiaoyan", "speed": 50, "volume": 50, "pitch": 50, "tte": "UTF8",
        },
        "data": {"status": 2, "text": base64.b64encode("你好，我是云麦，正在测试语音合成。".encode("utf-8")).decode("utf-8")},
    }
    await ws.send(json.dumps(payload))
    print("[send] payload sent")
    pcm = bytearray()
    while True:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=15)
        except asyncio.TimeoutError:
            print("[recv] TIMEOUT")
            break
        msg = json.loads(raw)
        code = msg.get("code")
        if code != 0:
            print(f"[recv] ERROR code={code} message={msg.get('message')}")
            # 打印整个返回便于诊断
            print(f"[recv] full msg = {json.dumps(msg, ensure_ascii=False)[:500]}")
            break
        d = msg.get("data") or {}
        if d.get("audio"):
            pcm += base64.b64decode(d["audio"])
        if d.get("status") == 2:
            break
    await ws.close()
    if pcm:
        out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "xf_test.wav")
        with open(out, "wb") as f:
            f.write(pcm16_to_wav(bytes(pcm)))
        print(f"[result] SUCCESS! got {len(pcm)} bytes PCM -> {out}")
        return True
    print("[result] NO AUDIO")
    return False


if __name__ == "__main__":
    ok = asyncio.run(test())
    sys.exit(0 if ok else 1)
