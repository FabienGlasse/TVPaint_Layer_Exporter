"""UI integration checks using a fake TVPaint connection; no live scene changes."""
import json
from pathlib import Path
import tempfile
import time
import tkinter as tk
import unittest
from unittest.mock import patch

from exporter_ui import ExporterWindow
from test_export_layers import FakeTVPaint


class GuiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = tk.Tk()
        self.root.attributes('-alpha', 0)
        self.addCleanup(self.destroy_window)
        self.fake = patch('exporter_ui.TVPaint', FakeTVPaint)
        self.fake.start()
        self.addCleanup(self.fake.stop)
        for name in ('read_settings', 'write_settings'):
            mock = patch('exporter_ui.'+name, return_value={})
            mock.start()
            self.addCleanup(mock.stop)
        self.ui = ExporterWindow(self.root)
        self.root.update()
        self.ui.connect()
        self.wait_idle()

    def wait_idle(self):
        limit = time.monotonic()+5
        while self.ui.busy and time.monotonic()<limit:
            self.root.update()
            time.sleep(.01)
        self.assertFalse(self.ui.busy)
        self.root.update_idletasks()

    def destroy_window(self):
        for callback in self.root.tk.call('after', 'info'):
            self.root.after_cancel(callback)
        self.root.destroy()

    def test_connection_preview_completion_and_layout(self):
        ui = self.ui
        self.assertEqual(len(ui.checks), 2)
        self.assertIn('Connected', ui.connection.get())
        self.assertEqual(ui.scene.get(), '1 / 2')
        self.assertEqual(str(ui.mode_buttons['Auto Mode']['style']), 'ActiveMode.TButton')
        ui.parent.set(self.tmp.name)
        ui.prefix.set('SH010')
        ui.first.set('8')
        ui.last.set('9')
        ui.numbering.set('1001')
        self.assertTrue(ui.validate())
        self.assertIn('SH010_A_B_1001.png', ui.preview.get())
        self.assertIn('duplicate', ui.notice.get())
        requested_minimum = (self.root.winfo_reqwidth(), self.root.winfo_reqheight())
        self.root.geometry('760x710')
        self.root.update()
        self.assertGreaterEqual(self.root.winfo_width(), requested_minimum[0])
        self.assertGreaterEqual(self.root.winfo_height(), requested_minimum[1])
        # All visible sections remain within the initial window height.
        for widget in (ui.start_button, ui.report_box, ui.open_button, ui.format_picker, ui.background_check, ui.flat_check):
            bottom = widget.winfo_rooty()-self.root.winfo_rooty()+widget.winfo_height()
            self.assertLessEqual(bottom, self.root.winfo_height())
            right = widget.winfo_rootx()-self.root.winfo_rootx()+widget.winfo_width()
            self.assertLessEqual(right, self.root.winfo_width())
        ui.start()
        self.wait_idle()
        self.assertEqual(ui.status.get(), 'Export complete.')
        self.assertEqual(ui.counter.get(), '4 / 4 frames')
        self.assertIn('Files: 4 / 4', ui.report_box.get('1.0', 'end'))
        self.assertEqual(str(ui.open_button['state']), 'normal')

    def test_invalid_input_is_inline_and_disables_export(self):
        self.ui.first.set('invalid')
        self.assertFalse(self.ui.validate())
        self.assertIn('whole numbers', self.ui.notice.get())
        self.assertEqual(str(self.ui.start_button['state']), 'disabled')

    def test_reconnect_clears_error_and_formats_tvpaint_name(self):
        ui = self.ui
        ui.events.put(('connection_error', 'Could not establish connection with a tvpaint instance before timeout !'))
        ui.poll()
        self.assertEqual(ui.status.get(), 'Connection details: Could not establish connection with a TVPaint instance before timeout!')
        self.assertEqual(str(ui.refresh_button['text']), 'Connect')
        ui.connect()
        self.wait_idle()
        self.assertIn('Connected', ui.connection.get())
        self.assertEqual(ui.status.get(), '')
        self.assertEqual(str(ui.refresh_button['text']), 'Refresh')
        self.assertEqual(str(ui.resume_button['text']), 'Resume interrupted export…')
        self.assertEqual(str(ui.resume_button['style']), 'Quiet.TButton')

    def test_reconnect_failure_in_layer_colours_recovers(self):
        from test_colours import ColourScene
        ui = self.ui
        ui.populate(ColourScene().inspect())
        ui.choose_mode('Colour Mode')
        ui.events.put(('connection_error', 'TVPaint disconnected'))
        ui.poll()
        self.assertIsNone(ui.info)
        self.assertEqual(str(ui.start_button['state']), 'disabled')
        with patch('exporter_ui.TVPaint', ColourScene):
            ui.connect()
            self.wait_idle()
        self.assertIn('Connected', ui.connection.get())
        self.assertEqual(len(ui.colour_checks), 3)

    def test_tooltips_and_contextual_tutorial_navigation(self):
        ui = self.ui
        tips = {tip.widget: tip for tip in ui.tooltips}
        self.assertIn('same folder', tips[ui.mode_buttons['Manual Mode']].text)
        self.assertEqual(tips[ui.mode_buttons['Auto Mode']].text, 'Auto Mode exports checked layers separately.')
        for widget in (ui.start_button, ui.background_check):
            self.assertEqual(tips[widget].text, '')
            tips[widget].show()
            self.assertIsNone(tips[widget].window)
        tips[ui.refresh_button].show()
        self.assertIsNotNone(tips[ui.refresh_button].window)
        tips[ui.refresh_button].hide()
        self.assertIsNone(tips[ui.refresh_button].window)
        ui.start_tutorial()
        tour = ui.tutorial
        self.assertEqual(tour.index, 0)
        self.assertIn('Connect to TVPaint', str(tour.heading['text']))
        self.assertNotIn('Close', [str(widget['text']) for widget in tour.back.master.winfo_children()])
        tour.move(1)
        self.assertIn('LAYER COLORS', str(tour.body['text']))
        tour.move(-1)
        self.assertEqual(tour.index, 0)
        while tour.index < len(tour.steps)-1:
            tour.move(1)
        self.assertEqual(str(tour.next['text']), 'Finish')
        tour.move(1)
        self.assertFalse(tour.window.winfo_exists())
        ui.start_tutorial()
        self.assertTrue(ui.tutorial.window.winfo_exists())
        ui.tutorial.close()

    def test_colour_buttons_selection_and_group_export(self):
        from test_colours import ColourScene
        ui = self.ui
        ui.populate(ColourScene().inspect())
        ui.parent.set(self.tmp.name)
        ui.choose_mode('Colour Mode')
        self.assertEqual([str(button['text']) for button in ui.mode_buttons.values()],
                         ['AUTO', 'MANUAL', 'LAYER COLORS'])
        for mode, button in ui.mode_buttons.items():
            self.assertEqual(str(button['style']), 'ActiveMode.TButton' if mode == 'Colour Mode' else 'TButton')
        self.assertEqual(ui.options().layer_ids, [3, 4])
        self.assertFalse(ui.checks[5].get())
        self.assertFalse(ui.checks[6].get())
        self.assertNotIn(10, ui.checks)
        self.assertTrue(ui.validate())
        self.assertEqual(str(ui.combine_check['state']), 'disabled')
        self.assertFalse(ui.combine_check.winfo_manager())
        self.assertFalse(ui.sections['sequence']['holder'].winfo_manager())
        self.assertTrue(ui.sections['colour_naming']['holder'].winfo_manager())
        self.assertEqual(ui.colour_naming.get(), 'top')
        self.assertEqual([str(widget['text']) for widget in ui.colour_name_radios],
                         ['Use color group names', 'Use universal color names', 'Use top layer', 'Use bottom layer'])
        ui.colour_name_radios[0].invoke()
        ui.validate()
        self.assertEqual(ui.options().colour_naming, 'colour')
        ui.colour_name_radios[1].invoke()
        ui.validate()
        self.assertEqual(ui.options().colour_naming, 'universal')
        self.assertIn('Red_001.png', ui.preview.get())
        ui.colour_name_radios[3].invoke()
        ui.validate()
        self.assertEqual(ui.options().colour_naming, 'bottom')
        ui.colour_name_radios[2].invoke()
        self.assertEqual(str(ui.sequence_entry['state']), 'disabled')
        self.assertIn('alternate', ui.colour_checks[1][1].state())
        ui.colour_checks[1][1].invoke()
        ui.validate()
        self.assertTrue(ui.checks[5].get())
        self.assertEqual(ui.options().layer_ids, [3, 4, 5])
        ui.select('none')
        self.assertFalse(ui.validate())
        ui.colour_checks[1][1].invoke()
        ui.validate()
        self.assertEqual(ui.options().layer_ids, [3, 5])
        with patch('exporter_ui.TVPaint', ColourScene):
            ui.start()
            self.wait_idle()
        self.assertEqual(ui.status.get(), 'Export complete.')
        self.assertTrue((ui.destination/'Red top/Red top_003.png').exists())
        self.assertIsNone(ui.session_folder)
        self.assertFalse(ui.overwrite_button.winfo_manager())
        ui.choose_mode('Manual Mode')
        self.assertTrue(ui.combine.get())
        self.assertFalse(ui.colour_checks)
        ui.choose_mode('Auto Mode')
        self.assertFalse(ui.combine.get())

    def test_colour_resume_restores_mode_and_locks_groups(self):
        from test_colours import ColourScene, ColourTests
        output = Path(self.tmp.name)/'interrupted'
        with self.assertRaises(InterruptedError):
            ColourTests().interrupt(output)
        self.ui.populate(ColourScene().inspect())
        with patch('exporter_ui.filedialog.askdirectory', return_value=str(output)):
            self.ui.load_resume()
        self.assertEqual(self.ui.mode.get(), 'Colour Mode')
        self.assertEqual(self.ui.options().layer_ids, [3, 4, 5])
        self.assertTrue(all('disabled' in widget.state() for _, widget in self.ui.colour_checks.values()))
        with patch('exporter_ui.TVPaint', ColourScene):
            self.ui.start()
            self.wait_idle()
        self.assertEqual(self.ui.status.get(), 'Export complete.')

    def test_universal_resume_restores_naming_and_locks_choices(self):
        from test_colours import ColourScene
        from export_layers import export
        from export_options import Options
        import threading
        output = Path(self.tmp.name)/'universal'
        stop = threading.Event()
        with self.assertRaises(InterruptedError):
            export(ColourScene(cancel=stop), output, stop, options=Options([3, 4, 5], colour_mode=True, colour_naming='universal'))
        self.ui.populate(ColourScene().inspect())
        with patch('exporter_ui.filedialog.askdirectory', return_value=str(output)):
            self.ui.load_resume()
        self.assertEqual(self.ui.colour_naming.get(), 'universal')
        self.assertTrue(all('disabled' in widget.state() for widget in self.ui.colour_name_radios))
        with patch('exporter_ui.TVPaint', ColourScene):
            self.ui.start()
            self.wait_idle()
        self.assertEqual(self.ui.status.get(), 'Export complete.')
        self.assertTrue((output/'Red/Red_003.png').is_file())

    def test_image_format_background_and_flat_preview(self):
        self.ui.parent.set(self.tmp.name)
        self.ui.image_format.set('JPEG')
        self.ui.flat_output.set(True)
        self.assertTrue(self.ui.validate())
        self.assertTrue(self.ui.background.get())
        self.assertEqual(str(self.ui.background_check['state']), 'disabled')
        self.assertTrue(self.ui.preview.get().endswith('A_B_001.jpg'))
        self.assertNotIn('A_B\\', self.ui.preview.get())
        self.assertIn('JPEG files', self.ui.notice.get())
        self.assertEqual(self.root.title(), 'TVPaint Layer Exporter')
        self.ui.image_format.set('PNG')
        self.ui.validate()
        self.assertEqual(str(self.ui.background_check['state']), 'normal')
        before = (self.root.winfo_width(), self.root.winfo_height())
        self.ui.background.set(True)
        self.ui.validate()
        self.root.update_idletasks()
        self.assertEqual((self.root.winfo_width(), self.root.winfo_height()), before)

    def test_resume_locks_original_settings(self):
        from test_export_options import ExportOptionsTests
        output = Path(self.tmp.name)/'interrupted'
        ExportOptionsTests().interrupted(output)
        with patch('exporter_ui.filedialog.askdirectory', return_value=str(output)):
            self.ui.load_resume()
        self.assertEqual(self.ui.resume_folder, output)
        self.assertEqual(str(self.ui.format_picker['state']), 'disabled')
        self.ui.start()
        self.wait_idle()
        self.assertEqual(json.loads((output/'export_manifest.json').read_text())['status'], 'complete')

    def test_manual_session_naming_and_mode_reset(self):
        ui = self.ui
        self.assertEqual(ui.mode.get(), 'Auto Mode')
        self.assertFalse(ui.combine.get())
        ui.parent.set(self.tmp.name)
        ui.mode.set('Manual Mode')
        ui.mode_changed()
        self.assertTrue(ui.combine.get())
        self.assertEqual(str(ui.mode_buttons['Manual Mode']['style']), 'ActiveMode.TButton')
        self.assertEqual(ui.sequence_name.get(), 'A/B')
        ui.use_bottom_layer()
        self.assertEqual(ui.sequence_name.get(), 'A\\B')
        ui.reset_sequence_name()
        self.assertEqual(ui.sequence_name.get(), 'A/B')
        ui.start()
        self.wait_idle()
        session = ui.session_folder
        self.assertIsNotNone(session)
        self.assertIn('already an export', ui.notice.get())
        self.assertTrue(ui.overwrite_button.winfo_manager())
        ui.checks[3].set(False)
        ui.validate()
        self.assertEqual(ui.sequence_name.get(), 'A\\B')
        ui.sequence_name.set('Shadow')
        self.assertTrue(ui.validate())
        ui.start()
        self.wait_idle()
        self.assertEqual(ui.session_folder, session)
        self.assertEqual(ui.destination, session)
        self.assertEqual((session/'Delivery Report.txt').read_text(encoding='utf-8').count('Export started:'), 2)
        ui.checks[3].set(True)
        ui.validate()
        self.assertEqual(ui.sequence_name.get(), 'A/B')
        ui.mode_changed()  # Re-selecting Manual Mode must not end the session.
        self.assertEqual(ui.session_folder, session)
        ui.mode.set('Auto Mode')
        ui.mode_changed()
        self.assertIsNone(ui.session_folder)
        self.assertFalse(ui.combine.get())
        self.assertEqual(str(ui.mode_buttons['Auto Mode']['style']), 'ActiveMode.TButton')
        self.assertFalse(ui.overwrite_button.winfo_manager())
        self.assertEqual(str(ui.parent_entry['state']), 'normal')
        self.assertNotIn('mode', ui.preferences())

    def test_manual_overwrite_replaces_only_matching_sequence(self):
        ui = self.ui
        ui.parent.set(self.tmp.name)
        ui.toggle_mode()
        ui.start()
        self.wait_idle()
        session = ui.session_folder
        original_report = (session/'Delivery Report.txt').read_text(encoding='utf-8')
        self.assertTrue(ui.overwrite_button.winfo_manager())
        ui.approve_overwrite()
        self.assertFalse(ui.overwrite_button.winfo_manager())
        self.assertIn('will be overwritten', ui.notice.get())
        ui.start()
        self.wait_idle()
        self.assertTrue((session/'A_B'/'A_B_003.png').is_file())
        self.assertGreater((session/'Delivery Report.txt').read_text(encoding='utf-8').count('Export started:'),
                           original_report.count('Export started:'))

    def test_sections_and_folder_dividers(self):
        ui = self.ui
        self.assertTrue(all(not item['content'].winfo_manager() for item in ui.sections.values()))
        ui.toggle_section('prefixes')
        self.root.update_idletasks()
        self.assertTrue(ui.folder_prefix_entry.winfo_ismapped())
        ui.folder_prefix.set('OUT')
        ui.prefix.set('SH010')
        info = FakeTVPaint().inspect()
        info['layers'].insert(0, dict(id=10, name='Characters', visible=False, is_folder=True))
        ui.populate(info)
        ui.parent.set(self.tmp.name)
        ui.select('all')
        self.assertTrue(ui.validate())
        self.assertNotIn(10, ui.checks)
        self.assertEqual(ui.options().layer_ids, [3, 4])
        self.assertIn('OUT_A_B', ui.preview.get())
        self.assertIn('SH010_A_B_001.png', ui.preview.get())
        ui.toggle_mode()
        self.root.update_idletasks()
        self.assertTrue(all(not item['content'].winfo_manager() for item in ui.sections.values()))
        for key in ('format', 'frames', 'prefixes', 'sequence'):
            ui.toggle_section(key)
        self.root.update_idletasks()
        self.assertTrue(all(ui.sections[key]['content'].winfo_ismapped() for key in ('format', 'frames', 'prefixes', 'sequence')))
        self.root.geometry('760x710')
        self.root.update()
        for widget in (ui.open_button, ui.report_button, ui.sequence_entry, ui.name_bottom, ui.folder_prefix_entry):
            self.assertTrue(widget.winfo_ismapped())
            self.assertLessEqual(widget.winfo_rooty() - self.root.winfo_rooty() + widget.winfo_height(), self.root.winfo_height())
            self.assertLessEqual(widget.winfo_rootx() - self.root.winfo_rootx() + widget.winfo_width(), self.root.winfo_width())
        ui.set_busy(True)
        ui.set_busy(False)
        ui.select('visible')
        ui.validate()
        self.assertEqual(ui.options().layer_ids, [4])
        ui.toggle_mode()
        self.assertTrue(all(not item['content'].winfo_manager() for item in ui.sections.values()))


if __name__ == '__main__':
    unittest.main()
