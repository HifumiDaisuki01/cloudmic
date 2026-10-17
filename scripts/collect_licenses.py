"""Collect the installed distributions' actual license texts for the release."""
from importlib import metadata
from pathlib import Path
import shutil

root=Path(__file__).resolve().parents[1]
out=root/'desktop'/'licenses'
out.mkdir(exist_ok=True)
for dist in metadata.distributions():
    name=dist.metadata['Name']
    if name.lower() in ('pip','setuptools','wheel','pytest','pytest-asyncio'):continue
    for file in dist.files or []:
        if any(word in file.name.lower() for word in ('license','copying','copyright')):
            source=Path(dist.locate_file(file))
            if source.is_file() and source.stat().st_size<1_000_000:
                target=out/name/file.name
                target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(source,target)
# LGPLv3 incorporates GPLv3; both accompany the distributable.
assert any('edge' in p.name.lower() for p in out.iterdir()), 'Missing edge-tts license'
print('Collected license texts for',len(list(out.iterdir())),'distributions')
