"""Build-time download only. End users receive this exact archive inside the EXE."""
from pathlib import Path
import hashlib
import time
import urllib.request
import zipfile

URL='https://download.vb-audio.com/Download_CABLE/VBCABLE_Driver_Pack45.zip'
SHA256='b950e39f01af1d04ea623c8f6d8eb9b6ea5c477c637295fabf20631c85116bfb'
root=Path(__file__).resolve().parents[1]
target=root/'desktop/vendor/VBCABLE_Driver_Pack45.zip'
def verified(data):
    if hashlib.sha256(data).hexdigest()!=SHA256:raise RuntimeError('VB-CABLE archive hash mismatch')
    return data

def main():
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():verified(target.read_bytes())
    else:
        for attempt in range(3):
            try:
                with urllib.request.urlopen(URL,timeout=30) as response:data=verified(response.read())
                target.write_bytes(data);break
            except Exception:
                if attempt==2:raise
                time.sleep(2)
    out=root/'desktop/licenses/VB-CABLE';out.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(target) as archive:
        # Preserve the author's full license text and original archive without changes.
        (out/'readme.txt').write_bytes(archive.read('readme.txt'))
    print('Verified original VB-CABLE Pack45:',target.stat().st_size,'bytes',SHA256)
if __name__=='__main__':main()
