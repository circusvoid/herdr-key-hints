"""依赖问题必须在安装或 doctor 阶段明确暴露。"""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from key_hints.checks import check_environment, swift_compiler
from key_hints.overlay import prepare


class Client:
    def __init__(self, version='herdr 0.9.0'):
        self.version = version
    def call(self, *args, **kwargs):
        return self.version


class DependencyTests(unittest.TestCase):
    def test_rejects_old_herdr_before_runtime(self):
        with self.assertRaisesRegex(ValueError, 'Herdr 0.9.0'):
            check_environment(Client('herdr 0.8.0'), 'herdr')

    def test_herdr_mode_does_not_need_swift(self):
        with patch('key_hints.checks.swift_compiler', side_effect=AssertionError('不应调用编译器')):
            result = check_environment(Client(), 'herdr')
        self.assertEqual(result['renderer'], 'herdr')

    def test_missing_compiler_has_actionable_message(self):
        with patch('key_hints.checks.shutil.which', return_value=None):
            with self.assertRaisesRegex(ValueError, 'Xcode Command Line Tools'):
                swift_compiler()

    def test_overlay_rejects_non_macos(self):
        with patch('key_hints.checks.sys.platform', 'linux'):
            with self.assertRaisesRegex(ValueError, 'macOS'):
                check_environment(Client(), 'overlay')

    def test_cached_native_binary_needs_no_compiler_or_runtime_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp)/'native'
            binary.write_bytes(b'cache fixture')
            binary.chmod(0o700)
            with patch('key_hints.overlay.sys.platform', 'darwin'), \
                 patch('key_hints.overlay.build_path', return_value=binary), \
                 patch('key_hints.checks.swift_compiler', side_effect=AssertionError('不应调用编译器')):
                self.assertEqual(prepare(), binary)


if __name__ == '__main__':
    unittest.main()
