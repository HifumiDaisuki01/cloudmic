#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CloudMic 中转服务器
===================
单文件部署：既提供手机端网页（/），又负责手机 <-> 电脑端的 WebSocket 消息中转。

部署（襄阳 61.184.23.165:23777）：
    pip3 install websockets -i https://mirrors.cloud.tencent.com/pypi/simple
    nohup python3 server.py --port 23777 > cloudmic.log 2>&1 &

原理：
    PC 端启动后生成随机配对 token，扫码/输码让手机端带上同一 token 连接。
    服务器以 token 为房间 ID：一个 PC + 多台手机，消息双向转发。

协议（JSON 文本帧，单向每条消息均透传）：
    phone -> server -> pc   : {"type":"say","text":"...","rate":1.0,"vol":1.0}
    pc    -> server -> phone: {"type":"state","playing":true} 等状态广播
"""

import argparse
import asyncio
import json
import logging
import os
import secrets
import sys
import time
from urllib.parse import parse_qs, urlsplit

import websockets

# 兼容 websockets 10~16：Headers/Response 位置、process_request 签名不同
try:
    from websockets.datastructures import Headers
    from websockets.http11 import Response
    WS_NEW = int(websockets.__version__.split(".")[0]) >= 14
except ImportError:
    from websockets.http import Headers
    WS_NEW = False

LOG = logging.getLogger("cloudmic")
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"

MAX_FRAME = 65536  # 单条消息上限 64KB，防滥用


def ws_state_open(ws):
    """跨版本判断连接是否 OPEN"""
    try:
        return ws.state == websockets.protocol.State.OPEN
    except Exception:
        return True

# ---------------------------------------------------------------------------
# 手机端网页：优先读取同目录 index.html（便于修改 UI），否则用内嵌兜底
# ---------------------------------------------------------------------------
_EXT_HTML = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")
if os.path.isfile(_EXT_HTML):
    with open(_EXT_HTML, "r", encoding="utf-8") as _f:
        INDEX_HTML = _f.read()
else:
    INDEX_HTML = (
        '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>CloudMic</title></head>"
        '<body style="font-family:sans-serif;background:#0d1117;color:#e6edf3;'
        'display:flex;align-items:center;justify-content:center;height:100vh;margin:0">'
        '<p>缺少 index.html，请将其与本文件放在同一目录后重启</p></body></html>'
    )


# ---------------------------------------------------------------------------
# 房间管理：token -> {"pc": ws|None, "phones": set[ws], "created": ts}
# SHORT_CODES: 4位配对码 -> 长 token（PC 注册时登记，手机输码时解析）
# ---------------------------------------------------------------------------
ROOMS = {}
SHORT_CODES = {}
LAST_CLEAN = time.time()


def resolve_token(tk):
    """手机端可能带 pc-XXXX 短码，解析为完整 token；其余原样返回"""
    if len(tk) == 7 and tk.startswith("pc-"):
        code = tk[3:]
        if code in SHORT_CODES:
            return SHORT_CODES[code]
    return tk


def get_room(tk):
    if tk not in ROOMS:
        ROOMS[tk] = {"pc": None, "phones": set(), "created": time.time()}
    return ROOMS[tk]


def room_broadcast(room, obj, exclude=None):
    """广播 JSON 给房间内所有手机（可选排除某连接）"""
    if not room:
        return
    raw = json.dumps(obj, ensure_ascii=False)
    dead = []
    for ph in room["phones"]:
        if ph is exclude:
            continue
        try:
            asyncio.ensure_future(ph.send(raw))
        except Exception:
            dead.append(ph)
    for ph in dead:
        room["phones"].discard(ph)


def clean_rooms():
    """清理空房间与过期短码"""
    global LAST_CLEAN
    now = time.time()
    if now - LAST_CLEAN < 120:
        return
    LAST_CLEAN = now
    for tk in [k for k, r in ROOMS.items() if r["pc"] is None and not r["phones"]]:
        del ROOMS[tk]
    for code, tk in list(SHORT_CODES.items()):
        if tk not in ROOMS:
            del SHORT_CODES[code]


async def handle_conn(ws):
    """处理单个 WS 连接"""
    tk = None
    role = None
    room = None
    try:
        # ---- 解析查询参数（兼容新旧版本 request 对象） ----
        req = getattr(ws, "request", None)
        raw_path = getattr(req, "path", None) or getattr(ws, "request_path", "/ws") or "/ws"
        url = urlsplit(raw_path)
        query = parse_qs(url.query)

        def qget(name, default=""):
            v = query.get(name, [])
            if isinstance(v, list):
                return v[0] if v else default
            return v or default

        tk = qget("tk", "").strip().lower()
        role = qget("role", "phone").strip().lower()
        code = qget("code", "").strip().lower()

        if not tk or len(tk) > 64:
            await ws.send(json.dumps({"type": "err", "msg": "bad token"}, ensure_ascii=False))
            return
        if role not in ("pc", "phone"):
            role = "phone"

        # 手机端短码解析；PC 端注册短码
        if role == "pc":
            if len(code) == 4 and code.isalnum():
                SHORT_CODES[code] = tk
        else:
            tk = resolve_token(tk)

        room = get_room(tk)
        LOG.info("connect role=%s tk=%s peers=%d", role, tk[:10] + "…", len(room["phones"]) + (1 if room["pc"] else 0))

        # ---- PC 端：抢占 / 通知手机端 ----
        if role == "pc":
            old = room["pc"]
            if old is not None and old is not ws and ws_state_open(old):
                try:
                    await old.send(json.dumps({"type": "kicked", "msg": "pc replaced"}, ensure_ascii=False))
                except Exception:
                    pass
                try:
                    await old.close()
                except Exception:
                    pass
            room["pc"] = ws
            # 通知已连手机：电脑上线了
            room_broadcast(room, {"type": "pc-online"})
        else:
            room["phones"].add(ws)
            if room["pc"] is None:
                await ws.send(json.dumps({"type": "nopc", "msg": "pc offline"}, ensure_ascii=False))
            else:
                await ws.send(json.dumps({"type": "pc-online"}))

        # ---- 消息转发循环 ----
        async for raw in ws:
            if len(raw) > MAX_FRAME:
                continue
            try:
                obj = json.loads(raw)
            except Exception:
                continue
            mtype = obj.get("type", "")
            if role == "pc":
                # 电脑端 -> 手机端（状态广播）
                room_broadcast(room, obj, exclude=ws)
            elif role == "phone":
                # 手机端 -> 电脑端：仅转发给房间 PC
                if mtype == "say":
                    pc = room["pc"]
                    if pc is not None and ws_state_open(pc):
                        await pc.send(raw)
                        # 回执给手机（用于聊天记录展示"已读给队友"）
                        await ws.send(json.dumps({"type": "sayback", "text": obj.get("text", "")}, ensure_ascii=False))
                    else:
                        await ws.send(json.dumps({"type": "nopc"}, ensure_ascii=False))
                # 其余（pong 等）忽略

    except websockets.exceptions.ConnectionClosed:
        pass
    except Exception as e:
        LOG.warning("conn error: %s", e)
    finally:
        if room is not None:
            if role == "pc" and room["pc"] is ws:
                room["pc"] = None
                room_broadcast(room, {"type": "pc-offline"})
            if role == "phone":
                room["phones"].discard(ws)
        clean_rooms()
        LOG.info("disconnect role=%s tk=%s", role, (tk or "?")[:10] + "…")


def main():
    ap = argparse.ArgumentParser(description="CloudMic 中转服务器")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=23777)
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
    LOG.info("CloudMic relay starting on %s:%d", args.host, args.port)
    LOG.info("手机端页面: http://<服务器IP>:%d/", args.port)

    if WS_NEW:
        def http_handler(conn, request):
            p = urlsplit(getattr(request, "path", "/")).path
            if p in ("/", "/index.html"):
                body = INDEX_HTML.encode("utf-8")
                return Response(200, "OK", Headers({"Content-Type": "text/html; charset=utf-8"}), body)
            # /download/<file>：提供 downloads 目录内的文件（如 VB-CABLE 安装包）
            if p.startswith("/download/"):
                fname = os.path.basename(p[len("/download/"):])
                fpath = os.path.join(os.path.dirname(os.path.abspath(__file__)), "downloads", fname)
                if fname and os.path.isfile(fpath):
                    with open(fpath, "rb") as _f:
                        data = _f.read()
                    return Response(200, "OK", Headers({
                        "Content-Type": "application/octet-stream",
                        "Content-Disposition": 'attachment; filename="%s"' % fname,
                    }), data)
                return Response(404, "Not Found", Headers({"Content-Type": "text/plain"}), b"Not Found")
            return None  # 其余路径（含 /ws）交给 WebSocket 握手处理
    else:
        def http_handler(path, request_headers):
            p = urlsplit(path).path
            if p in ("/", "/index.html"):
                return Headers({"Content-Type": "text/html; charset=utf-8"})
            return None

    def conn_handler(ws):
        req = getattr(ws, "request", None)
        raw_path = getattr(req, "path", None) or getattr(ws, "request_path", "/ws")
        p = urlsplit(raw_path).path if raw_path else "/ws"
        if p == "/ws":
            return handle_conn(ws)
        return ws.close(1008, "only /ws allowed")

    async def main_loop():
        async with websockets.serve(
            conn_handler,
            args.host,
            args.port,
            ping_interval=20,
            ping_timeout=20,
            max_size=MAX_FRAME + 1024,
            process_request=http_handler,
        ):
            LOG.info("ready")
            await asyncio.Future()  # run forever

    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        LOG.info("shutdown")


if __name__ == "__main__":
    main()
