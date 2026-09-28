"""Collect the Windows platform plugin used by this Qt Widgets application."""

from pathlib import Path

from PyInstaller.utils.hooks.qt import add_qt6_dependencies

hiddenimports, binaries, datas = add_qt6_dependencies(__file__)
# PNG support is built in. PDF, virtual keyboards and image-format plugins are
# unused and would pull unrelated Qt libraries into both Windows distributions.
binaries = [(source, target) for source, target in binaries if Path(source).name == "qwindows.dll"]
