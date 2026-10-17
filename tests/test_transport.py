"""Regression: reader finishing must cancel writer, then reconnect."""
import asyncio
import json
import time
import pytest
from cloudmic.config import Settings
from cloudmic.transport import Backend

@pytest.mark.asyncio
async def test_reader_disconnect_reconnects_and_cancels_writer(monkeypatch):
    backend=Backend(Settings(),play=lambda *a:None)
    connections=[]
    async def create_room(client):
        backend.room={'code':'ABCDEFGH','hostKey':'a'*64,'relay':'https://relay.example',
                      'expiresAt':time.time()*1000+60000}
    backend.create_room=create_room
    class Socket:
        def __init__(self):self.sent=[];self.n=len(connections);connections.append(self)
        async def __aenter__(self):return self
        async def __aexit__(self,*args):return False
        async def send(self,message):self.sent.append(message)
        async def close(self):pass
        def __aiter__(self):return self.messages()
        async def messages(self):
            yield json.dumps({'type':'ready','protocol':2})
            await asyncio.sleep(.01)
            if self.n==1:backend.closing=True
            # A clean close also has to trigger reconnect, even without an exception.
    monkeypatch.setattr('cloudmic.transport.websockets.connect',lambda *a,**k:Socket())
    await asyncio.wait_for(backend.run(),3)
    assert len(connections)==2
    assert all(json.loads(c.sent[0])['role']=='host' for c in connections)
    assert not backend.connected
    assert not any('Backend.writer' in task.get_coro().__qualname__ for task in asyncio.all_tasks() if task is not asyncio.current_task())
