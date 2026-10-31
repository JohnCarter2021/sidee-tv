# Build on a native macOS runner; PyInstaller cannot cross-compile this bundle.
import os
from pathlib import Path

root = Path(SPECPATH).parent
architecture = os.environ.get("SIDEE_TARGET_ARCH")
version = os.environ.get("SIDEE_BUILD_VERSION", "0.1.4.2")
# Apple uses three components for the marketing version and a separate build
# number. Keep the full Sidee release in its own key for four-part hotfixes.
version_parts = version.split(".")
short_version = ".".join(version_parts[:3])
build_version = os.environ.get("SIDEE_BUILD_NUMBER") or (
    version if len(version_parts) == 3 else str(max(1, int(version_parts[3]))))
identity = os.environ.get("SIDEE_CODESIGN_IDENTITY") or None
entitlements = os.environ.get("SIDEE_ENTITLEMENTS_FILE") or None

a = Analysis(
    [str(root / "macos_launcher.py")],
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
    hiddenimports=["tkinter", "tkinter.ttk", "tkinter.messagebox"],
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
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=architecture,
    codesign_identity=identity,
    entitlements_file=entitlements,
)
collection = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Sidee",
)
app = BUNDLE(
    collection,
    name="Sidee.app",
    icon=str(root / "build" / "macos" / "Sidee.icns"),
    bundle_identifier="io.github.empi9245.sidee",
    info_plist={
        "CFBundleName": "Sidee",
        "CFBundleDisplayName": "Sidee",
        "CFBundleShortVersionString": short_version,
        "CFBundleVersion": build_version,
        "SideeReleaseVersion": version,
        "LSMinimumSystemVersion": "15.0",
        "NSHighResolutionCapable": True,
        "NSLocalNetworkUsageDescription": (
            "Sidee finds and pairs with your VIDAA TV on your home network, "
            "and shares the dashboard with your phone."
        ),
    },
)
