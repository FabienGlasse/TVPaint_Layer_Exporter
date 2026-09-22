import json
from pathlib import Path
import tempfile
import threading
import unittest

from export_layers import TVPaint, export, folder_names
from types import SimpleNamespace


class FakeTVPaint:
    def __init__(self, fail_at=None, cancel=None):
        self.fail_at = fail_at
        self.cancel = cancel
        self.rendered = []
        self.restored = False

    def inspect(self):
        return dict(version=["fake", "11.7.3", "en"], project_id=1, clip_id=2,
                    start=7, end=9, layers=[dict(id=3, name="A/B", visible=False),
                                          dict(id=4, name="A\\B", visible=True)])

    def snapshot(self):
        return {"original": True}

    def prepare(self, state, options=None):
        if self.fail_at == "prepare":
            raise RuntimeError("setup failed")

    def activate(self, layer):
        self.layer = layer["id"]

    def render(self, frame, path):
        if self.fail_at == "render":
            raise RuntimeError("disk full")
        if self.fail_at != "missing_file":
            # A stub signature exercises the output check; this is not image QA.
            path.write_bytes(b"\x89PNG\r\n\x1a\n" + bytes(30))
        self.rendered.append((self.layer, frame, path.name))
        if self.cancel:
            self.cancel.set()

    def restore(self, state, layers):
        self.restored = state == {"original": True} and layers[0]["visible"] is False
        return ["disconnected"] if self.fail_at == "restore" else []


class ExportTests(unittest.TestCase):
    def test_sdk_path_unquoted_and_final_name_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            api = TVPaint.__new__(TVPaint)
            positions = []
            api.frame_offset = 1
            api.g = SimpleNamespace(tv_layer_image=positions.append)
            def send(command, filename, **kwargs):
                self.assertEqual(command, "tv_SaveDisplay")
                self.assertNotIn('"', filename)
                self.assertNotIn(" ", filename)
                Path(filename).write_bytes(b"\x89PNG\r\n\x1a\n" + bytes(30))
            api.send = send
            target = Path(tmp) / "Layer with spaces é_001.png"
            api.render(1, target)
            self.assertTrue(target.exists())
            self.assertEqual(positions, [0])

    def test_names_are_safe_and_unique(self):
        names = folder_names(["Letters", "letters", "../x", "CON", "NUL.txt", "", ".", "A/B", "A\\B", "é", "e\u0301", "X" * 200])
        self.assertEqual(names[0], "Letters")
        self.assertEqual(len(set(x.casefold() for x in names)), len(names))
        self.assertEqual(names[3:5], ["_CON", "_NUL.txt"])
        self.assertTrue(all(len(x) <= 84 and "/" not in x and "\\" not in x for x in names))

    def test_full_range_and_held_frames(self):
        with tempfile.TemporaryDirectory() as tmp:
            api = FakeTVPaint()
            output = export(api, Path(tmp) / "new")
            self.assertEqual([(i, f) for i, f, _ in api.rendered], [(3, 7), (3, 8), (3, 9), (4, 7), (4, 8), (4, 9)])
            self.assertTrue((output / "A_B" / "A_B_001.png").exists())
            self.assertTrue((output / "A_B__2" / "A_B__2_003.png").exists())
            self.assertTrue(api.restored)
            self.assertEqual(json.loads((output / "export_manifest.json").read_text())["status"], "complete")

    def test_failures_restore_and_record(self):
        for failure in ["prepare", "render", "missing_file", "restore"]:
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as tmp:
                api = FakeTVPaint(failure)
                output = Path(tmp) / "new"
                with self.assertRaises(RuntimeError):
                    export(api, output)
                self.assertTrue(api.restored)
                self.assertNotEqual(json.loads((output / "export_manifest.json").read_text())["status"], "complete")

    def test_cancel_restores(self):
        with tempfile.TemporaryDirectory() as tmp:
            stop = threading.Event()
            api = FakeTVPaint(cancel=stop)
            with self.assertRaises(InterruptedError):
                export(api, Path(tmp) / "new", stop)
            self.assertTrue(api.restored)
            self.assertEqual(len(api.rendered), 1)

    def test_refuses_existing_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            sentinel = Path(tmp) / "keep.txt"
            sentinel.write_text("keep")
            with self.assertRaises(FileExistsError):
                export(FakeTVPaint(), Path(tmp))
            self.assertEqual(sentinel.read_text(), "keep")


if __name__ == "__main__":
    unittest.main()
