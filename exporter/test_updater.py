"""Release validation and updates against temporary, fake installations."""
from io import BytesIO
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import updater


class UpdaterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / 'app'
        self.root.mkdir()
        self.payload = {name: b'new application file' for name in updater.PAYLOAD_FILES}
        self.payload['version.ini'] = b'[app]\nversion=1.0.1\n'
        self.payload['requirements.txt'] = b'pytvpaint==1.1.2\n'
        self.payload['setup_steps.py'] = b'CONFIG = {"11.7.3": {"sha256": "same bridge"}}\n'
        for name in updater.PAYLOAD_FILES:
            (self.root / name).write_bytes(b'old application file')
        (self.root / 'version.ini').write_bytes(b'[app]\nversion=1.0.0\n')
        (self.root / 'requirements.txt').write_bytes(self.payload['requirements.txt'])
        (self.root / 'setup_steps.py').write_bytes(self.payload['setup_steps.py'])
        (self.root / 'installation.json').write_text(json.dumps({'app_id': updater.APP_ID, 'root': str(self.root)}))
        for name in ('settings.json', 'unins000.exe', 'my_scene.tvpp'):
            (self.root / name).write_bytes(b'keep unchanged')
        for name in ('venv', 'python', 'downloads', 'exports'):
            (self.root / name).mkdir()
            (self.root / name / 'keep.txt').write_bytes(b'keep unchanged')

    def archive(self, entries=None):
        archive = self.base / 'update.zip'
        with zipfile.ZipFile(archive, 'w') as stream:
            for name, data in (entries or self.payload).items():
                stream.writestr(name, data)
        return archive, hashlib.sha256(archive.read_bytes()).hexdigest()

    def release(self):
        return {'tag_name': 'v1.0.1', 'draft': False, 'prerelease': False, 'body': 'New features', 'assets': [{
            'name': 'TVPaint_Layer_Exporter_1.0.1_CMD.zip', 'size': 1024, 'digest': 'sha256:' + 'a'*64,
            'browser_download_url': f'https://github.com/{updater.REPOSITORY}/releases/download/v1.0.1/TVPaint_Layer_Exporter_1.0.1_CMD.zip'}]}

    def check(self, data, current='1.0.0'):
        return updater.check_release(current, lambda request, timeout: BytesIO(json.dumps(data).encode()))

    def test_versions_and_stable_release_selection(self):
        self.assertGreater(updater.version_tuple('1.10.0'), updater.version_tuple('1.9.9'))
        self.assertIsNone(self.check(self.release(), current='1.0.1'))
        self.assertIsNone(self.check(self.release(), current='2.0.0'))
        for key in ('prerelease', 'draft'):
            data = self.release()
            data[key] = True
            self.assertIsNone(self.check(data))
        release = self.check(self.release())
        self.assertEqual(release['version'], '1.0.1')
        self.assertEqual(release['sha256'], 'a'*64)
        for value in ('main', '1.0', '../1.0.1', '1.0.1-beta', '01.0.0'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                updater.version_tuple(value)

    def test_untrusted_asset_metadata_is_rejected(self):
        for key, value in [('digest', None), ('size', -1), ('size', updater.MAX_PACKAGE+1),
                           ('browser_download_url', 'https://example.com/exporter.zip')]:
            data = self.release()
            data['assets'][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.check(data)
        data = self.release()
        data['assets'] *= 2
        with self.assertRaises(ValueError):
            self.check(data)

    def test_download_integrity_failure_keeps_app_unchanged(self):
        content = b'update bytes'
        release = {'url': 'https://github.com/package.zip', 'size': len(content), 'sha256': hashlib.sha256(content).hexdigest()}
        target = self.base / 'download.zip'
        updater.download_package(release, target, lambda request, timeout: BytesIO(content))
        self.assertEqual(target.read_bytes(), content)
        with self.assertRaises(FileExistsError):
            updater.download_package(release, target, lambda request, timeout: BytesIO(content))
        self.assertEqual(target.read_bytes(), content)
        target.unlink()
        for data in (b'short', content+b'extra', b'wrong bytes!'):
            with self.subTest(data=data), self.assertRaises(ValueError):
                updater.download_package(release, target, lambda request, timeout: BytesIO(data))
            self.assertFalse(target.exists())
        self.assertEqual(updater.installed_version(self.root), '1.0.0')

    def test_success_preserves_settings_environment_exports_and_uninstaller(self):
        archive, digest = self.archive()
        updater.apply_payload(self.root, archive, '1.0.1', digest, self.base/'backup')
        self.assertEqual(updater.installed_version(self.root), '1.0.1')
        self.assertEqual((self.root/'exporter_ui.py').read_bytes(), self.payload['exporter_ui.py'])
        self.assertEqual((self.base/'backup/exporter_ui.py').read_bytes(), b'old application file')
        for name in ('settings.json', 'unins000.exe', 'my_scene.tvpp', 'venv/keep.txt', 'python/keep.txt', 'downloads/keep.txt', 'exports/keep.txt'):
            self.assertEqual((self.root/name).read_bytes(), b'keep unchanged')
        with self.assertRaisesRegex(ValueError, 'already installed'):
            updater.apply_payload(self.root, archive, '1.0.1', digest, self.base/'backup2')

    def test_failed_file_replacement_rolls_back(self):
        archive, digest = self.archive()
        original = {name: (self.root/name).read_bytes() for name in updater.PAYLOAD_FILES}
        real_write = updater.atomic_write
        failed = False
        def write(path, data):
            nonlocal failed
            if path.name == 'exporter_ui.py' and not failed:
                failed = True
                raise PermissionError('File is locked')
            real_write(path, data)
        with patch('updater.atomic_write', side_effect=write), self.assertRaisesRegex(RuntimeError, 'previous application files were restored'):
            updater.apply_payload(self.root, archive, '1.0.1', digest, self.base/'backup')
        for name, data in original.items():
            self.assertEqual((self.root/name).read_bytes(), data)

    def test_dependencies_or_wrong_version_require_full_installer(self):
        for name, data in [('requirements.txt', b'pytvpaint==99.0.0'), ('version.ini', b'[app]\nversion=4.0.0\n'),
                           ('setup_steps.py', b'CONFIG = {"11.7.3": {"sha256": "different bridge"}}\n')]:
            payload = dict(self.payload)
            payload[name] = data
            archive, digest = self.archive(payload)
            with self.subTest(name=name), self.assertRaises(ValueError):
                updater.apply_payload(self.root, archive, '1.0.1', digest, self.base/'backup')
            self.assertEqual(updater.installed_version(self.root), '1.0.0')
            self.assertFalse((self.base/'backup').exists())

    def test_unexpected_paths_settings_and_bad_hash_are_rejected(self):
        for name in ('../outside.txt', 'settings.json', 'venv/anything.py', 'C:/outside.txt'):
            payload = {**self.payload, name: b'invalid entry'}
            archive, digest = self.archive(payload)
            with self.subTest(name=name), self.assertRaises(ValueError):
                updater.apply_payload(self.root, archive, '1.0.1', digest, self.base/'backup')
        archive, _ = self.archive()
        with self.assertRaises(ValueError):
            updater.validated_payload(archive, '1.0.1', '0'*64)
        self.assertEqual(updater.installed_version(self.root), '1.0.0')

    def test_source_folder_without_installation_marker_is_not_overwritten(self):
        (self.root/'installation.json').unlink()
        archive, digest = self.archive()
        with self.assertRaises(OSError):
            updater.apply_payload(self.root, archive, '1.0.1', digest, self.base/'backup')
        self.assertEqual(updater.installed_version(self.root), '1.0.0')

    def test_helper_starts_as_separate_process_with_parent_pid(self):
        archive, digest = self.archive()
        release = {'version': '1.0.1', 'sha256': digest}
        with patch('updater.subprocess.Popen') as popen:
            updater.launch_helper(self.root, archive, release, self.base)
        args = popen.call_args.args[0]
        self.assertIn('--wait-pid', args)
        self.assertIn('--apply', args)
        self.assertEqual(args[2], str(self.base/'update_runner.py'))


if __name__ == '__main__':
    unittest.main()
