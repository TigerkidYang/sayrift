import io
import threading

import numpy as np
import soundfile as sf

from local_typeless import audio


def test_speech_detection_needs_sustained_voice_above_the_noise_floor():
    silence = [90.0] * 60
    assert not audio.speech_present(silence)
    chime_only = [90.0] * 55 + [3000.0] * 3  # the start sound picked up by the mic
    assert not audio.speech_present(chime_only)
    speech = [90.0] * 20 + [1500.0] * 30
    assert audio.speech_present(speech)
    loud_room = [800.0] * 40 + [1200.0] * 10  # voiced blocks must beat 3x the room's own floor
    assert not audio.speech_present(loud_room)
    assert not audio.speech_present([5000.0] * 3)  # too short


def test_writer_encodes_blocks_to_ogg_opus_incrementally():
    rec = audio.Recorder()
    t = np.arange(audio.SAMPLE_RATE * 2) / audio.SAMPLE_RATE
    pcm = (8000 * np.sin(2 * np.pi * 220 * t)).astype(np.int16)
    writer = threading.Thread(target=rec._write_loop)
    writer.start()
    for i in range(0, len(pcm), audio.BLOCK):
        rec._queue.put(pcm[i : i + audio.BLOCK])
    rec._queue.put(None)
    writer.join(5)
    data = rec._buf.getvalue()
    assert data[:4] == b"OggS"
    decoded, sr = sf.read(io.BytesIO(data), dtype="int16")
    assert sr == audio.SAMPLE_RATE
    assert abs(len(decoded) / sr - 2.0) < 0.1
    assert len(rec._rms) == len(pcm) // audio.BLOCK
    assert len(data) < 16_000  # ~24 kbps -> ~6 KB for 2 s; WAV would be 64 KB
