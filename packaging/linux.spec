# Build on a native Linux runner; PyInstaller cannot cross-compile this bundle.
# One-directory portable build: Sidee plus its _internal folder, wrapped
# by tools/build_linux_appimage.py into a single-file AppImage.
# The entry point is sidee.py itself: it starts the dashboard and opens
# the system browser, so no separate launcher is needed on Linux.
# Unsigned beta: no signing step yet; that is a signed-release step.
import os
from pathlib import Path

root = Path(SPECPATH).parent
version = os.environ.get("SIDEE_BUILD_VERSION", "0.1.4.2")

a = Analysis(
    [str(root / "sidee.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[
        (str(root / "core" / "dashboard.html"), "core"),
        (str(root / "core" / "tv-client.bundle"), "core"),
        (str(root / "assets" / "sidee-logo.png"), "assets"),
        (str(root / "assets" / "nuvio-wordmark.png"), "assets"),
        (str(root / "assets" / "jellyfin.png"), "assets"),
        (str(root / "README.md"), "."),
        (str(root / "LICENSE"), "."),
    ],
    hiddenimports=["paho.mqtt.client"],
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
    name="Sidee",
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
    name="Sidee",
)
