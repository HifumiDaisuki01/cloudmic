import asyncio
from dataclasses import replace
import threading
import time
import pytest
from cloudmic.config import Settings, validate_relay
from cloudmic.speech import SpeechQueue, segments, MAX_QUEUE

class FakeSynth:
    async def synthesize(self,text,cfg,cancel):
        await asyncio.sleep(0.001)
        return b'audio', 'test voice'

@pytest.mark.asyncio
async def test_queue_order_and_dedup():
    events=[];spoken=[]
    def play(data,device,preview,volume,cancel):spoken.append(data)
    q=SpeechQueue(FakeSynth(),play,lambda *e:events.append(e))
    assert q.enqueue('message-1','第一句。',Settings())
    assert not q.enqueue('message-1','重复消息',Settings())
    assert q.enqueue('message-2','第二句。',Settings())
    worker=asyncio.create_task(q.run())
    await asyncio.wait_for(q.queue.join(),2)
    worker.cancel();await asyncio.gather(worker,return_exceptions=True)
    assert len(spoken)==2
    assert [e[0] for e in events if e[1]=='done']==['message-1','message-2']
    assert all(any(e[0]==id and e[1]=='playing' for e in events) for id in ['message-1','message-2'])

@pytest.mark.asyncio
async def test_stop_during_synthesis_and_runner_survives():
    entered=asyncio.Event();events=[]
    class Slow:
        async def synthesize(self,*args):
            entered.set();await asyncio.sleep(20)
    q=SpeechQueue(Slow(),lambda *a:None,lambda *e:events.append(e))
    q.enqueue('message-1','hello',Settings());q.enqueue('message-2','hello',Settings())
    worker=asyncio.create_task(q.run());await entered.wait();q.stop()
    await asyncio.wait_for(q.queue.join(),1)
    assert not worker.done()
    assert {e[0] for e in events if e[1]=='cancelled'}=={'message-1','message-2'}
    q.synth=FakeSynth();q.enqueue('message-3','恢复',Settings());await asyncio.wait_for(q.queue.join(),1)
    assert any(e[0]=='message-3' and e[1]=='done' for e in events)
    worker.cancel();await asyncio.gather(worker,return_exceptions=True)

@pytest.mark.asyncio
async def test_stop_during_playback():
    playing=threading.Event();events=[]
    def play(data,device,preview,volume,cancel):
        playing.set()
        assert cancel.wait(1)
    q=SpeechQueue(FakeSynth(),play,lambda *e:events.append(e))
    q.enqueue('message-1','hello',Settings());worker=asyncio.create_task(q.run())
    await asyncio.to_thread(playing.wait,1);q.stop();await asyncio.wait_for(q.queue.join(),2)
    assert any(e[1]=='cancelled' for e in events)
    assert not any(e[1]=='done' for e in events)
    worker.cancel();await asyncio.gather(worker,return_exceptions=True)

def test_bounded_queue_and_validation():
    q=SpeechQueue(FakeSynth(),lambda *a:None,lambda *a:None)
    assert not q.enqueue('invalid','x'*501,Settings())
    assert not q.enqueue('invalid',[],Settings())
    for i in range(MAX_QUEUE):assert q.enqueue(str(i),'hello',Settings())
    assert not q.enqueue('overflow','hello',Settings())
    q.stop();assert q.queue.empty()

@pytest.mark.asyncio
async def test_expired_and_failed_messages_do_not_kill_queue():
    events=[]
    class Broken:
        async def synthesize(self,*args):raise RuntimeError('offline')
    q=SpeechQueue(Broken(),lambda *a:None,lambda *e:events.append(e))
    q.enqueue('stale-msg','hello',Settings());q.queue._queue[0].created-=31
    q.enqueue('failed-msg','hello',Settings());worker=asyncio.create_task(q.run())
    await asyncio.wait_for(q.queue.join(),1)
    assert any(e[0]=='stale-msg' and e[1]=='cancelled' for e in events)
    assert any(e[0]=='failed-msg' and e[1]=='failed' for e in events)
    assert not worker.done()
    worker.cancel();await asyncio.gather(worker,return_exceptions=True)

def test_split_and_https_validation():
    text='你好。'+('这是很长的一句话'*60)+'！结束。'
    parts=segments(text)
    assert ''.join(parts)==text
    assert max(map(len,parts))<=80
    assert segments('你好。世界！')==['你好。','世界！']
    assert validate_relay('https://example.com/')=='https://example.com'
    for value in ['http://example.com','https://user:pw@example.com','https://example.com/a','https://example.com?key=x']:
        with pytest.raises(ValueError):validate_relay(value)
