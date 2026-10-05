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

        import numpy as np
        import sounddevice
        import soundfile

        encoded = io.BytesIO()
        soundfile.write(encoded, np.zeros(1600, dtype="float32"), 16000, format="OGG", subtype="OPUS")
        encoded.seek(0)
        decoded, rate = soundfile.read(encoded)
        result.update(
            sndfile=soundfile.__libsndfile_version__,
            frames=len(decoded),
            rate=rate,
            portaudio=sounddevice.get_portaudio_version(),
        )
    Path(sys.argv[2]).write_text(json.dumps(result, indent=2), encoding="utf-8")
    raise SystemExit(0)
