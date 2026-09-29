# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

spec_root = Path(SPECPATH)
model_dir = spec_root / "vosk-model-small-en-us-0.15"
datas = []
if model_dir.is_dir():
    datas.append((str(model_dir), "vosk-model-small-en-us-0.15"))
plugin_dir = spec_root / "plugins"
if plugin_dir.is_dir():
    datas.append((str(plugin_dir), "plugins"))

a = Analysis(
    ["karina_gui.py"],
    pathex=[str(spec_root)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "win32api",
        "win32con",
        "win32gui",
        "pythoncom",
        "pywintypes",
        "cv2",
        "numpy",
        "sounddevice",
        "vosk",
        "pyttsx3",
        "pystray",
        "PIL",
        "command_registry",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Karina",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="Karina",
)
