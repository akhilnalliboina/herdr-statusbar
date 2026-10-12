import json
import os
from pathlib import Path
import subprocess
import tempfile
import tomllib
import unittest
from unittest.mock import patch

from install import configure, managed_entry, patch_config


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="installer tests ")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.config = self.directory / "config.toml"
        self.settings = self.directory / "options/config.toml"
        self.state = self.directory / "state"
        self.root = self.directory / "source with spaces"
        self.entry = managed_entry(self.root, self.settings, self.state)

    def test_existing_settings_and_comments_are_preserved(self):
        source = '# keep me\n[keys]\nprefix = "ctrl+a"\n[ui]\ntab_bar_position = "top"\ntab_bar_right = [\n  { type = "datetime", format = "%H:%M" }, # keep clock\n]\n[theme]\nname = "catppuccin"\n'
        result = patch_config(source, self.entry)
        self.assertIn("# keep me", result)
        self.assertIn("# keep clock", result)
        self.assertEqual(tomllib.loads(result)["keys"], tomllib.loads(source)["keys"])
        self.assertEqual(patch_config(result), source)

    def test_top_and_bottom_placement_preserved_through_setup_and_removal(self):
        for position in ('top', 'bottom'):
            with self.subTest(position=position):
                source = f'[ui]\ntab_bar_position = "{position}"\ntab_bar_right = []\n'
                self.config.write_text(source)
                configure(self.config, self.settings, self.state, self.root, reload=False)
                self.assertEqual(tomllib.loads(self.config.read_text())['ui']['tab_bar_position'], position)
                self.assertIsNone(configure(self.config, self.settings, self.state, self.root, reload=False))
                configure(self.config, self.settings, self.state, self.root, remove=True, reload=False)
                self.assertEqual(tomllib.loads(self.config.read_text()), tomllib.loads(source))

    def test_reconfigure_is_exact_noop(self):
        source = '[ui]\ntab_bar_right = []\n'
        first = patch_config(source, self.entry)
        self.assertEqual(patch_config(first, self.entry), first)

    def test_one_line_array_and_brackets_in_strings(self):
        source = '[ui]\ntab_bar_right = [{ type = "text", text = "] # [" }]\n'
        result = patch_config(source, self.entry)
        self.assertEqual(tomllib.loads(result)["ui"]["tab_bar_right"][1]["text"], "] # [")

    def test_multiline_string_in_array(self):
        source = '[ui]\ntab_bar_right = [{type="text", text="""first\n[not a section]\n]"""}]\n'
        self.assertEqual(len(tomllib.loads(patch_config(source, self.entry))["ui"]["tab_bar_right"]), 2)

    def test_ui_table_and_missing_array_are_created(self):
        for source in ("", '[theme]\nname="terminal"\n', '[ui]\nsidebar_width=28\n'):
            with self.subTest(source=source):
                result = patch_config(source, self.entry)
                self.assertEqual(len(tomllib.loads(result)["ui"]["tab_bar_right"]), 1)

    def test_invalid_or_unsupported_config_is_not_modified(self):
        for source in ('invalid', '[ui]\ntab_bar_right="wrong"\n',
                       'ui = { tab_bar_right = [] }\n'):
            with self.subTest(source=source):
                with self.assertRaises(ValueError):
                    patch_config(source, self.entry)

    def test_edited_or_duplicate_marker_is_refused(self):
        result = patch_config('[ui]\ntab_bar_right=[]\n', self.entry)
        with self.assertRaises(ValueError):
            patch_config(result.replace('interval_seconds = 5', 'interval_seconds = 9'))
        with self.assertRaises(ValueError):
            patch_config(result.replace(self.entry, self.entry + self.entry))

    def test_marker_inside_unrelated_string_is_not_deleted(self):
        with self.assertRaises(ValueError):
            patch_config('[ui]\nwindow_title="# herdr-statusbar:entry"\n')

    def test_install_backup_permissions_and_idempotency(self):
        original = '[keys]\nprefix="ctrl+a"\n'
        self.config.write_text(original)
        self.config.chmod(0o640)
        backup = configure(self.config, self.settings, self.state, self.root, reload=False)
        self.assertEqual(backup.read_text(), original)
        self.assertEqual(backup.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o640)
        self.assertEqual(self.settings.stat().st_mode & 0o777, 0o600)
        before = self.config.read_text()
        self.assertIsNone(configure(self.config, self.settings, self.state, self.root, reload=False))
        self.assertEqual(self.config.read_text(), before)
        self.assertEqual(len(list((self.state / "backups").glob("*.toml"))), 1)

    def test_unconfigure_preserves_later_user_edits(self):
        self.config.write_text('[ui]\ntab_bar_right=[]\n')
        configure(self.config, self.settings, self.state, self.root, reload=False)
        self.config.write_text(self.config.read_text() + '[theme]\nname="terminal"\n')
        configure(self.config, self.settings, self.state, self.root, remove=True, reload=False)
        self.assertEqual(tomllib.loads(self.config.read_text())["theme"]["name"], "terminal")
        self.assertEqual(tomllib.loads(self.config.read_text())["ui"]["tab_bar_right"], [])
        self.assertTrue(self.settings.exists())

    def test_reload_failure_restores_original(self):
        source = '[ui]\ntab_bar_right=[]\n'
        self.config.write_text(source)
        with patch('install.subprocess.run', side_effect=subprocess.CalledProcessError(1, 'herdr')):
            with self.assertRaisesRegex(ValueError, "reload failed"):
                configure(self.config, self.settings, self.state, self.root)
        self.assertEqual(self.config.read_text(), source)

    def test_reload_rejection_with_zero_exit_restores_original(self):
        source = '[ui]\ntab_bar_right=[]\n'
        self.config.write_text(source)
        rejected = subprocess.CompletedProcess([], 0, b'{"result":{"status":"rejected"}}', b'')
        with patch('install.subprocess.run', return_value=rejected):
            with self.assertRaises(ValueError):
                configure(self.config, self.settings, self.state, self.root)
        self.assertEqual(self.config.read_text(), source)

    def test_moved_checkout_replaces_only_managed_entry(self):
        self.config.write_text('[ui]\ntab_bar_right=[{type="text",text="keep"}]\n')
        configure(self.config, self.settings, self.state, self.root, reload=False)
        moved = self.directory / 'new source'
        configure(self.config, self.settings, self.state, moved, reload=False)
        entries = tomllib.loads(self.config.read_text())['ui']['tab_bar_right']
        self.assertEqual(len(entries), 2)
        self.assertIn(str(moved), entries[0]['command'])
        self.assertEqual(entries[1]['text'], 'keep')

    def test_first_install_reload_failure_restores_absence(self):
        with patch('install.subprocess.run', side_effect=FileNotFoundError()):
            with self.assertRaises(ValueError):
                configure(self.config, self.settings, self.state, self.root)
        self.assertFalse(self.config.exists())
        self.assertEqual(len(list((self.state / 'backups').glob('*.absent'))), 1)

    def test_symlink_config_is_rejected_without_writes(self):
        other = self.directory / "other"
        other.write_text("untouched")
        self.config.symlink_to(other)
        with self.assertRaises(ValueError):
            configure(self.config, self.settings, self.state, self.root, reload=False)
        self.assertEqual(other.read_text(), "untouched")
        self.assertFalse(self.settings.exists())

    def test_cli_paths_with_spaces_and_no_reload(self):
        cli = Path(__file__).resolve().parents[1] / 'cli.py'
        import sys
        result = subprocess.run([sys.executable, str(cli), 'configure', '--no-reload',
                                 '--herdr-config', str(self.config), '--settings', str(self.settings),
                                 '--state', str(self.state)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        command = tomllib.loads(self.config.read_text())['ui']['tab_bar_right'][0]['command']
        env = dict(os.environ)
        env.pop('HERDR_ACTIVE_PANE_CWD', None)
        env.pop('HERDR_PANE_ID', None)
        result = subprocess.run(command, shell=True, capture_output=True, text=True, env=env)
        self.assertEqual((result.returncode, result.stderr), (0, ''))
        self.assertTrue(result.stdout.startswith('CPU '), result.stdout)
