from pathlib import Path
import hashlib
import json
import tempfile
import unittest
from unittest.mock import patch

import component_cleanup as cleanup


class ComponentCleanupTests(unittest.TestCase):
    def fixture(self, root):
        app = root/'app'
        app.mkdir()
        exe = root/'TVPaint/TVPaint Animation 11.7.3 Pro (64bits).exe'
        exe.parent.mkdir()
        exe.write_bytes(b'exe')
        bridge = exe.parent/'plugins/tvpaint-rpc-1.1.0-tvp-11.dll'
        bridge.parent.mkdir()
        bridge.write_bytes(b'original bridge')
        data = {'app_id': 'FabienGlasse.TVPaintLayerExporter', 'root': str(app.resolve()),
                'bridge': {'tvpaint_exe': str(exe.resolve()), 'path': str(bridge.resolve()),
                           'sha256': hashlib.sha256(bridge.read_bytes()).hexdigest()}}
        (app/'installation.json').write_text(json.dumps(data))
        return app, bridge, data

    def test_keep_both_never_resolves_or_removes_components(self):
        with patch.object(cleanup, 'python_uninstaller') as python, patch.object(cleanup, 'bridge_target') as bridge:
            self.assertIsNone(cleanup.prepare_removal(Path('unused'), {'python': False, 'bridge': False}))
            python.assert_not_called()
            bridge.assert_not_called()

    def test_console_defaults_to_keep(self):
        with patch.object(cleanup, 'availability', return_value={'python': (Path('python.exe'), ''), 'bridge': (Path('bridge.dll'), '')}), patch('builtins.input', return_value=''):
            self.assertEqual(cleanup.choose_components(Path('unused')), {'python': False, 'bridge': False})

    def test_deletes_only_recorded_bridge(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, bridge, data = self.fixture(Path(tmp).resolve())
            other = bridge.parent/'another-plugin.dll'
            other.write_bytes(b'keep')
            with patch('setup_steps.require_tvpaint_closed'), patch('setup_steps.version_of', return_value='11.7.3'):
                cleanup.remove_bridge_file(app)
            self.assertFalse(bridge.exists())
            self.assertEqual(other.read_bytes(), b'keep')

    def test_modified_bridge_is_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, bridge, data = self.fixture(Path(tmp).resolve())
            bridge.write_bytes(b'new version')
            with patch('setup_steps.version_of', return_value='11.7.3'):
                with self.assertRaisesRegex(ValueError, 'changed'):
                    cleanup.bridge_target(app)
            self.assertTrue(bridge.exists())

    def test_path_outside_tvpaint_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            app, bridge, data = self.fixture(root)
            outside = root/'tvpaint-rpc-other.dll'
            outside.write_bytes(bridge.read_bytes())
            data['bridge']['path'] = str(outside)
            (app/'installation.json').write_text(json.dumps(data))
            with patch('setup_steps.version_of', return_value='11.7.3'):
                with self.assertRaisesRegex(ValueError, 'outside'):
                    cleanup.bridge_target(app)
            self.assertTrue(outside.exists())

    def test_running_tvpaint_prevents_removal(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, bridge, _ = self.fixture(Path(tmp).resolve())
            with patch('setup_steps.require_tvpaint_closed', side_effect=RuntimeError('Close TVPaint')), patch('setup_steps.version_of', return_value='11.7.3'):
                with self.assertRaisesRegex(RuntimeError, 'Close TVPaint'):
                    cleanup.remove_bridge_file(app)
            self.assertTrue(bridge.exists())

    def test_private_python_uses_official_installer_not_recursive_delete(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, _, data = self.fixture(Path(tmp).resolve())
            python = app/'python/python.exe'
            python.parent.mkdir()
            python.write_bytes(b'python')
            installer = app/'python-3.13.13-amd64.exe'
            installer.write_bytes(b'installer')
            data['python'] = {'executable': str(python), 'version': '3.13.13', 'installed_by_exporter': True}
            (app/'installation.json').write_text(json.dumps(data))
            self.assertEqual(cleanup.python_uninstaller(app), installer)
            with patch.object(cleanup, 'verify_python_publisher', side_effect=ValueError('untrusted')), patch.object(cleanup, 'remove_bridge') as remove:
                with self.assertRaises(ValueError):
                    cleanup.prepare_removal(app, {'python': True, 'bridge': True})
                remove.assert_not_called()
            self.assertTrue(python.exists())

    def test_python_helper_waits_until_interpreter_exits(self):
        with patch('component_cleanup.subprocess.Popen') as launch:
            cleanup.schedule_python_uninstall(Path('app'), Path('python installer.exe'))
            args, kwargs = launch.call_args
            self.assertIn('Wait-Process', args[0][-1])
            self.assertIn("'/uninstall'", args[0][-1])
            self.assertEqual(kwargs['env']['TVPE_PYTHON_UNINSTALLER'], 'python installer.exe')


if __name__ == '__main__':
    unittest.main()
