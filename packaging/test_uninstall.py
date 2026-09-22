import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import subprocess
import sys
import os
import shutil

import uninstall


class UninstallTests(unittest.TestCase):
    def marker(self, root):
        (root/'installation.json').write_text(json.dumps({'app_id': uninstall.APP_ID, 'root': str(root.resolve())}))

    def test_preserves_exports_shared_python_and_unknown_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            self.marker(root)
            for folder in ('venv', 'python', 'my exports', 'downloads'):
                (root/folder).mkdir()
                (root/folder/'keep.txt').write_text('data')
            (root/'export_layers.py').write_text('app')
            uninstall.remove(root)
            self.assertFalse((root/'venv').exists())
            self.assertFalse((root/'export_layers.py').exists())
            for folder in ('python', 'my exports', 'downloads'):
                self.assertEqual((root/folder/'keep.txt').read_text(), 'data')

    def test_unmarked_folder_never_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root/'export_layers.py').write_text('keep')
            with self.assertRaises(FileNotFoundError):
                uninstall.remove(root)
            self.assertTrue((root/'export_layers.py').exists())

    def test_declining_uninstall_preserves_launcher(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            self.marker(root)
            (root/'Uninstall.bat').write_text('keep')
            with patch.object(uninstall, '__file__', str(root/'uninstall.py')), patch('builtins.input', return_value='n'):
                self.assertEqual(uninstall.main(), 2)
            self.assertEqual((root/'Uninstall.bat').read_text(), 'keep')

    def test_redirected_tree_rejected_before_deletion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            self.marker(root)
            (root/'venv').mkdir()
            (root/'venv/file').write_text('keep')
            with patch('uninstall.os.walk', return_value=[(str(root/'venv'), [], ['../../outside'])]):
                with self.assertRaises((ValueError, FileNotFoundError)):
                    uninstall.remove(root)
            self.assertTrue((root/'venv/file').exists())

    @unittest.skipUnless(os.name == 'nt', 'Windows BAT')
    def test_bat_finds_base_python_in_path_with_spaces(self):
        with tempfile.TemporaryDirectory(prefix='uninstall check ') as tmp:
            root = Path(tmp)
            subprocess.run([sys.executable, '-m', 'venv', '--without-pip', str(root/'venv')], check=True)
            shutil.copy2(Path(__file__).parent/'Uninstall.bat', root/'Uninstall.bat')
            (root/'uninstall.py').write_text("print('UNINSTALL_LAUNCH_OK')")
            result = subprocess.run(['cmd.exe', '/d', '/c', str(root/'Uninstall.bat')], input='\n', capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            self.assertIn('UNINSTALL_LAUNCH_OK', result.stdout)
            self.assertFalse((root/'Uninstall.bat').exists())
