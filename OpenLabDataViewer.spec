# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


SPEC_PATH = globals().get("SPEC") or globals().get("__file__")
if SPEC_PATH is None:
    raise RuntimeError("PyInstaller did not provide the spec file path")
SPEC_DIR = Path(SPEC_PATH).resolve().parent
hiddenimports = collect_submodules("openlab_viewer")

a = Analysis(
    [str(SPEC_DIR / "run_data_viewer.py")],
    pathex=[str(SPEC_DIR / "src")],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["PySide6", "labcontrol"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="OpenLabDataViewer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)
