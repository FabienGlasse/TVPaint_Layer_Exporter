import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import setup_steps as setup


class SetupTests(unittest.TestCase):
    def test_stale_windows_version_is_listed_and_requires_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            exe = Path(directory) / "TVPaint Developpement/TVPaint Animation 12 Pro/TVPaint Animation 12 Pro.exe"
            exe.parent.mkdir(parents=True)
            exe.touch()
            with patch.object(setup, "executable_details", return_value=(0x8664, "12.0.0")), patch.dict(
                    os.environ, {name: directory for name in ("ProgramW6432", "ProgramFiles", "ProgramFiles(x86)")}), patch.object(setup, "log"):
                with patch("builtins.input", return_value="1"):
                    self.assertEqual(setup.choose_tvpaint(), exe.resolve())
                with patch("builtins.input", return_value="12.1.0"):
                    self.assertEqual(setup.selected_version(exe), "12.1.0")
                with patch("builtins.input", return_value=""):
                    with self.assertRaises(InterruptedError):
                        setup.selected_version(exe)
                with patch.object(setup, "verified_bridge", return_value=b"bridge"), patch.object(setup, "require_tvpaint_closed"), patch.object(setup, "plugin_conflict", return_value=None):
                    setup.admin_copy(exe, Path("verified.zip"), confirmed_version="12.1.0")
                    self.assertEqual((exe.parent/setup.CONFIG["12.1.0"]["target"]).read_bytes(), b"bridge")

    def test_elevation_carries_confirmed_version(self):
        with patch.object(setup, "checked_run") as run:
            setup.elevate_plugin(Path("TVPaint Animation 12 Pro.exe"), Path("verified.zip"), "12.1.0")
        self.assertIn("--confirmed-version 12.1.0", run.call_args.kwargs["env"]["TVPE_ADMIN_ARGS"])

    def test_generic_tvpaint12_name_is_detected_and_selected(self):
        with tempfile.TemporaryDirectory() as directory:
            exe = Path(directory) / "TVPaint Developpement/TVPaint Animation 12 Pro/TVPaint Animation 12 Pro.exe"
            exe.parent.mkdir(parents=True)
            exe.touch()
            with patch.object(setup, "executable_details", return_value=(0x8664, "12.1.0")), patch.dict(
                    os.environ, {name: directory for name in ("ProgramW6432", "ProgramFiles", "ProgramFiles(x86)")}), patch("builtins.input", return_value="1"):
                self.assertEqual(setup.version_of(exe), "12.1.0")
                self.assertEqual(setup.choose_tvpaint(), exe.resolve())

    def test_version_and_architecture_are_not_guessed_from_filename(self):
        with tempfile.TemporaryDirectory() as directory:
            exe = Path(directory) / "TVPaint Animation 12.1.0 Pro (64bits).exe"
            exe.touch()
            for details in ((0x14c, "12.1.0"), (0x8664, "12.0.0")):
                with self.subTest(details=details), patch.object(setup, "executable_details", return_value=details):
                    with self.assertRaises(ValueError):
                        setup.version_of(exe)
            with patch.object(setup, "executable_details", return_value=(0x8664, None)):
                self.assertEqual(setup.version_of(exe), "12.1.0")
            generic = exe.with_name("TVPaint Animation 12 Pro.exe")
            generic.touch()
            with patch.object(setup, "executable_details", return_value=(0x8664, None)):
                with self.assertRaisesRegex(ValueError, "unavailable"):
                    setup.version_of(generic)

    def test_decline_stops_before_changes(self):
        with patch.object(setup, "log"), patch("builtins.input", return_value="n"):
            with self.assertRaises(InterruptedError):
                setup.confirm("S5", "admin copy")

    def test_official_bridge_archives(self):
        bridge = Path(__file__).resolve().parents[1] / "exporter/bridge"
        if not bridge.exists():
            self.skipTest("optional downloaded bridge archives are not in the source checkout")
        for version, filename in [("11.7.3", "tvpaint-rpc-1.1.0-tvp-11.dll"), ("12.1.0", "tvpaint-rpc-1.2.0-tvp-12.1.zip")]:
            with self.subTest(version=version):
                self.assertTrue(setup.verified_bridge(bridge / filename, version).startswith(b"MZ"))

    def test_modified_download_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "component.dll"
            path.write_bytes(b"incorrect bytes")
            with self.assertRaises(RuntimeError):
                setup.verified_bridge(path, "11.7.3")

    def test_conflicting_component_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            exe = Path(directory) / "TVPaint.exe"
            plugin = Path(directory) / "plugins/other-rpc.dll"
            plugin.parent.mkdir()
            plugin.write_bytes(b"existing")
            with self.assertRaises(RuntimeError):
                setup.plugin_conflict(exe, "11.7.3", b"new")
            self.assertEqual(plugin.read_bytes(), b"existing")

    def test_matching_component_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            exe = Path(directory) / "TVPaint.exe"
            plugin = Path(directory) / "plugins/tvpaint-rpc.dll"
            plugin.parent.mkdir()
            plugin.write_bytes(b"matching")
            self.assertEqual(setup.plugin_conflict(exe, "11.7.3", b"matching"), plugin)

    def test_invalid_selection_does_not_install(self):
        with patch.dict(os.environ, {name: "Z:/nonexistent" for name in ("ProgramW6432", "ProgramFiles", "ProgramFiles(x86)")}), patch("builtins.input", return_value="0"):
            with self.assertRaises(ValueError):
                setup.choose_tvpaint()

    @unittest.skipUnless(os.name == "nt", "Windows BAT integration")
    def test_declining_python_download_creates_no_download(self):
        import shutil
        with tempfile.TemporaryDirectory(prefix="tvpaint download decline ") as directory:
            root = Path(directory)
            shutil.copy2(Path(__file__).parent / "Install.bat", root / "Install.bat")
            (root / "py.cmd").write_text("@exit /b 1\n")
            environment = os.environ.copy()
            environment["TVPE_APP"] = str(root / "app")
            result = subprocess.run(["cmd.exe", "/d", "/c", str(root / "Install.bat")],
                                    input="N\n\n", capture_output=True, text=True,
                                    env=environment, cwd=root, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((root / "app/python-3.13.13-amd64.exe").exists())
            self.assertIn("User stopped setup", (root / "app/setup.log").read_text())

    @unittest.skipUnless(os.name == "nt", "Windows BAT integration")
    def test_bat_stops_safely_at_invalid_selection(self):
        # Exercise actual CMD quoting with a path containing spaces; no downloads.
        import shutil
        with tempfile.TemporaryDirectory(prefix="tvpaint setup check ") as directory:
            root = Path(directory)
            for name in ("Install.bat", "setup_steps.py"):
                shutil.copy2(Path(__file__).parent / name, root / name)
            # Simulate a working py launcher; this host's py.exe has no registered
            # Python even though the test interpreter exists at an explicit path.
            (root / "py.cmd").write_text('@echo off\n"' + sys.executable + '" %2 %3 %4 %5 %6 %7 %8 %9\n')
            environment = os.environ.copy()
            environment["TVPE_APP"] = str(root / "local data/TVPaintLayerExporter")
            result = subprocess.run(["cmd.exe", "/d", "/c", str(root / "Install.bat")],
                                    input="0\n\n", capture_output=True, text=True,
                                    env=environment, cwd=root, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            log = (root / "local data/TVPaintLayerExporter/setup.log").read_text()
            self.assertIn("S1 select TVPaint", log)
            self.assertNotIn("S2 START", log)


if __name__ == "__main__":
    unittest.main()
