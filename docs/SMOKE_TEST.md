# Manual smoke tests

These checks complement the tests. Never use the owner's live configuration as the test fixture without permission.

## Checklist

- [ ] Record Herdr version, Python version, OS, and source revision.
- [ ] Link the manifest in an isolated Herdr profile; confirm all four actions register.
- [ ] Configure a session with an existing toolbar, comments, and shortcuts; confirm they remain.
- [ ] Reconfigure twice; confirm one entry and no extra backup/write on the second call.
- [ ] Focus a dirty Git working tree; visually confirm local count, including staged and untracked files.
- [ ] Focus a branch with an open PR; compare file/line counts with `gh pr view --json number,changedFiles,additions,deletions`.
- [ ] Switch repositories/branches/worktrees; confirm no previous-branch PR after the next toolbar tick.
- [ ] Disconnect network or deny gh authentication; confirm `PR ?` rather than a stale successful reading.
- [ ] Test the optional open-PR action in a pane and confirm the intended browser page.
- [ ] Test a narrow terminal; confirm no broken layout when Herdr hides the status area.
- [ ] Unconfigure after making an unrelated user edit; confirm the edit remains.
- [ ] Reinstall/update the plugin and rerun configure; confirm paths/entry update correctly.
- [ ] Repeat platform-specific checks on macOS and Linux.

## Evidence

Record exact commands and results here before tagging. Screen capture may require OS permission; when it is unavailable, a human must confirm the visible bar. Do not mark visual checks as passed based only on script output. Never include tokens, repository contents, or private configuration backups in evidence.

### Local pre-release checks — 12.10.2026

Environment: macOS, Herdr 0.9.3, Python 3.14.7. Source is an uncommitted release candidate, not a published version.

- `python3 -B -m unittest discover -s tests -q`: **48 tests passed**.
- `sh -n scripts/run.sh`: passed.
- `python3 -B scripts/smoke_herdr.py`: all four actions registered in an isolated profile; configure + actual reload passed; reconfigure was a no-op; unconfigure + actual reload passed and preserved the existing entry. The temporary server stopped afterward.
- Pure patch/unpatch against a read-only copy of the owner's current toolbar config returned the original text exactly. No live config writes were made.
- CLI `bar --cwd <existing worktree> --settings <temporary file> --state <temporary directory>` returned both local Git count and remote PR statistics. A repeated read reused the cached snapshot. Private repository details are intentionally omitted here.
- Python 3.10 invocation failed with the intended Python 3.11+ requirement message.

### Follow-up pane-switch verification — 12.10.2026

- Added a repository-switch regression test: **49 tests passed**. Coverage includes switching branches, repositories, and worktrees, then entering a non-repository directory.
- Installed the local candidate into the owner's toolbar to fix its old separate five-second Git and 120-second PR commands. Backed up the original config and preserved other entries/shortcuts.
- Temporarily traced the actual scheduled toolbar command (active directory plus numeric output only). Switching between two existing repository panes produced the correct distinct PR summaries after **5.2 seconds** and **4.6 seconds**. Returning to a non-repository pane cleared the old Git/PR text.
- Removed tracing, restored the original focused pane, and reloaded the final config. This confirms the server's scheduled command output, not a screenshot of the rendered bar.

### Local Linux/macOS matrix — 12.10.2026

All four local combinations passed: macOS and Ubuntu 24.04 x86_64, each with Python 3.11.16 and 3.14.7. Each passed 49 unit tests, shell validation, source packaging, and the real isolated Herdr 0.9.3 smoke test. See [matrix evidence and reproduction commands](CI_RESULTS.md). Linux ran in emulated Docker containers with networking disabled during execution. This was not a GitHub Actions run.

### Operator confirmation and placement — 12.10.2026

The owner confirmed the visible toolbar, pane/branch switching, local changes, and existing PR shortcut work. Supplied screenshots show the compact status layout; private live PR details are not included in the source package.

Top/bottom placement uses Herdr's native `ui.tab_bar_position` setting. A regression test checks that configure, reconfigure, and unconfigure preserve either choice. Real isolated Herdr sessions accepted bottom placement on macOS and Linux. The bottom smoke test is available with `python3 -B scripts/smoke_herdr.py --position bottom`.

At this checkpoint, GitHub-hosted CI and a clean public-repository install remained to be checked during publication. Linux visible rendering and browser opening through the optional plugin action were not tested; the operator checked the existing local browser shortcut.
