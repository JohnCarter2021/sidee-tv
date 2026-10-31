"""Build the Linux AppImage from the PyInstaller one-directory bundle.

Layout inside the AppImage (AppDir):
    AppRun                       -> runs usr/bin/Sidee/Sidee "$@"
    Sidee.desktop                -> desktop entry (Exec=Sidee, Icon=Sidee)
    Sidee.png                    -> app icon (the Sidee logo)
    usr/bin/Sidee/Sidee          -> the PyInstaller executable
    usr/bin/Sidee/_internal/     -> the PyInstaller support files

The entry point is sidee.py itself: it starts the dashboard and opens
the system browser, so no separate Linux launcher is needed. Running
from a terminal shows errors on the console; running from a file
manager hides them, the same trade-off as any GUI-less AppImage.

appimagetool is not vendored: pass --appimagetool with a path to a
downloaded copy (CI downloads the official continuous build), or put
it on PATH. The tool runs with APPIMAGE_EXTRACT_AND_RUN=1 so it also
works on systems without FUSE, and the finished AppImage is verified
the same way (self-test through the AppImage, no FUSE required).
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

if __package__:
    from .public_release_guard import check_public_source
else:
    from public_release_guard import check_public_source

ROOT = Path(__file__).resolve().parent.parent
APP_NAME = "Sidee"
DESKTOP = """[Desktop Entry]
Type=Application
Name=Sidee
Comment=Add web apps as permanent tiles to a VIDAA TV launcher
Exec=Sidee
Icon=Sidee
Categories=Utility;Network;
Terminal=false
"""


def run(*arguments, **kwargs):
    return subprocess.run([str(value) for value in arguments],
                          check=True, **kwargs)


def build_appdir(bundle: Path, appdir: Path) -> Path:
    """Assemble an AppDir from a PyInstaller one-directory bundle."""
    if not (bundle / "Sidee").is_file():
        raise SystemExit(f"PyInstaller did not produce {bundle / 'Sidee'}")
    if appdir.exists():
        shutil.rmtree(appdir)
    target = appdir / "usr" / "bin" / "Sidee"
    shutil.copytree(bundle, target)
    apprun = appdir / "AppRun"
    apprun.write_text("#!/bin/sh\n"
                      'exec "$APPDIR/usr/bin/Sidee/Sidee" "$@"\n',
                      encoding="utf-8")
    apprun.chmod(0o755)
    (appdir / "Sidee.desktop").write_text(DESKTOP, encoding="utf-8")
    shutil.copyfile(ROOT / "assets" / "sidee-logo.png", appdir / "Sidee.png")
    return appdir


def find_appimagetool(explicit: Path | None) -> Path:
    if explicit is not None:
        if not explicit.is_file():
            raise SystemExit(f"appimagetool not found: {explicit}")
        # Resolve to absolute: a relative path like ./appimagetool
        # stringifies to the bare name "appimagetool" in subprocess,
        # which then searches PATH instead of the working directory
        # (the Run #9 Linux failure). An absolute path is used as-is.
        return explicit.resolve()
    found = shutil.which("appimagetool")
    if found is None:
        raise SystemExit(
            "appimagetool not found: download the official AppImage from "
            "https://github.com/AppImage/appimagetool/releases and pass "
            "--appimagetool <path>, or put it on PATH.")
    return Path(found)


def build(appimagetool: Path | None = None,
          version: str = "0.1.4.2") -> Path:
    if sys.platform != "linux":
        raise SystemExit(
            "Build on a native Linux runner; PyInstaller cannot "
            "cross-compile a Linux AppImage from this platform.")
    check_public_source(ROOT)
    tool = find_appimagetool(appimagetool)
    destination = ROOT / "dist" / "Sidee-Linux-x86_64.AppImage"
    destination.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, SIDEE_BUILD_VERSION=version)
    run(sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm",
        str(ROOT / "packaging" / "linux.spec"), cwd=ROOT, env=env)
    bundle = ROOT / "dist" / "Sidee"
    if not (bundle / "Sidee").is_file() or not (bundle / "_internal").is_dir():
        raise SystemExit(f"PyInstaller did not produce a complete bundle in {bundle}")
    appdir = build_appdir(bundle, ROOT / "dist" / "AppDir")
    tool_env = dict(os.environ, APPIMAGE_EXTRACT_AND_RUN="1")
    run(tool, appdir, destination, env=tool_env)
    if not destination.is_file() or destination.stat().st_size == 0:
        raise SystemExit(f"appimagetool did not produce {destination}")
    destination.chmod(0o755)
    # Verify the finished AppImage itself, not just the bundle inside it.
    verify_env = dict(os.environ, APPIMAGE_EXTRACT_AND_RUN="1")
    run(destination, "--self-test", env=verify_env, timeout=120)
    print(f"Built {destination} ({destination.stat().st_size} bytes)")
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default="0.1.4.2")
    parser.add_argument("--appimagetool", type=Path, default=None)
    arguments = parser.parse_args()
    build(arguments.appimagetool, arguments.version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
