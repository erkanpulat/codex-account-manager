"""Build a multi-resolution Windows icon from the native Qt brand drawing."""

from __future__ import annotations

import os
import struct
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtWidgets import QApplication

from codex_account_manager.gui.design import app_icon


def main() -> None:
    app = QApplication.instance() or QApplication([])
    sizes = (16, 24, 32, 48, 64, 128, 256)
    images = []
    for size in sizes:
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        if not app_icon(size).pixmap(size, size).save(buffer, "PNG"):
            raise RuntimeError("Icon rendering failed")
        images.append(bytes(buffer.data()))
    header = struct.pack("<HHH", 0, 1, len(sizes))
    offset = 6 + 16 * len(sizes)
    entries = bytearray()
    for size, data in zip(sizes, images, strict=True):
        entries += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    output = Path(__file__).resolve().parents[1] / "packaging" / "assets"
    output.mkdir(parents=True, exist_ok=True)
    (output / "app.ico").write_bytes(header + entries + b"".join(images))
    app_icon(256).pixmap(256, 256).save(str(output / "app.png"))
    assert app is not None


if __name__ == "__main__":
    main()
