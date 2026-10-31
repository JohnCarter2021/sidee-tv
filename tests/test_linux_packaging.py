"""Linux AppImage packaging: spec datas, AppDir layout, builder guards."""
from pathlib import Path
import os
import runpy
import shutil
import tempfile
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace

from tools import build_linux_appimage as packaging
from tools import build_macos_release


class TestLinuxSpec(unittest.TestCase):
    def test_spec_datas_match_verified_resources(self):
        analysis = SimpleNamespace(pure=[], scripts=[], binaries=[], datas=[])
        analysis_mock = Mock(return_value=analysis)
        spec = packaging.ROOT / "packaging" / "linux.spec"
        runpy.run_path(str(spec), init_globals={
            "SPECPATH": str(spec.parent),
            "Analysis": analysis_mock, "PYZ": Mock(),
            "EXE": Mock(), "COLLECT": Mock(),
        })
        datas = analysis_mock.call_args.kwargs["datas"]
        expected = {(str(packaging.ROOT / relative),
                     Path(relative).parent.as_posix()
                     if str(Path(relative).parent) != "." else ".")
                    for relative in build_macos_release.RESOURCES}
        self.assertEqual({(source, dest) for source, dest in datas}, expected)
        self.assertEqual(analysis_mock.call_args.args[0],
                         [str(packaging.ROOT / "sidee.py")])


class TestAppDir(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.bundle = self.root / "Sidee"
        (self.bundle / "_internal").mkdir(parents=True)
        (self.bundle / "Sidee").write_bytes(b"fake-exe")
        (self.bundle / "_internal" / "sidee").write_bytes(b"fake-lib")

    def test_appdir_layout_and_apprun(self):
        appdir = packaging.build_appdir(self.bundle, self.root / "AppDir")
        self.assertEqual((appdir / "usr" / "bin" / "Sidee" / "Sidee").read_bytes(),
                         b"fake-exe")
        self.assertTrue((appdir / "usr" / "bin" / "Sidee" / "_internal").is_dir())
        apprun = appdir / "AppRun"
        self.assertEqual(apprun.read_text(encoding="utf-8"),
                         "#!/bin/sh\n"
                         'exec "$APPDIR/usr/bin/Sidee/Sidee" "$@"\n')
        # Windows chmod cannot set exec bits, so the mode check
        # only applies on Unix runners.
        if os.name != "nt":
            self.assertTrue(apprun.stat().st_mode & 0o111)
        desktop = (appdir / "Sidee.desktop").read_text(encoding="utf-8")
        self.assertIn("Exec=Sidee", desktop)
        self.assertIn("Icon=Sidee", desktop)
        self.assertTrue((appdir / "Sidee.png").is_file())

    def test_missing_executable_is_rejected(self):
        (self.bundle / "Sidee").unlink()
        with self.assertRaisesRegex(SystemExit, "did not produce"):
            packaging.build_appdir(self.bundle, self.root / "AppDir")


class TestBuilderGuards(unittest.TestCase):
    def test_non_linux_build_is_rejected(self):
        with patch.object(packaging.sys, "platform", "win32"):
            with self.assertRaisesRegex(SystemExit, "native Linux"):
                packaging.build()

    def test_relative_appimagetool_path_is_resolved_absolute(self):
        # Run #9 Linux: CI passed ./appimagetool, which Path
        # stringifies to the bare name "appimagetool", so subprocess
        # searched PATH instead of the working directory.
        import os
        with tempfile.TemporaryDirectory() as temporary:
            tool = Path(temporary) / "appimagetool"
            tool.write_bytes(b"fake-tool")
            previous = os.getcwd()
            try:
                os.chdir(temporary)
                found = packaging.find_appimagetool(Path("./appimagetool"))
            finally:
                os.chdir(previous)
            self.assertTrue(found.is_absolute())
            # Compare resolved paths: resolve() also normalises
            # symlinked temp dirs (/var -> /private/var on macOS)
            # and 8.3 short paths on Windows, so the raw temp path
            # is not equal to the resolved one on those runners
            # (the Run #10 failure). Absolute + resolvable is the
            # property the builder actually needs.
            self.assertEqual(found, tool.resolve())

    def test_missing_appimagetool_is_rejected(self):
        # Pin the platform: without this, build() rejects the run on
        # Windows/macOS with "native Linux" before it ever checks the
        # tool path, so this test failed on every non-Linux CI job in
        # Run #9 even though the guard itself is correct.
        with patch.object(packaging.sys, "platform", "linux"), \
                patch.object(packaging, "check_public_source"):
            with self.assertRaisesRegex(SystemExit, "appimagetool not found"):
                packaging.build(Path("/nonexistent/appimagetool"))


if __name__ == "__main__":
    unittest.main()
