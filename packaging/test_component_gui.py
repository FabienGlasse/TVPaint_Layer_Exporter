"""Hidden-window checks; all component locations are simulated."""
from pathlib import Path
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch

import component_cleanup as cleanup


class ComponentGuiTests(unittest.TestCase):
    def check_window(self, select):
        original_tk = tk.Tk
        seen = []
        def factory():
            window = original_tk()
            window.attributes('-alpha', 0)
            def inspect():
                box = window.winfo_children()[0]
                checks = [child for child in box.winfo_children() if isinstance(child, ttk.Checkbutton)]
                seen.extend(check.instate(['selected']) for check in checks)
                if select:
                    checks[0].invoke()
                    checks[1].invoke()
                next(child for child in box.winfo_children() if isinstance(child, ttk.Button)).invoke()
            window.after(150, inspect)
            return window
        with patch('tkinter.Tk', side_effect=factory), patch.object(cleanup, 'availability', return_value={
                'python': (Path('Python installer.exe'), ''), 'bridge': (Path('TVPaint/plugins/bridge.dll'), '')}):
            result = cleanup.choose_components(Path('unused'), gui=True)
        self.assertEqual(seen, [False, False])
        self.assertEqual(result, {'python': select, 'bridge': select})

    def test_defaults_keep_both(self):
        self.check_window(False)

    def test_both_can_be_selected_independently(self):
        self.check_window(True)
