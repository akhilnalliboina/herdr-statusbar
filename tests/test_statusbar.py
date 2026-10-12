import fcntl
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from statusbar import Settings, StatusBar, changed_files, execute, github_repository

PR = {"number": 42, "state": "OPEN", "changedFiles": 5, "additions": 128, "deletions": 34}


class StatusBarTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="statusbar tests ")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.repo = self.directory / "repository with spaces"
        self.repo.mkdir()
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.invalid")
        (self.repo / "tracked").write_text("initial\n")
        self.git("add", ".")
        self.git("commit", "-qm", "initial")
        self.git("remote", "add", "origin", "https://github.com/example/project.git")
        self.state = self.directory / "state"
        self.calls = []
        self.now = 1000
        self.response = subprocess.CompletedProcess([], 0, json.dumps(PR).encode(), b"")
        self.availability = patch("statusbar.shutil.which", return_value="gh")
        self.availability.start()
        self.addCleanup(self.availability.stop)

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args],
                              capture_output=True, check=True).stdout

    def run_command(self, argv, cwd, timeout=1):
        if argv[0] == "gh":
            self.calls.append(argv)
            return self.response
        return execute(argv, cwd, timeout)

    def bar(self, settings=Settings()):
        return StatusBar(self.state, settings, run=self.run_command, clock=lambda: self.now)

    def test_real_git_and_remote_pr_format(self):
        (self.repo / "tracked").write_text("changed\n")
        (self.repo / "untracked\nname").write_text("new")
        self.assertEqual(self.bar().collect(self.repo),
                         "Git Δ2 · PR #42 · 5 files · +128 −34")

    def test_remote_formats_and_explicit_repository(self):
        for remote in ('https://github.com/example/project.git',
                       'git@github.com:example/project.git',
                       'ssh://git@github.com/example/project.git',
                       'https://github.com/example/project.git/'):
            self.assertEqual(github_repository(remote), 'github.com/example/project')
        self.assertEqual(github_repository('https://user:secret@github.com/example/project.git'),
                         'github.com/example/project')
        self.assertIsNone(github_repository('/local/repository'))
        self.assertIsNone(github_repository('file:///local/repository'))
        self.bar().collect(self.repo)
        self.assertIn('--repo', self.calls[0])
        self.assertIn('github.com/example/project', self.calls[0])

    def test_unsupported_remote_skips_github(self):
        self.git('remote', 'set-url', 'origin', '/local/repository')
        self.assertEqual(self.bar().collect(self.repo), 'Git Δ0 · PR remote?')
        self.assertEqual(self.calls, [])

    def test_staged_and_unstaged_same_file_counts_once(self):
        (self.repo / "tracked").write_text("staged\n")
        self.git("add", "tracked")
        (self.repo / "tracked").write_text("unstaged\n")
        self.assertEqual(self.bar(Settings(show_pr=False)).collect(self.repo), "Git Δ1")

    def test_rename_counts_once(self):
        self.git("mv", "tracked", "renamed\nfile")
        self.assertEqual(self.bar(Settings(show_pr=False)).collect(self.repo), "Git Δ1")

    def test_clean_tree_and_non_repository(self):
        self.assertEqual(self.bar(Settings(show_pr=False)).collect(self.repo), "Git Δ0")
        self.assertEqual(self.bar().collect(self.directory), "")
        self.assertEqual(self.bar().collect(None), "")
        self.assertEqual(self.calls, [])

    def test_cache_is_shared_across_process_style_instances(self):
        self.bar().collect(self.repo)
        self.now += 100
        self.bar().collect(self.repo)
        self.assertEqual(len(self.calls), 1)
        self.now += 21
        self.bar().collect(self.repo)
        self.assertEqual(len(self.calls), 2)

    def test_switching_branch_does_not_reuse_previous_pr(self):
        self.bar().collect(self.repo)
        self.git("checkout", "-qb", "different")
        self.response = subprocess.CompletedProcess([], 0, json.dumps(dict(PR, number=99)).encode(), b"")
        self.assertIn("PR #99", self.bar().collect(self.repo))
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.calls[-1][3], "different")

    def test_switching_repositories_and_non_repo_does_not_reuse_previous_data(self):
        self.assertIn('PR #42', self.bar().collect(self.repo))
        other = self.directory / 'second repo'
        other.mkdir()
        subprocess.run(['git', 'init', '-q', '-b', 'main', str(other)], check=True)
        subprocess.run(['git', '-C', str(other), 'remote', 'add', 'origin',
                        'https://github.com/example/second.git'], check=True)
        (other / 'untracked').write_text('new')
        self.response = subprocess.CompletedProcess([], 0, json.dumps(dict(PR, number=77)).encode(), b'')
        self.assertEqual(self.bar().collect(other), 'Git Δ1 · PR #77 · 5 files · +128 −34')
        self.assertEqual(self.bar().collect(self.directory), '')
        self.assertEqual(len(self.calls), 2)

    def test_switching_remote_does_not_reuse_previous_pr(self):
        self.bar().collect(self.repo)
        self.git("remote", "set-url", "origin", "https://github.com/other/repo.git")
        self.bar().collect(self.repo)
        self.assertEqual(len(self.calls), 2)

    def test_detached_head_and_missing_remote_skip_github(self):
        self.git("checkout", "--detach", "-q")
        self.assertEqual(self.bar().collect(self.repo), "Git Δ0")
        self.git("checkout", "main", "-q")
        self.git("remote", "remove", "origin")
        self.assertEqual(self.bar().collect(self.repo), "Git Δ0")
        self.assertEqual(self.calls, [])

    def test_git_only_and_pr_only_and_hide_file_count(self):
        self.assertEqual(self.bar(Settings(show_pr=False)).collect(self.repo), "Git Δ0")
        self.assertEqual(self.bar(Settings(show_git=False, show_pr_files=False)).collect(self.repo),
                         "PR #42 · +128 −34")

    def test_no_pr_is_not_an_error_and_is_cached(self):
        self.response = subprocess.CompletedProcess([], 1, b"", b'no pull requests found for branch "main"')
        self.assertEqual(self.bar().collect(self.repo), "Git Δ0")
        self.bar().collect(self.repo)
        self.assertEqual(len(self.calls), 1)

    def test_error_is_visible_and_uses_short_retry_not_stale_data(self):
        self.bar().collect(self.repo)
        self.now += 121
        self.response = subprocess.CompletedProcess([], 1, b"", b"private error detail")
        self.assertEqual(self.bar().collect(self.repo), "Git Δ0 · PR ?")
        self.now += 29
        self.bar().collect(self.repo)
        self.assertEqual(len(self.calls), 2)
        self.now += 2
        self.bar().collect(self.repo)
        self.assertEqual(len(self.calls), 3)

    def test_timeout_and_hidden_errors(self):
        self.response = None
        self.assertEqual(self.bar().collect(self.repo), "Git Δ0 · PR ?")
        self.assertEqual(self.bar(Settings(show_errors=False)).collect(self.repo), "Git Δ0")

    def test_git_status_timeout_shows_marker_and_keeps_pr(self):
        def run(argv, cwd, timeout=1):
            if argv[0] == "git" and "status" in argv:
                self.assertIn("--untracked-files=normal", argv)
                return None
            return self.run_command(argv, cwd, timeout)
        bar = StatusBar(self.state, Settings(), run=run, clock=lambda: self.now)
        self.assertEqual(bar.collect(self.repo), "Git … · PR #42 · 5 files · +128 −34")

    def test_invalid_remote_data_cannot_inject_terminal_text(self):
        self.response = subprocess.CompletedProcess([], 0, json.dumps(dict(PR, additions="\x1b[31m")).encode(), b"")
        self.assertEqual(self.bar().collect(self.repo), "Git Δ0 · PR ?")

    def test_closed_pr_is_hidden(self):
        self.response = subprocess.CompletedProcess([], 0, json.dumps(dict(PR, state="MERGED")).encode(), b"")
        self.assertEqual(self.bar().collect(self.repo), "Git Δ0")

    def test_missing_gh_keeps_local_changes(self):
        with patch("statusbar.shutil.which", return_value=None):
            self.assertEqual(self.bar().collect(self.repo), "Git Δ0 · PR gh?")
        self.assertEqual(self.calls, [])

    def test_cache_only_contains_numeric_stats_and_timestamp(self):
        self.bar().collect(self.repo)
        cache = next((self.state / "pr").glob("*.json"))
        text = cache.read_text()
        self.assertNotIn("github.com", text)
        self.assertNotIn(str(self.repo), text)
        self.assertEqual(cache.stat().st_mode & 0o777, 0o600)

    def test_corrupted_or_future_cache_is_refetched(self):
        self.bar().collect(self.repo)
        cache = next((self.state / "pr").glob("*.json"))
        cache.write_text("broken")
        self.bar().collect(self.repo)
        data = json.loads(cache.read_text())
        data["observed_at"] = self.now + 10
        cache.write_text(json.dumps(data))
        self.bar().collect(self.repo)
        self.assertEqual(len(self.calls), 3)

    def test_symlink_cache_directory_never_fetches(self):
        self.state.mkdir()
        (self.state / "pr").symlink_to(self.directory, target_is_directory=True)
        self.assertEqual(self.bar().collect(self.repo), "Git Δ0 · PR cache?")
        self.assertEqual(self.calls, [])

    def test_symlink_cache_file_never_fetches_or_overwrites(self):
        self.bar().collect(self.repo)
        cache = next((self.state / 'pr').glob('*.json'))
        target = self.directory / 'unrelated'
        target.write_text('untouched')
        cache.unlink()
        cache.symlink_to(target)
        self.assertEqual(self.bar().collect(self.repo), 'Git Δ0 · PR cache?')
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(target.read_text(), 'untouched')

    def test_conflicted_and_deleted_files_count(self):
        self.assertEqual(changed_files(b'UU conflict\0 D deleted\0?? new\0'), 3)

    def test_busy_cache_lock_prevents_duplicate_query(self):
        self.bar().collect(self.repo)
        lock = next((self.state / "pr").glob("*.lock"))
        with lock.open("w") as held:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertEqual(self.bar().collect(self.repo), "Git Δ0 · PR …")
        self.assertEqual(len(self.calls), 1)

    def test_linked_worktree_is_supported(self):
        worktree = self.directory / "worktree"
        self.git("worktree", "add", "-q", "-b", "topic", str(worktree))
        (worktree / "new").write_text("new")
        self.assertTrue(self.bar().collect(worktree).startswith("Git Δ1 · PR #42"))

    def test_damaged_git_record_rejected(self):
        with self.assertRaises(ValueError):
            changed_files(b"R  renamed\0")
        with self.assertRaises(ValueError):
            changed_files(b"bad\0")

    def test_settings_validation_and_defaults(self):
        path = self.directory / "options.toml"
        self.assertEqual(Settings.load(path), Settings())
        path.write_text("show_pr = false\npr_refresh_seconds = 60\n")
        self.assertFalse(Settings.load(path).show_pr)
        for invalid in ('show_pr = "false"', 'pr_refresh_seconds = 0',
                        'command_timeout_seconds = 4', 'unknown = true'):
            path.write_text(invalid)
            with self.assertRaises(ValueError):
                Settings.load(path)
