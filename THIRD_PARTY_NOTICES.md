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

CloudMic desktop 2.0.1 embeds the complete, unmodified standard
`VBCABLE_Driver_Pack45.zip` (1,318,877 bytes, SHA256
`b950e39f01af1d04ea623c8f6d8eb9b6ea5c477c637295fabf20631c85116bfb`).

VB-CABLE is by **VB-Audio / Vincent Burel** and is **donationware**.
Please support its author at https://vb-audio.com/Cable/ . It is a separate
third-party product, not relicensed under the CloudMic MIT license.
The original archive and full readme/license are retained without changes.

The author's current distribution policy permits the standard VB-CABLE package
to accompany an application, including embedding in an installation package,
when end users can identify the VB-Audio origin and donationware model and can
support the author: https://vb-audio.com/Services/licensing.htm (checked
2026-10-17). Professional/organization distribution has additional conditions.
The A+B and C+D products are not bundled.

When the required device is absent, CloudMic launches the official installer
with `-i -h`, using standard Windows elevation. UAC, driver-signature policy,
and the Windows security model remain in force; the application never performs
an automatic reboot. Driver installation is disabled in CI smoke tests.
