# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller one-folder build for the Windows portable release."""
from __future__ import annotations

import glob
import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, copy_metadata


project_root = Path(SPEC).resolve().parents[1]
datas = [
    (str(project_root / "rulepack" / "current.json"), "rulepack"),
    (str(project_root / "lmpc" / "server" / "web"), "lmpc/server/web"),
]
binaries = []
hiddenimports = [
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
]

for package in (
    "rapidocr_onnxruntime",
    "onnxruntime",
    "weasyprint",
    "pillow_heif",
    "docx",
):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

for distribution in ("rapidocr-onnxruntime", "onnxruntime", "weasyprint", "python-docx"):
    datas += copy_metadata(distribution)

# WeasyPrint loads Pango through CFFI. On Windows the workflow installs the official
# MSYS2 UCRT64 package; adding its entry DLLs lets PyInstaller recursively collect their
# linked dependencies into the application folder.
if sys.platform == "win32":
    dll_root = Path(os.environ.get("LMPC_PANGO_DLL_DIR", r"C:\msys64\ucrt64\bin"))
    patterns = (
        "libgobject-2.0-0.dll",
        "libglib-2.0-0.dll",
        "libgio-2.0-0.dll",
        "libpango-1.0-0.dll",
        "libpangoft2-1.0-0.dll",
        "libharfbuzz-0.dll",
        "libharfbuzz-subset-0.dll",
        "libfontconfig-1.dll",
        "libfreetype-6.dll",
    )
    for pattern in patterns:
        binaries += [(path, ".") for path in glob.glob(str(dll_root / pattern))]

a = Analysis(
    [str(project_root / "lmpc" / "desktop.py")],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["boto3", "botocore", "matplotlib", "pytest"],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LMPC-Compliance",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
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
    upx=False,
    upx_exclude=[],
    name="LMPC-Compliance",
)
