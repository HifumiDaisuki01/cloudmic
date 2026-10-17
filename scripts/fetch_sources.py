"""Download corresponding LGPL source archives from their upstream publishers."""
from pathlib import Path
import hashlib
import json
import time
import urllib.request

out=Path('third-party-sources');out.mkdir(exist_ok=True)
def get(url):
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url,timeout=30) as response:return response.read()
        except Exception:
            if attempt==2:raise
            time.sleep(2)
metadata=json.loads(get('https://pypi.org/pypi/edge-tts/7.3.1/json'))
source=next(x for x in metadata['urls'] if x['packagetype']=='sdist')
data=get(source['url'])
assert hashlib.sha256(data).hexdigest()==source['digests']['sha256']
(out/source['filename']).write_bytes(data)
# Exact upstream v0.19.5 commit, verified against its official Git tag.
archive=get('https://codeload.github.com/moses-palmer/pystray/tar.gz/c587fbe535610c177d49b585264762fa06abddca')
(out/'pystray-0.19.5.tar.gz').write_bytes(archive)
for path in out.iterdir():print(path.name,hashlib.sha256(path.read_bytes()).hexdigest())
