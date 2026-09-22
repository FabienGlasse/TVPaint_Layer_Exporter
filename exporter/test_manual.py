import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
import threading

from export_layers import TVPaint, export
from export_options import Options, plan, new_output_folder, check_sequence_conflicts
from test_export_layers import FakeTVPaint


class ManualTests(unittest.TestCase):
    def test_combined_sequence_uses_top_layer_and_one_frame_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            api = FakeTVPaint()
            output = export(api, Path(tmp)/'out', options=Options(combine=True))
            manifest = json.loads((output/'export_manifest.json').read_text())
            self.assertEqual(len(api.rendered), 3)
            self.assertEqual(manifest['layers'][0]['source_ids'], [3, 4])
            self.assertEqual(manifest['layers'][0]['folder'], 'A_B')
            self.assertEqual(manifest['total'], 3)
            self.assertTrue(api.restored)

    def test_combined_visibility_is_exact_then_restored(self):
        visible = {3: False, 4: True, 5: True}
        selected = []
        calls = []
        api = TVPaint.__new__(TVPaint)
        api.scene_layer_ids = list(visible)
        api.send = lambda *args, **kwargs: calls.append(args) or 'current'
        api.g = SimpleNamespace(tv_layer_set=selected.append, tv_layer_image=lambda frame: None,
                                tv_layer_display_set=lambda key, value: visible.update({key: value}))
        state = dict(layer=5, frame=0, background='none', save='png', alpha='nopremultiply')
        layers = [dict(id=key, visible=value) for key, value in visible.items()]
        api.prepare(state, {'combine': True})
        api.activate(dict(id=3, source_ids=[3, 4]))
        self.assertEqual(visible, {3: True, 4: True, 5: False})
        self.assertIn(('tv_Display', 'all'), calls)
        self.assertEqual(api.restore(state, layers), [])
        self.assertEqual(visible, {3: False, 4: True, 5: True})
        self.assertEqual(selected[-1], 5)

    def test_reuse_appends_log_and_replaces_only_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/'out'
            export(FakeTVPaint(), output, options=Options(combine=True, sequence_name='Character'), reuse_folder=True)
            original = (output/'Character/Character_001.png').read_bytes()
            export(FakeTVPaint(), output, options=Options([4], combine=True, sequence_name='Shadow'), reuse_folder=True)
            manifest = json.loads((output/'export_manifest.json').read_text())
            self.assertEqual(manifest['layers'][0]['name'], 'Shadow')
            log = (output/'Delivery Report.txt').read_text(encoding='utf-8')
            self.assertEqual(log.count('DELIVERY REPORT'), 1)
            self.assertEqual(log.count('Export started:'), 2)
            self.assertIn('Character', log)
            self.assertIn('Shadow', log)
            self.assertEqual((output/'Character/Character_001.png').read_bytes(), original)
            before_manifest = (output/'export_manifest.json').read_bytes()
            with self.assertRaisesRegex(ValueError, 'already an export'):
                export(FakeTVPaint(), output, options=Options(combine=True, sequence_name='Character'), reuse_folder=True)
            self.assertEqual((output/'export_manifest.json').read_bytes(), before_manifest)
            self.assertEqual((output/'Delivery Report.txt').read_text(encoding='utf-8'), log)

    def test_flat_conflicts_across_format_and_numbering(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/'out'
            export(FakeTVPaint(), output, options=Options(combine=True, sequence_name='Group', layer_folders=False), reuse_folder=True)
            task = plan(FakeTVPaint().inspect(), output, Options(combine=True, sequence_name='group', numbering=1001, image_format='TIFF'))
            with self.assertRaisesRegex(ValueError, 'already an export'):
                check_sequence_conflicts(output, task)

    def test_combined_resume_in_shared_folder_preserves_earlier_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/'out'
            export(FakeTVPaint(), output, options=Options(combine=True, sequence_name='Earlier'), reuse_folder=True)
            stop = threading.Event()
            with self.assertRaises(InterruptedError):
                export(FakeTVPaint(cancel=stop), output, stop,
                       options=Options(combine=True, sequence_name='Later'), reuse_folder=True)
            export(FakeTVPaint(), output, resume=True, reuse_folder=True)
            self.assertTrue((output/'Earlier/Earlier_003.png').is_file())
            self.assertTrue((output/'Later/Later_003.png').is_file())
            self.assertEqual(json.loads((output/'export_manifest.json').read_text())['status'], 'complete')
            self.assertEqual((output/'Delivery Report.txt').read_text(encoding='utf-8').count('Export started:'), 3)

    def test_folder_timestamp_has_seconds_and_safe_collision_suffix(self):
        with tempfile.TemporaryDirectory() as tmp:
            now = datetime(2026, 9, 16, 14, 33, 3, 257082)
            first = new_output_folder(tmp, now)
            self.assertEqual(first.name, 'TVPaint_export_20260916_143303')
            first.mkdir()
            self.assertEqual(new_output_folder(tmp, now).name, first.name+'_2')

    def test_manual_overwrite_removes_stale_matching_frames_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/'out'
            export(FakeTVPaint(), output, options=Options(combine=True, sequence_name='Character'), reuse_folder=True)
            export(FakeTVPaint(), output, options=Options([4], combine=True, sequence_name='Shadow'), reuse_folder=True)
            shadow = (output/'Shadow'/'Shadow_003.png').read_bytes()
            export(FakeTVPaint(), output,
                   options=Options(combine=True, sequence_name='Character', first=7, last=8),
                   reuse_folder=True, overwrite=True)
            self.assertFalse((output/'Character'/'Character_003.png').exists())
            self.assertEqual((output/'Shadow'/'Shadow_003.png').read_bytes(), shadow)
            self.assertEqual((output/'Delivery Report.txt').read_text(encoding='utf-8').count('Export started:'), 3)


if __name__ == '__main__':
    unittest.main()
