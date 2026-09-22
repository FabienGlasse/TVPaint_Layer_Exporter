import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from types import SimpleNamespace

from export_layers import TVPaint, export
from export_options import Options, plan
from test_export_layers import FakeTVPaint


class FolderScene(FakeTVPaint):
    def inspect(self):
        info = super().inspect()
        info['layers'].insert(0, dict(id=10, name='Characters', visible=False, is_folder=True))
        return info


class DeliveryTests(unittest.TestCase):
    def test_folder_type_from_bridge_and_visibility_restored(self):
        api = TVPaint.__new__(TVPaint)
        visible = {10: False, 3: False, 4: True}
        api.send = lambda command, index: str([10, 3, 4][index]) if index < 3 else 'none'
        api.g = SimpleNamespace(
            tv_project_current_id=lambda: 1, tv_clip_current_id=lambda: 2,
            tv_layer_info=lambda key: SimpleNamespace(id=key, name=str(key), visibility=visible[key],
                type=SimpleNamespace(value='folder' if key == 10 else 'sequence')),
            tv_project_info=lambda key: SimpleNamespace(start_frame=1, path='test.tvpp', width=10, height=10, frame_rate=24),
            tv_version=lambda: ['TVPaint', '12.1.0'], tv_clip_name_get=lambda key: 'Clip',
            tv_first_image=lambda: 0, tv_last_image=lambda: 2,
            tv_layer_set=lambda key: None, tv_layer_image=lambda frame: None,
            tv_layer_display_set=lambda key, value: visible.update({key: value}))
        info = api.inspect()
        self.assertTrue(info['layers'][0]['is_folder'])
        api.activate(dict(id=3, source_ids=[3]))
        self.assertEqual(visible, {10: True, 3: True, 4: False})
        self.assertEqual(api.restore(dict(layer=3, frame=0), info['layers']), [])
        self.assertEqual(visible, {10: False, 3: False, 4: True})

    def test_complete_stack_once_and_folders_never_render(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/'out'
            api = FolderScene()
            export(api, output, options=Options([4], prefix='SH010', folder_prefix='COMP'), reuse_folder=True)
            self.assertTrue((output/'COMP_A_B'/'SH010_A_B_001.png').is_file())
            self.assertTrue(all(layer != 10 for layer, _, _ in api.rendered))
            export(FolderScene(), output, options=Options([3], prefix='Other'), reuse_folder=True)
            text = (output/'Delivery Report.txt').read_text(encoding='utf-8')
            self.assertEqual(text.count('DELIVERY REPORT'), 1)
            self.assertEqual(text.count('Layer structure'), 1)
            self.assertEqual(text.count('Export started:'), 2)
            self.assertIn('[Characters] (hidden)', text)
            self.assertIn('- A/B (hidden)', text)
            self.assertIn('- A\\B', text)
            self.assertNotIn('Sequence:', text)
            task = plan(api.inspect(), output)
            self.assertEqual(task['options']['layer_ids'], [3, 4])
            with self.assertRaises(ValueError):
                plan(api.inspect(), output, Options([10]))

    @unittest.skipUnless(os.name == 'nt', 'Windows hidden attribute')
    def test_hidden_manifest_updates_resume_and_manual_reuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/'out'
            stop = threading.Event()
            with self.assertRaises(InterruptedError):
                export(FolderScene(cancel=stop), output, stop,
                       options=Options(prefix='SHOT', folder_prefix='COMP'))
            manifest = output/'export_manifest.json'
            self.assertTrue(manifest.stat().st_file_attributes & 2)
            export(FolderScene(), output, resume=True)
            self.assertTrue(manifest.stat().st_file_attributes & 2)
            self.assertEqual(json.loads(manifest.read_text())['status'], 'complete')
            export(FolderScene(), output, options=Options(prefix='Other', layer_folders=False, folder_prefix='IGNORED'), reuse_folder=True)
            self.assertTrue(manifest.stat().st_file_attributes & 2)
            self.assertTrue((output/'Other_A_B_001.png').exists())
            self.assertFalse((output/'Delivery Report.txt').stat().st_file_attributes & 2)

    def test_folder_prefix_separates_sequences_and_overwrite_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/'out'
            export(FolderScene(), output, options=Options([4], folder_prefix='A'), reuse_folder=True)
            export(FolderScene(), output, options=Options([4], folder_prefix='B'), reuse_folder=True)
            export(FolderScene(), output, options=Options([4], folder_prefix='B', first=7, last=7), reuse_folder=True, overwrite=True)
            self.assertTrue((output/'A_A_B'/'A_B_003.png').exists())
            self.assertFalse((output/'B_A_B'/'A_B_003.png').exists())


if __name__ == '__main__':
    unittest.main()
