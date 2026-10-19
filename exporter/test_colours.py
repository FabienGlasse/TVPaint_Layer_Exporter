"""Colour recognition, grouping and resumable combined exports."""
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest

from export_layers import TVPaint, export
from export_options import Options, plan
from test_export_layers import FakeTVPaint
from colour_names import PALETTE, universal_colour_name, oklab


class ColourScene(FakeTVPaint):
    def inspect(self):
        info = super().inspect()
        info['layers'] = [
            dict(id=10, name='Folder', is_folder=True, visible=False),
            dict(id=3, name='Red top', visible=True, colour_index=1, colour_name='Character', colour_rgb=[255, 0, 0]),
            dict(id=4, name='Blue', visible=True, colour_index=2, colour_name='Shadow', colour_rgb=[0, 0, 255]),
            dict(id=5, name='Red bottom', visible=False, colour_index=1, colour_name='Character', colour_rgb=[255, 0, 0]),
            dict(id=6, name='Unassigned', visible=True, colour_index=0, colour_name='Default', colour_rgb=[100, 100, 100]),
        ]
        return info


class ColourTests(unittest.TestCase):
    def test_universal_palette_and_nearby_values(self):
        for name, rgb in PALETTE:
            with self.subTest(name=name):
                self.assertEqual(universal_colour_name(rgb), name)
        self.assertEqual(universal_colour_name([249, 0, 8]), 'Red')
        self.assertEqual(universal_colour_name([8, 12, 245]), 'Blue')
        self.assertEqual(universal_colour_name([120, 122, 121]), 'Grey')
        # Published Oklab conversion checks for linear sRGB primaries.
        for actual, expected in zip(oklab((255, 0, 0)), (0.627955, 0.224863, 0.125846)):
            self.assertAlmostEqual(actual, expected, places=5)

    def test_universal_names_leave_equal_colour_groups_separate(self):
        info = ColourScene().inspect()
        info['layers'][2]['colour_rgb'] = [255, 0, 0]
        task = plan(info, 'out', Options([3, 4, 5], colour_mode=True, colour_naming='universal', prefix='SHOT', folder_prefix='COMP'))
        self.assertEqual([layer['folder'] for layer in task['layers']], ['COMP_Red', 'COMP_Red__2'])
        self.assertEqual([layer['source_ids'] for layer in task['layers']], [[3, 5], [4]])

    def test_universal_missing_rgb_does_not_guess_or_affect_group_names(self):
        for rgb in (None, [], [255, 0], [256, 0, 0], [True, 0, 0], ['red', 0, 0]):
            with self.subTest(rgb=rgb), self.assertRaises(ValueError):
                universal_colour_name(rgb)
        info = ColourScene().inspect()
        info['layers'][1]['colour_rgb'] = None
        with self.assertRaisesRegex(ValueError, 'RGB colour information'):
            plan(info, 'out', Options([3], colour_mode=True, colour_naming='universal'))
        self.assertEqual(plan(info, 'out', Options([3], colour_mode=True, colour_naming='colour'))['layers'][0]['name'], 'Character')

    def test_universal_export_resume_flat_output_and_group_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/'out'
            stop = threading.Event()
            with self.assertRaises(InterruptedError):
                export(ColourScene(cancel=stop), output, stop, options=Options([3, 4, 5], colour_mode=True, colour_naming='universal', layer_folders=False))
            export(ColourScene(), output, resume=True)
            self.assertTrue((output/'Red_003.png').exists())
            self.assertTrue((output/'Blue_003.png').exists())
            data = json.loads((output/'export_manifest.json').read_text())
            self.assertEqual(data['options']['colour_naming'], 'universal')
            self.assertEqual(len(data['files']), 6)
            self.assertIn('Character (#FF0000)', (output/'Delivery Report.txt').read_text(encoding='utf-8'))

    def test_groups_follow_stack_and_keep_nonadjacent_layers_together(self):
        task = plan(ColourScene().inspect(), 'out', Options([3, 4, 5], colour_mode=True, colour_naming='colour'))
        self.assertEqual([x['name'] for x in task['layers']], ['Character', 'Shadow'])
        self.assertEqual(task['layers'][0]['source_ids'], [3, 5])
        self.assertEqual(task['layers'][1]['source_ids'], [4])
        self.assertEqual(task['total'], 6)
        self.assertTrue(task['options']['colour_mode'])
        self.assertFalse(task['options']['combine'])

    def test_duplicate_group_names_and_equal_rgb_stay_distinct(self):
        info = ColourScene().inspect()
        info['layers'][2].update(colour_name='Character', colour_rgb=[255, 0, 0])
        task = plan(info, 'out', Options([3, 4, 5], colour_mode=True, layer_folders=False, colour_naming='colour'))
        self.assertEqual([x['filename'] for x in task['layers']], ['Character', 'Character__2'])
        self.assertEqual([x['source_ids'] for x in task['layers']], [[3, 5], [4]])

    def test_unavailable_colour_blocks_only_colour_mode(self):
        info = FakeTVPaint().inspect()
        with self.assertRaisesRegex(ValueError, 'Colour information is unavailable'):
            plan(info, 'out', Options(colour_mode=True))
        self.assertEqual(len(plan(info, 'out')['layers']), 2)

    def test_bridge_recognition_caches_palette_and_handles_missing_colours(self):
        for version in ('11.7.3', '12.1.0'):
            with self.subTest(version=version):
                api = TVPaint.__new__(TVPaint)
                queries = []
                def colour(clip, index):
                    queries.append((clip, index))
                    return SimpleNamespace(color_r=12, color_g=34, color_b=56, name='Characters')
                api.send = lambda command, index: str([3, 4][index]) if index < 2 else 'none'
                api.g = SimpleNamespace(
                    tv_project_current_id=lambda: 1, tv_clip_current_id=lambda: 2,
                    tv_layer_info=lambda key: SimpleNamespace(id=key, name=str(key), visibility=True, type='sequence'),
                    tv_layer_color_get=lambda key: 1, tv_layer_color_get_color=colour,
                    tv_project_info=lambda key: SimpleNamespace(start_frame=1, path='test.tvpp', width=10, height=10, frame_rate=24),
                    tv_version=lambda: ['TVPaint', version], tv_clip_name_get=lambda key: 'Clip',
                    tv_first_image=lambda: 0, tv_last_image=lambda: 2)
                info = api.inspect()
                self.assertEqual(queries, [(2, 1)])
                self.assertEqual(info['layers'][1]['colour_rgb'], [12, 34, 56])
                del api.g.tv_layer_color_get
                info = api.inspect()
                self.assertIn('Colour information could not be read', info['colour_warning'])
                self.assertNotIn('colour_index', info['layers'][0])

    def test_colour_display_uses_all_and_exact_group_visibility(self):
        api = TVPaint.__new__(TVPaint)
        calls, visible = [], {}
        api.scene_layer_ids = [3, 4, 5]
        api.send = lambda *args, **kwargs: calls.append(args) or 'current'
        api.g = SimpleNamespace(tv_layer_set=lambda key: None,
                                tv_layer_display_set=lambda key, value: visible.update({key: value}))
        api.prepare({'background': 'none'}, {'colour_mode': True})
        api.activate({'id': 3, 'source_ids': [3, 5]})
        self.assertIn(('tv_Display', 'all'), calls)
        self.assertEqual(visible, {3: True, 4: False, 5: True})

    def test_colour_export_resume_and_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/'out'
            with self.assertRaises(InterruptedError):
                self.interrupt(output)
            export(ColourScene(), output, resume=True)
            manifest = json.loads((output/'export_manifest.json').read_text())
            self.assertEqual(manifest['status'], 'complete')
            self.assertEqual(len(manifest['files']), 6)
            self.assertTrue((output/'Shadow/Shadow_003.png').exists())
            report = (output/'Delivery Report.txt').read_text(encoding='utf-8')
            self.assertIn('Character (#FF0000)', report)
            self.assertIn('Combined layers: Red top, Red bottom', report)

    def interrupt(self, output):
        stop = threading.Event()
        export(ColourScene(cancel=stop), output, stop, options=Options([3, 4, 5], colour_mode=True, colour_naming='colour'))

    def test_layer_colour_naming_top_bottom_and_old_manifest(self):
        info = ColourScene().inspect()
        task = plan(info, 'out', Options([3, 4, 5], colour_mode=True))
        self.assertEqual([layer['name'] for layer in task['layers']], ['Red top', 'Blue'])
        bottom = plan(info, 'out', Options([3, 4, 5], colour_mode=True, colour_naming='bottom'))
        self.assertEqual([layer['name'] for layer in bottom['layers']], ['Red bottom', 'Blue'])
        self.assertEqual(bottom['layers'][0]['source_ids'], [3, 5])
        # Before naming choices, manifests omitted this field and used group names.
        restored = Options.from_manifest({'colour_mode': True, 'layer_ids': [3, 4, 5]})
        self.assertEqual([layer['name'] for layer in plan(info, 'out', restored)['layers']], ['Character', 'Shadow'])

    def test_resume_retains_bottom_layer_naming(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/'out'
            stop = threading.Event()
            with self.assertRaises(InterruptedError):
                export(ColourScene(cancel=stop), output, stop,
                       options=Options([3, 4, 5], colour_mode=True, colour_naming='bottom'))
            export(ColourScene(), output, resume=True)
            self.assertTrue((output/'Red bottom/Red bottom_003.png').exists())

    def test_colour_changes_reject_resume_before_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/'out'
            with self.assertRaises(InterruptedError):
                self.interrupt(output)
            before = (output/'export_manifest.json').read_bytes()
            class Changed(ColourScene):
                def inspect(self):
                    info = super().inspect()
                    info['layers'][3]['colour_index'] = 2
                    return info
            with self.assertRaisesRegex(ValueError, 'Layer colours changed'):
                export(Changed(), output, resume=True)
            self.assertEqual((output/'export_manifest.json').read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
