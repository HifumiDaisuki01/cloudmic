# Third-party notices

CloudMic application and relay: MIT, Copyright © 2026 Keran Technology.

The Windows portable application bundles Python (PSF license), Tcl/Tk (BSD-style
licenses), CustomTkinter (MIT, Tom Schimansky), edge-tts (LGPL-3.0, rany and
contributors), aiohttp (Apache-2.0/MIT), websockets (BSD-3-Clause), miniaudio
(MIT-0/MIT, David Reid and contributors), sounddevice/PortAudio (MIT), Pillow
(HPND), qrcode (BSD), pystray (LGPL-3.0), pywin32 (PSF and included third-party
licenses), and their dependencies. The exact installed license texts are
included in the release's `licenses` directory and in the executable bundle.

## LGPL components and rebuilding

- edge-tts source: https://github.com/rany2/edge-tts (version 7.3.1)
- pystray source: https://github.com/moses-palmer/pystray (version 0.19.5)
- The corresponding source archives are attached to the release as
  `third-party-sources.zip`, alongside the complete CloudMic source supplied by
  the GitHub release's source archive at the same tag.
- No changes are made to these libraries. They are included with their licenses,
  not relicensed under CloudMic's MIT license.
- To modify/recombine them: obtain the application source, install Python 3.12
  on Windows, replace the relevant package with your modified version, then run
  `python -m PyInstaller --clean --noconfirm CloudMic.spec` from `desktop` after
  installing the remaining pinned dependencies and collecting license texts.
  There is no signing, activation, or installation lock preventing replacement.
- Modification and reverse engineering for debugging changes to these LGPL
  components are permitted. The application source and build instructions are
  public, so the combined work can be rebuilt with a modified library.

## Virtual audio driver

VB-CABLE is NOT bundled, silently installed, or covered by the MIT license.
It is a separate donationware product by VB-Audio / Vincent Burel:
https://vb-audio.com/Cable/ . Obtain it from its author and follow its license.
Existing compatible audio devices can be selected without installing VB-CABLE.
