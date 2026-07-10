# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

ROOT = Path.cwd()
ICON = ROOT / "assets" / "ICON_MOBILE_ERP.icns"

datas = []
for folder in ["images"]:
    p = ROOT / folder
    if p.exists():
        datas.append((str(p), folder))

for filename in ["README.md", "BUSINESS_LOGIC.md"]:
    p = ROOT / filename
    if p.exists():
        datas.append((str(p), "."))

a = Analysis(
    ["app.py"],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=["PIL._tkinter_finder"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ICON MOBILE ERP",
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
    strip=False,
    upx=True,
    upx_exclude=[],
    name="ICON MOBILE ERP",
)

app = BUNDLE(
    coll,
    name="ICON MOBILE ERP.app",
    icon=str(ICON) if ICON.exists() else None,
    bundle_identifier="com.iconmobile.imerpvgm",
    info_plist={
        "CFBundleName": "ICON MOBILE ERP",
        "CFBundleDisplayName": "ICON MOBILE ERP",
        "CFBundleShortVersionString": "2026.07",
        "CFBundleVersion": "2026.07",
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "11.0",
    },
)
