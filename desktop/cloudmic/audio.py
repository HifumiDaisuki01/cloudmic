"""Audio output is deliberately blocking and only called on a worker thread."""
from __future__ import annotations
import threading
from dataclasses import dataclass
import miniaudio
import sounddevice as sd

@dataclass(frozen=True)
class OutputDevice:
    index: int
    name: str
    cable: bool
    samplerate: int


def outputs():
    result = []
    for i, device in enumerate(sd.query_devices()):
        if device['max_output_channels'] <= 0:
            continue
        # WASAPI avoids truncated MME names and duplicate devices.
        host = sd.query_hostapis(device['hostapi'])['name']
        if 'WASAPI' not in host:
            continue
        name = device['name']
        result.append(OutputDevice(i, name, 'cable input' in name.lower(), int(device['default_samplerate'])))
    return result


def choose_output(name: str, preview: bool):
    devices = outputs()
    if preview:
        # Preview must go to a physical/default device, not silently to CABLE.
        default = sd.default.device[1]
        match = next((d for d in devices if d.index == default and not d.cable), None)
        match = match or next((d for d in devices if not d.cable), None)
    else:
        match = next((d for d in devices if name and d.name == name), None)
        match = match or next((d for d in devices if d.cable), None)
    if match is None:
        raise RuntimeError('未找到输出设备。游戏语音需先安装 VB-CABLE；仅试听可打开“扬声器试听”。')
    return match


def play_audio(data: bytes, device_name: str, preview: bool, volume: float, cancel: threading.Event):
    device = choose_output(device_name, preview)
    # Resample to the actual endpoint format. No numpy or external ffmpeg needed.
    decoded = miniaudio.decode(data, output_format=miniaudio.SampleFormat.SIGNED16,
                               nchannels=1, sample_rate=device.samplerate)
    samples = decoded.samples
    if volume != 1.0:
        for i, sample in enumerate(samples):
            samples[i] = max(-32768, min(32767, int(sample * volume)))
    chunk = max(1, device.samplerate // 50)  # 20 ms; cancellation stays responsive.
    if cancel.is_set():
        return
    with sd.RawOutputStream(device=device.index, samplerate=device.samplerate,
                            channels=1, dtype='int16', latency='low') as stream:
        for start in range(0, len(samples), chunk):
            if cancel.is_set():
                stream.abort()
                return
            stream.write(samples[start:start + chunk].tobytes())
