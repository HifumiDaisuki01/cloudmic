"""End-to-end relay protocol probe; creates one temporary room and revokes it."""
import argparse
import asyncio
import json
import os
import ssl
import time
import aiohttp
import websockets

async def probe(base):
    context=ssl.create_default_context()
    if os.environ.get('CODEX_PROXY_CERT'):context.load_verify_locations(os.environ['CODEX_PROXY_CERT'])
    trust=not base.startswith('http://127.0.0.1')
    connector=aiohttp.TCPConnector(ssl=context)
    async with aiohttp.ClientSession(connector=connector,trust_env=trust,timeout=aiohttp.ClientTimeout(total=20)) as client:
        async with client.get(base+'/health') as r:assert r.status==200 and (await r.json())['protocol']==2
        async with client.post(base+'/api/rooms',headers={'Origin':'https://untrusted.example'},json={}) as r:assert r.status==403
        async with client.post(base+'/api/pair',json={'code':'invalid'}) as r:assert r.status==400
        async with client.post(base+'/api/rooms',json={}) as r:
            room=await r.json();assert r.status==200,room
        async with client.post(base+'/api/pair',json={'code':room['code']}) as r:
            phone=await r.json();assert r.status==200,phone
        url=base.replace('https://','wss://').replace('http://','ws://')+'/ws?room='+room['code']
        extra={'ssl':context} if url.startswith('wss:') else {'proxy':None}
        async def receive(ws,type):
            while True:
                data=await asyncio.wait_for(ws.recv(),10)
                if data=='pong':continue
                obj=json.loads(data)
                if obj.get('type')==type:return obj
        async with websockets.connect(url,**extra) as bad:
            await bad.send(json.dumps({'type':'auth','role':'host','key':phone['phoneKey']}))
            try:await bad.recv();raise AssertionError('phone credential became host')
            except websockets.ConnectionClosed as e:assert e.code==4003
        async with websockets.connect(url,**extra) as host,websockets.connect(url,**extra) as mobile:
            await host.send(json.dumps({'type':'auth','role':'host','key':room['hostKey']}));await receive(host,'ready')
            await mobile.send(json.dumps({'type':'auth','role':'phone','key':phone['phoneKey']}));await receive(mobile,'ready')
            assert (await receive(mobile,'peers'))['online']
            t=time.monotonic()
            await mobile.send(json.dumps({'type':'say','id':'integration-0001','text':'测试语音。'}))
            msg=await receive(host,'say');assert msg['text']=='测试语音。'
            for state in ['queued','synthesizing','playing','done']:
                await host.send(json.dumps({'type':'status','id':msg['id'],'state':state}))
                status=await receive(mobile,'status');assert status['state']==state
            elapsed=round((time.monotonic()-t)*1000)
            await mobile.send(json.dumps({'type':'stop'}));assert (await receive(host,'stop'))['type']=='stop'
            await mobile.send(json.dumps({'type':'say','id':'integration-0002','text':'x'*501}))
            assert (await receive(mobile,'error'))['detail']
            # Receiving malformed JSON must not kill the room.
            await mobile.send('not-json');await receive(mobile,'error')
            await mobile.send(json.dumps({'type':'say','id':'integration-0003','text':'恢复'}));assert (await receive(host,'say'))['text']=='恢复'
            await host.close()
            assert not (await receive(mobile,'peers'))['online']
            await mobile.send(json.dumps({'type':'say','id':'integration-0004','text':'离线'}));assert (await receive(mobile,'status'))['state']=='failed'
            async with websockets.connect(url,**extra) as reconnect:
                await reconnect.send(json.dumps({'type':'auth','role':'host','key':room['hostKey']}));await receive(reconnect,'ready')
                assert (await receive(mobile,'peers'))['online']
                await reconnect.send('{"type":"revoke"}')
                try:await mobile.recv();raise AssertionError('revoke did not close phone')
                except websockets.ConnectionClosed as e:assert e.code==4001
        async with client.post(base+'/api/pair',json={'code':room['code']}) as r:assert r.status==404
        print(json.dumps({'ok':True,'checks':16,'status_roundtrips_ms':elapsed,'relay':base},ensure_ascii=False))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('url',nargs='?',default='http://127.0.0.1:8787');args=parser.parse_args()
    asyncio.run(probe(args.url.rstrip('/')))
