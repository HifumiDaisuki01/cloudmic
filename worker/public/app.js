'use strict';
const $ = id => document.getElementById(id);
let socket, session, retry, heartbeat, watchdog, generation = 0, online = false, attempts = 0;
const entries = new Map();
const states = { queued:'电脑已接收 · 排队中', synthesizing:'正在合成语音', playing:'正在朗读', done:'朗读完成', failed:'未能朗读', cancelled:'已取消' };
const defaults = ['等一下，我正在打字。','你好，很高兴认识你。','收到，谢谢！','我需要一点帮助。','稍等，我马上回来。','再说一遍可以吗？'];
let phrases = defaults;
try { const saved = JSON.parse(localStorage.getItem('cloudmic.phrases')); if(Array.isArray(saved)) phrases = saved.filter(x=>typeof x==='string'&&x.length<=200).slice(0,12); } catch {}
function connection(label, active=false) { $('connection').textContent=label; $('connection').classList.toggle('on',active); online=active; $('send').disabled=!active; $('stop').disabled=!active; document.querySelectorAll('#phrases button').forEach(b=>b.disabled=!active); $('sendHint').textContent=active?'回车发送 · Shift + 回车换行 · 最多 500 字':'电脑离线或连接中，文字不会自动重发'; }
function closeSocket() { generation++; clearTimeout(retry); clearInterval(heartbeat); clearTimeout(watchdog); if(socket){socket.onclose=null;socket.close();socket=null;} }
function saveSession(value) { session=value; try { if(value) sessionStorage.setItem('cloudmic.session',JSON.stringify(value)); else sessionStorage.removeItem('cloudmic.session'); } catch {} }
function unpair(message='') { closeSocket();saveSession(null);connection('未连接');$('pairPanel').hidden=false;$('composePanel').hidden=true;$('pairError').textContent=message; }
function connect() {
  if(!session||session.expiresAt<=Date.now()) return unpair('配对已过期，请在电脑端刷新配对码');
  closeSocket(); const g=generation; connection('正在连接');
  $('pairPanel').hidden=true;$('composePanel').hidden=false;
  socket=new WebSocket(`${location.protocol==='https:'?'wss:':'ws:'}//${location.host}/ws?room=${session.code}`);
  socket.onopen=()=>{socket.send(JSON.stringify({type:'auth',role:'phone',key:session.phoneKey}));heartbeat=setInterval(()=>{if(socket?.readyState===1){socket.send('ping');clearTimeout(watchdog);watchdog=setTimeout(()=>socket?.close(),12000);}},20000);};
  socket.onmessage=event=>{
    if(g!==generation)return;
    if(event.data==='pong'){clearTimeout(watchdog);return;}
    let obj;try{obj=JSON.parse(event.data);}catch{return;}
    if(obj.type==='ready') attempts=0;
    if(obj.type==='peers') connection(obj.online?'已连接电脑':'电脑端离线',obj.online);
    if(obj.type==='status'&&entries.has(obj.id)) {
      const el=entries.get(obj.id); el.dataset.state=obj.state;
      el.querySelector('small').textContent=(states[obj.state]||obj.state)+(obj.detail?' · '+obj.detail:'')+(obj.ms>0&&obj.state==='playing'?` · ${obj.ms} ms`: '');
    }
    if(obj.type==='error') $('sendHint').textContent=obj.detail;
  };
  socket.onerror=()=>socket?.close();
  socket.onclose=event=>{
    if(g!==generation)return;clearInterval(heartbeat);clearTimeout(watchdog);
    for(const el of entries.values())if(['sent','queued','synthesizing','playing'].includes(el.dataset.state)){el.dataset.state='failed';el.querySelector('small').textContent='连接中断 · 朗读结果未知，不会自动重发';}
    if([4001,4003,4000].includes(event.code))return unpair('配对已结束，请重新扫码或输入配对码');
    connection('连接中断 · 正在重连');retry=setTimeout(connect,Math.min(15000,1000*2**Math.min(attempts++,4))+Math.random()*400);
  };
}
async function pair(code) {
  $('pairButton').disabled=true;$('pairError').textContent='正在配对…';
  try {const response=await fetch('/api/pair',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code}),signal:AbortSignal.timeout(12000)});const result=await response.json();if(!response.ok)throw Error(result.error||'配对失败');saveSession({...result,code:code.replace(/[\s-]/g,'').toUpperCase()});history.replaceState(null,'',location.pathname);connect();}
  catch(error){$('pairError').textContent=error.message==='The operation was aborted due to timeout'?'网络超时，请重试':error.message;}
  finally{$('pairButton').disabled=false;}
}
function send(text) {
  text=text.trim();if(!text||!online||socket?.readyState!==1)return;if(text.length>500)return;
  const id=crypto.randomUUID();
  if(!entries.size)$('history').replaceChildren();
  const el=document.createElement('article');el.className='entry';el.dataset.state='sent';
  const p=document.createElement('p');p.textContent=text;const status=document.createElement('small');status.textContent='已发送 · 等待电脑接收';el.append(p,status);$('history').prepend(el);entries.set(id,el);
  if(entries.size>60){const oldest=entries.keys().next().value;entries.get(oldest).remove();entries.delete(oldest);}
  socket.send(JSON.stringify({type:'say',id,text}));$('text').value='';$('count').textContent='0 / 500';
}
function renderPhrases(){ $('phrases').replaceChildren();for(const phrase of phrases){const b=document.createElement('button');b.textContent=phrase;b.disabled=!online;b.onclick=()=>send(phrase);$('phrases').append(b);} }
$('pairForm').onsubmit=e=>{e.preventDefault();pair($('code').value);};
$('code').oninput=()=>{$('code').value=$('code').value.toUpperCase().replace(/[^A-HJ-NP-Z2-9\s-]/g,'');};
$('text').oninput=()=>{$('count').textContent=$('text').value.length+' / 500';};
$('text').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing&&e.keyCode!==229){e.preventDefault();send($('text').value);}};
$('send').onclick=()=>send($('text').value);
$('stop').onclick=()=>{if(online&&socket?.readyState===1)socket.send(JSON.stringify({type:'stop'}));};
$('disconnect').onclick=()=>unpair();
$('clearHistory').onclick=()=>{entries.clear();$('history').replaceChildren();};
$('editPhrases').onclick=()=>{$('phraseText').value=phrases.join('\n');$('phraseDialog').showModal();};
$('cancelPhrases').onclick=()=>$('phraseDialog').close();
$('phraseForm').onsubmit=e=>{e.preventDefault();phrases=$('phraseText').value.split('\n').map(x=>x.trim()).filter(Boolean).slice(0,12).map(x=>x.slice(0,200));try{localStorage.setItem('cloudmic.phrases',JSON.stringify(phrases));}catch{}renderPhrases();$('phraseDialog').close();};
renderPhrases();
try{const s=JSON.parse(sessionStorage.getItem('cloudmic.session'));if(s&&typeof s.phoneKey==='string'&&/^[A-HJ-NP-Z2-9]{8}$/.test(s.code))session=s;}catch{}
const invite=new URLSearchParams(location.hash.slice(1)).get('code');
if(invite){$('code').value=invite;history.replaceState(null,'',location.pathname);if(session?.code===invite)connect();else pair(invite);}else if(session)connect();
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&session&&(!socket||socket.readyState>1))connect();});
