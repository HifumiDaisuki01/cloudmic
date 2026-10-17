import { DurableObject } from 'cloudflare:workers';
import { VERSION, ROOM_TTL, PAIR_TTL, CODE_PATTERN, randomCode, randomKey, hash, sayMessage, json } from './protocol.js';

export default {
  async fetch(request, env) {
    try {
      const url = new URL(request.url);
      const origin = request.headers.get('Origin');
      if (origin && origin !== url.origin) return json({ error: '不允许跨站请求' }, 403);
      if (url.pathname === '/health') return json({ ok: true, version: VERSION, protocol: 2 });
      const internal = async (name, path, body) => env.ROOMS.get(env.ROOMS.idFromName(name)).fetch(new Request('https://room' + path, { method: 'POST', body: JSON.stringify(body) }));
      const ip = request.headers.get('CF-Connecting-IP') || 'local';
      const limited = async (action, max) => {
        const key = await hash(ip + ':' + action);
        return (await internal('limit:' + key, '/limit', { max })).status !== 200;
      };
      if (url.pathname === '/api/rooms' && request.method === 'POST') {
        if (await limited('create', 6)) return json({ error: '创建过于频繁，请一分钟后重试' }, 429);
        for (let i = 0; i < 5; i++) {
          const code = randomCode(), hostKey = randomKey();
          const response = await internal(code, '/create', { hostHash: await hash(hostKey) });
          if (response.status === 409) continue;
          if (response.status !== 200) return response;
          return json({ code, hostKey, pairUrl: url.origin + '/#code=' + code, expiresAt: Date.now() + ROOM_TTL, pairExpiresAt: Date.now() + PAIR_TTL, protocol: 2 });
        }
        return json({ error: '请重试' }, 503);
      }
      if (url.pathname === '/api/pair' && request.method === 'POST') {
        if (await limited('pair', 20)) return json({ error: '配对尝试过多，请一分钟后重试' }, 429);
        if (Number(request.headers.get('Content-Length') || 0) > 1024) return json({ error: '请求过大' }, 413);
        const raw = await request.text();
        if (raw.length > 1024) return json({ error: '请求过大' }, 413);
        const code = String(JSON.parse(raw).code || '').replace(/[\s-]/g, '').toUpperCase();
        if (!CODE_PATTERN.test(code)) return json({ error: '请输入 8 位配对码' }, 400);
        return internal(code, '/pair', {});
      }
      if (url.pathname === '/ws' && request.headers.get('Upgrade')?.toLowerCase() === 'websocket') {
        const code = url.searchParams.get('room') || '';
        if (!CODE_PATTERN.test(code)) return json({ error: '无效房间' }, 400);
        if (await limited('ws', 40)) return json({ error: '连接过于频繁' }, 429);
        return env.ROOMS.get(env.ROOMS.idFromName(code)).fetch(request);
      }
      if (url.pathname.startsWith('/api/') || url.pathname === '/ws') return json({ error: 'Not found' }, 404);
      if (!['GET', 'HEAD'].includes(request.method)) return new Response(null, { status: 405 });
      const res = await env.ASSETS.fetch(request);
      const headers = new Headers(res.headers);
      headers.set('Content-Security-Policy', "default-src 'self'; connect-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'; form-action 'self'");
      headers.set('Referrer-Policy', 'no-referrer');
      headers.set('X-Content-Type-Options', 'nosniff');
      headers.set('Permissions-Policy', 'camera=(), microphone=(), geolocation=()');
      headers.set('Cache-Control', 'no-cache');
      return new Response(res.body, { status: res.status, headers });
    } catch { return json({ error: '请求失败，请重试' }, 400); }
  }
};

export class Room extends DurableObject {
  constructor(ctx, env) {
    super(ctx, env);
    this.ctx = ctx;
    ctx.setWebSocketAutoResponse(new WebSocketRequestResponsePair('ping', 'pong'));
  }
  async fetch(request) {
    const path = new URL(request.url).pathname;
    if (path === '/limit') {
      const { max } = await request.json();
      const now = Date.now(), bucket = Math.floor(now / 60000);
      let limit = await this.ctx.storage.get('limit');
      if (!limit || limit.bucket !== bucket) limit = { bucket, n: 0 };
      limit.n++;
      await this.ctx.storage.put('limit', limit);
      await this.ctx.storage.setAlarm(now + 120000);
      return json({}, limit.n <= max ? 200 : 429);
    }
    let meta = await this.ctx.storage.get('meta');
    if (path === '/create') {
      if (meta && meta.expiresAt > Date.now()) return json({}, 409);
      meta = { ...(await request.json()), expiresAt: Date.now() + ROOM_TTL, pairExpiresAt: Date.now() + PAIR_TTL, phones: [] };
      await this.ctx.storage.put('meta', meta);
      await this.ctx.storage.setAlarm(meta.expiresAt);
      return json({ ok: true });
    }
    if (!meta || meta.expiresAt <= Date.now()) return json({ error: '配对码已失效，请在电脑端重新配对' }, 404);
    if (path === '/pair') {
      if (meta.pairExpiresAt <= Date.now()) return json({ error: '配对码已过期，请在电脑端刷新' }, 410);
      if (meta.phones.length >= 4) return json({ error: '最多配对 4 台手机，请在电脑端刷新配对' }, 409);
      const phoneKey = randomKey();
      meta.phones.push(await hash(phoneKey));
      await this.ctx.storage.put('meta', meta);
      return json({ phoneKey, expiresAt: meta.expiresAt, protocol: 2 });
    }
    if (path !== '/ws') return json({}, 404);
    if (this.ctx.getWebSockets().length >= 10) return json({ error: '连接数已满' }, 429);
    const pair = new WebSocketPair();
    this.ctx.acceptWebSocket(pair[1]);
    pair[1].serializeAttachment({ role: 'pending', since: Date.now() });
    await this.ctx.storage.setAlarm(Math.min(meta.expiresAt, Date.now() + 11000));
    return new Response(null, { status: 101, webSocket: pair[0] });
  }
  send(ws, obj) { try { ws.send(JSON.stringify(obj)); } catch { try { ws.close(1011, 'send failed'); } catch {} } }
  sockets(role) { return this.ctx.getWebSockets().filter(ws => ws.deserializeAttachment()?.role === role); }
  peers() {
    const obj = { type: 'peers', online: this.sockets('host').length > 0, phones: this.sockets('phone').length };
    for (const ws of [...this.sockets('host'), ...this.sockets('phone')]) this.send(ws, obj);
  }
  async webSocketMessage(ws, raw) {
    try {
      const a = ws.deserializeAttachment();
      const meta = await this.ctx.storage.get('meta');
      if (!meta || meta.expiresAt <= Date.now()) return ws.close(4001, 'room expired');
      if (typeof raw !== 'string' || raw.length > 4096) return ws.close(1009, 'message too large');
      const obj = JSON.parse(raw);
      if (a.role === 'pending') {
        if (Date.now() - a.since > 10000 || obj.type !== 'auth' || typeof obj.key !== 'string' || obj.key.length !== 64) return ws.close(4003, 'auth failed');
        const keyHash = await hash(obj.key);
        const role = obj.role === 'host' && keyHash === meta.hostHash ? 'host' : obj.role === 'phone' && meta.phones.includes(keyHash) ? 'phone' : null;
        if (!role) return ws.close(4003, 'auth failed');
        // Reconnect the same identity without allowing it to become another role.
        for (const other of this.ctx.getWebSockets()) {
          if (other !== ws && other.deserializeAttachment()?.keyHash === keyHash) { other.serializeAttachment({ role: 'replaced' }); other.close(4000, 'replaced'); }
        }
        ws.serializeAttachment({ role, keyHash, window: Date.now(), count: 0 });
        this.send(ws, { type: 'ready', protocol: 2 });
        this.peers(); return;
      }
      if (!['host', 'phone'].includes(a.role)) return;
      if (Date.now() - a.window > 10000) { a.window = Date.now(); a.count = 0; }
      if (++a.count > 100) return ws.close(4008, 'rate limited');
      ws.serializeAttachment(a);
      if (a.role === 'phone') {
        const hosts = this.sockets('host');
        if (!hosts.length) { this.send(ws, { type: 'status', id: obj.id, state: 'failed', detail: '电脑端离线' }); return; }
        const say = sayMessage(obj);
        if (say) this.send(hosts[0], { ...say, sender: a.keyHash.slice(0, 16) });
        else if (obj.type === 'stop') this.send(hosts[0], { type: 'stop' });
        else this.send(ws, { type: 'error', detail: '消息无效或超过 500 字' });
      } else if (obj.type === 'revoke') {
        for (const peer of this.ctx.getWebSockets()) { try { peer.close(4001, 'pairing reset'); } catch {} }
        await this.ctx.storage.deleteAll();
      } else if (obj.type === 'status' && typeof obj.id === 'string' && typeof obj.state === 'string') {
        const allowed = ['queued', 'synthesizing', 'playing', 'done', 'failed', 'cancelled'];
        if (!allowed.includes(obj.state)) return;
        const message = { type: 'status', id: obj.id.slice(0, 64), state: obj.state, detail: String(obj.detail || '').slice(0, 200), ms: Number(obj.ms) || 0 };
        for (const ph of this.sockets('phone')) this.send(ph, message);
      }
    } catch { this.send(ws, { type: 'error', detail: '消息格式错误' }); }
  }
  webSocketClose(ws, code) { ws.serializeAttachment({ role: 'closed' }); try { ws.close(code === 1005 || code === 1006 ? 1000 : code, 'closed'); } catch {} this.peers(); }
  webSocketError(ws) { ws.serializeAttachment({ role: 'closed' }); try { ws.close(1011, 'connection error'); } catch {} this.peers(); }
  async alarm() {
    const meta = await this.ctx.storage.get('meta');
    if (!meta || meta.expiresAt <= Date.now()) {
      for (const ws of this.ctx.getWebSockets()) { try { ws.close(4001, 'room expired'); } catch {} }
      await this.ctx.storage.deleteAll(); return;
    }
    let next = meta.expiresAt;
    for (const ws of this.ctx.getWebSockets()) {
      const a = ws.deserializeAttachment();
      if (a?.role !== 'pending') continue;
      if (Date.now() - a.since >= 10000) { ws.serializeAttachment({ role: 'closed' }); try { ws.close(4003, 'auth timeout'); } catch {} }
      else next = Math.min(next, a.since + 11000);
    }
    await this.ctx.storage.setAlarm(next);
  }
}
