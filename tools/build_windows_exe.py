"""Build the portable Windows executable ZIP with PyInstaller.

Run on a native Windows runner only: PyInstaller cannot cross-compile
a Windows exe from Linux or macOS. The output is a one-directory
portable folder (Sidee.exe plus _internal/) zipped as
``dist/Sidee-Windows-Exe.zip``, with a safe-mode batch file and a
README at the folder root. The source ZIP (start-windows.ps1) remains
available for users who prefer it; this exe replaces the need to
download Python on first launch, not the source checkout.

The build is fail-closed: the public-source guard runs first, so a
private token in a core module stops the build before anything ships.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

if __package__:
    from .public_release_guard import check_public_source
else:
    from public_release_guard import check_public_source

ROOT = Path(__file__).resolve().parent.parent


def build(destination: Path | None = None, version: str = "0.1.4.2") -> Path:
    if sys.platform != "win32":
        raise SystemExit(
            "Build on a native Windows runner; PyInstaller cannot "
            "cross-compile a Windows exe from this platform.")
    check_public_source(ROOT)
    destination = Path(destination or ROOT / "dist" / "Sidee-Windows-Exe.zip")
    destination.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, SIDEE_BUILD_VERSION=version)
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm",
         str(ROOT / "packaging" / "windows.spec")],
        cwd=ROOT, env=env, check=True)
    bundle = ROOT / "dist" / "Sidee"
    exe = bundle / "Sidee.exe"
    if not exe.is_file():
        raise SystemExit(f"PyInstaller did not produce {exe}")
    shutil.copyfile(ROOT / "packaging" / "Sidee-SafeMode.bat",
                    bundle / "Sidee-SafeMode.bat")
    shutil.copyfile(ROOT / "packaging" / "windows-portable-README.txt",
                    bundle / "README.txt")
    fd, temporary = tempfile.mkstemp(prefix=".sidee-exe-", suffix=".zip",
                                     dir=destination.parent)
    os.close(fd)
    temporary = Path(temporary)
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(bundle.rglob("*")):
                if path.is_file():
                    archive.write(path, "Sidee/" + path.relative_to(bundle).as_posix())
        with zipfile.ZipFile(temporary) as archive:
            names = archive.namelist()
        for required in ("Sidee/Sidee.exe", "Sidee/Sidee-SafeMode.bat",
                         "Sidee/README.txt"):
            if required not in names:
                raise SystemExit(f"exe ZIP is missing {required}")
        if not any(n.startswith("Sidee/_internal/") for n in names):
            raise SystemExit("exe ZIP is missing the _internal folder")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="0.1.4.2")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    print(build(Path(args.output) if args.output else None, args.version))
