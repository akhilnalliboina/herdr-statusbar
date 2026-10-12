import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CLITests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.settings = self.directory / 'settings.toml'
        self.state = self.directory / 'state'
        self.env = {key: value for key, value in os.environ.items() if not key.startswith('HERDR_')}

    def cli(self, command, *extra):
        return subprocess.run([sys.executable, '-B', str(ROOT/'cli.py'), command,
                               '--settings', str(self.settings), '--state', str(self.state), *extra],
                              capture_output=True, text=True, env=self.env, timeout=12)

    def test_system_status_works_without_repository_context(self):
        result = self.cli('bar')
        self.assertEqual((result.returncode, result.stderr), (0, ''))
        self.assertTrue(result.stdout.startswith('CPU '), result.stdout)
        self.assertIn('RAM ', result.stdout)
        self.assertRegex(result.stdout, r'\d{4}-\d{2}-\d{2}')
        self.assertTrue(self.state.exists())

    def test_explicit_cwd_and_local_only(self):
        subprocess.run(['git', 'init', '-q', str(self.directory)], check=True)
        self.settings.write_text('show_pr=false\nshow_cpu=false\nshow_ram=false\nshow_battery=false\nshow_datetime=false\n')
        result = self.cli('bar', '--cwd', str(self.directory))
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, 'Git Δ1\n', ''))

    def test_invalid_settings_fail_closed(self):
        self.settings.write_text('show_pr="true"\n')
        result = self.cli('bar')
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, 'Status config?\n', ''))
        self.assertFalse(self.state.exists())

    def test_open_pr_without_context_fails_without_browser(self):
        result = self.cli('open-pr')
        self.assertEqual(result.returncode, 1)
        self.assertIn('active repository', result.stderr)

    def test_plugin_action_resolves_pane_directory(self):
        fake = self.directory / 'herdr'
        fake.write_text('#!/bin/sh\nprintf \'%s\\n\' \'{"result":{"pane":{"foreground_cwd":"/tmp/fixture"}}}\'\n')
        fake.chmod(0o700)
        self.env.update(HERDR_BIN_PATH=str(fake), HERDR_PANE_ID='test:p1')
        result = self.cli('doctor')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Active repository directory: /tmp/fixture', result.stdout)

    def test_manifest_and_cli_versions_match(self):
        import tomllib
        version = tomllib.loads((ROOT/'herdr-plugin.toml').read_text())['version']
        result = subprocess.run([sys.executable, '-B', str(ROOT/'cli.py'), '--version'],
                                text=True, capture_output=True, check=True)
        self.assertEqual(result.stdout.strip(), f'herdr-statusbar {version}')
