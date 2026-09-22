import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from export_layers import export, TVPaint, check_image
from export_options import Options, IMAGE_FORMATS, plan, frame_path, check_writable, read_settings, write_settings
from test_export_layers import FakeTVPaint


class ExportOptionsTests(unittest.TestCase):
    def test_flat_output_collision_names_and_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/'out'
            stop = threading.Event()
            with self.assertRaises(InterruptedError):
                export(FakeTVPaint(cancel=stop), output, stop, options=Options(layer_folders=False))
            export(FakeTVPaint(), output, resume=True)
            self.assertTrue((output/'A_B_001.png').is_file())
            self.assertTrue((output/'A_B__2_003.png').is_file())
            self.assertFalse(any(path.is_dir() for path in output.iterdir()))
            self.assertIn('All images in the output folder', (output/'Delivery Report.txt').read_text(encoding='utf-8'))

    def test_all_image_modes_and_background_restore(self):
        for image_format, (mode, extension, alpha) in IMAGE_FORMATS.items():
            with self.subTest(image_format=image_format):
                api = TVPaint.__new__(TVPaint)
                calls = []
                api.send = lambda *args, **kwargs: calls.append((args, kwargs)) or 'all'
                state = {'background': 'color 10 20 30'}
                api.prepare(state, {'image_format': image_format, 'background': True})
                self.assertIn((('tv_SaveMode', mode), {}), calls)
                self.assertIn((('tv_Background', 'color 10 20 30'), {'handle_string': False}), calls)
                self.assertEqual(state['background'], 'color 10 20 30')
                task = plan(FakeTVPaint().inspect(), 'out', Options(image_format=image_format))
                self.assertTrue(str(frame_path('out', task['layers'][0], 7, task['options'])).endswith('.'+extension))
                self.assertEqual(task['options']['background'], not alpha)
        calls.clear()
        api.prepare({'background': 'check 100 100 100 200 200 200'}, {'background': True})
        self.assertIn((('tv_Background', 'color 255 255 255'), {'handle_string': False}), calls)
        calls.clear()
        api.prepare({'background': 'color 10 20 30'})
        self.assertIn((('tv_Background', 'none'), {}), calls)

    def test_format_file_checks_and_non_png_resume(self):
        headers = {'PNG': b'\x89PNG\r\n\x1a\n', 'JPEG': b'\xff\xd8\xff', 'TIFF': b'II*\x00',
                   'BMP': b'BM', 'TGA': b'\x00\x00\x02' + bytes(9) + b'\x01\x00\x01\x00\x20\x08'}
        class ImageFake(FakeTVPaint):
            def prepare(self, state, options=None):
                self.image_format = options['image_format']
            def render(self, frame, path):
                path.write_bytes(headers[self.image_format]+bytes(40))
                self.rendered.append((self.layer, frame, path.name))
                if self.cancel:
                    self.cancel.set()
        with tempfile.TemporaryDirectory() as tmp:
            for image_format in IMAGE_FORMATS:
                with self.subTest(image_format=image_format):
                    output = Path(tmp)/image_format
                    stop = threading.Event()
                    with self.assertRaises(InterruptedError):
                        export(ImageFake(cancel=stop), output, stop, options=Options(image_format=image_format, layer_folders=False))
                    export(ImageFake(), output, resume=True)
                    manifest = json.loads((output/'export_manifest.json').read_text())
                    self.assertEqual(manifest['status'], 'complete')
                    for filename in manifest['files']:
                        check_image(output/filename, image_format)
                    self.assertIn('(•ᆺ•)づ  DELIVERY REPORT', (output/'Delivery Report.txt').read_text(encoding='utf-8'))

    def test_selected_range_naming_and_delivery(self):
        with tempfile.TemporaryDirectory() as tmp:
            api = FakeTVPaint()
            updates = []
            output = export(api, Path(tmp)/'out', options=Options([4], 8, 9, 'SH010', 1001, 4), on_progress=updates.append)
            self.assertEqual([(i, f) for i, f, _ in api.rendered], [(4, 8), (4, 9)])
            self.assertTrue((output/'A_B/SH010_A_B_1001.png').exists())
            self.assertEqual(updates[-1]['completed'], 2)
            self.assertEqual(updates[-1]['remaining'], 0)
            self.assertIn('Files: 2 / 2', (output/'Delivery Report.txt').read_text(encoding='utf-8'))

    def interrupted(self, output):
        stop = threading.Event()
        with self.assertRaises(InterruptedError):
            export(FakeTVPaint(cancel=stop), output, stop)
        return json.loads((output/'export_manifest.json').read_text())

    def test_resume_verifies_and_finishes_missing_frames(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/'out'
            before = self.interrupted(output)
            first = next(iter(before['files']))
            timestamp = (output/first).stat().st_mtime_ns
            api = FakeTVPaint()
            export(api, output, resume=True)
            after = json.loads((output/'export_manifest.json').read_text())
            self.assertEqual(after['status'], 'complete')
            self.assertEqual(len(after['files']), 6)
            self.assertEqual((output/first).stat().st_mtime_ns, timestamp)
            self.assertTrue(api.restored)

    def test_resume_rejects_edited_output_and_keeps_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/'out'
            before = self.interrupted(output)
            path = output/next(iter(before['files']))
            path.write_bytes(path.read_bytes()+b'edited')
            with self.assertRaisesRegex(ValueError, 'modified'):
                export(FakeTVPaint(), output, resume=True)
            self.assertEqual(json.loads((output/'export_manifest.json').read_text())['files'], before['files'])

    def test_resume_rejects_source_changes(self):
        class Changed(FakeTVPaint):
            def render(self, frame, path):
                super().render(frame, path)
                path.write_bytes(path.read_bytes()+b'different drawing')
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/'out'
            self.interrupted(output)
            api = Changed()
            with self.assertRaisesRegex(ValueError, 'drawings changed'):
                export(api, output, resume=True)
            self.assertTrue(api.restored)

    def test_resume_recovers_crash_between_png_and_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/'out'
            before = self.interrupted(output)
            first = output/next(iter(before['files']))
            (first.parent/'A_B_002.png').write_bytes(first.read_bytes())
            export(FakeTVPaint(), output, resume=True)
            self.assertEqual(json.loads((output/'export_manifest.json').read_text())['status'], 'complete')

    def test_changed_scene_stops_before_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            api = FakeTVPaint()
            expected = api.inspect()
            expected['project_id'] = 100
            with self.assertRaisesRegex(ValueError, 'scene changed'):
                export(api, Path(tmp)/'out', expected=expected)
            self.assertFalse((Path(tmp)/'out').exists())

    def test_discreet_preflight_has_actionable_notices(self):
        info = FakeTVPaint().inspect()
        task = plan(info, Path('out'))
        self.assertIn('duplicate', task['notices'][-1])
        for opts in [Options([], 7, 9), Options(first=1), Options(prefix='../bad'), Options(padding=0)]:
            with self.assertRaises(ValueError):
                plan(info, Path('out'), opts)
        with self.assertRaisesRegex(ValueError, 'too long'):
            plan(info, Path('x'*240))
        with tempfile.TemporaryDirectory() as tmp, patch('export_options.tempfile.TemporaryFile', side_effect=PermissionError):
            with self.assertRaisesRegex(ValueError, 'Cannot write'):
                check_writable(tmp)

    def test_preferences_roundtrip_and_corrupt_file(self):
        with tempfile.TemporaryDirectory() as tmp, patch('export_options.settings_path', return_value=Path(tmp)/'settings.json'):
            values = {'parent': tmp, 'prefix': 'SH010', 'numbering': '1001', 'padding': '4'}
            write_settings(values)
            self.assertEqual(read_settings(), values)
            (Path(tmp)/'settings.json').write_text('invalid')
            self.assertEqual(read_settings(), {})


if __name__ == '__main__':
    unittest.main()
