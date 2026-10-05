"""WASAPI-only build policy and opt-in, offline frozen-library diagnostic."""

import os
import sys

# ASIO is not part of this distribution; do not select an absent optional DLL.
os.environ.pop("SD_ENABLE_ASIO", None)

if len(sys.argv) == 3 and sys.argv[1] == "--library-probe":
    import json
    from pathlib import Path

    from PySide6 import QtCore, QtGui, QtWidgets

    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QtWidgets.QApplication([])
    image = QtGui.QImage(16, 16, QtGui.QImage.Format.Format_ARGB32)
    image.fill(QtGui.QColor("purple"))
    result = {"qt": QtCore.qVersion(), "binding": QtCore.__file__, "image_width": image.width()}
    if Path(sys.executable).name.lower() == "sayrift.exe":
        import io
        import ssl

        import certifi
        import numpy as np
        import sounddevice
        import soundfile

        encoded = io.BytesIO()
        soundfile.write(encoded, np.zeros(1600, dtype="float32"), 16000, format="OGG", subtype="OPUS")
        encoded.seek(0)
        decoded, rate = soundfile.read(encoded)
        pcm = io.BytesIO()
        samples = np.array([-1000, 0, 1000], dtype="int16")
        soundfile.write(pcm, samples, 16000, format="WAV", subtype="PCM_16")
        pcm.seek(0)
        pcm_decoded, _ = soundfile.read(pcm, dtype="int16")
        result.update(
            sndfile=soundfile.__libsndfile_version__,
            frames=len(decoded),
            rate=rate,
            portaudio=sounddevice.get_portaudio_version(),
            audio_formats=sorted(soundfile.available_formats()),
            ogg_subtypes=sorted(soundfile.available_subtypes("OGG")),
            openssl=ssl.OPENSSL_VERSION,
            ca_count=len(ssl.create_default_context(cafile=certifi.where()).get_ca_certs()),
            pcm_roundtrip=bool(np.array_equal(samples, pcm_decoded)),
        )
    Path(sys.argv[2]).write_text(json.dumps(result, indent=2), encoding="utf-8")
    raise SystemExit(0)
