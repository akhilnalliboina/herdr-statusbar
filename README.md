# Herdr Git and PR status bar

Local Git changes and remote GitHub pull-request statistics in Herdr's native tab bar.

```text
Git Δ3 · PR #42 · 5 files · +128 −34
```

- **Git Δ3:** three changed files in the active pane's working tree. Includes staged, unstaged, untracked, and conflicted files. A file changed in both index and working tree counts once; a rename counts once.
- **PR #42:** the open PR associated with the active branch.
- **5 files / +128 −34:** GitHub's remote PR diff statistics. These do not include unpushed or uncommitted work.

One toolbar entry; one small Python implementation; no pip dependencies, daemon, or background process. This is an unofficial community plugin, not affiliated with Herdr or GitHub.

## Requirements

- Herdr **0.9.3+** on **macOS or Linux**.
- Python **3.11+** and Git on the Herdr **server's** PATH.
- Optional: GitHub CLI (`gh`), signed in with access to the repository, for PR statistics and browser opening.
- The repository must have a GitHub `origin` remote for PR statistics. HTTPS, SSH, and SCP-style Git URLs are supported, including GitHub Enterprise hosts. Detached HEAD and repositories without an origin show local changes only. Non-repository panes show nothing. PR lookup is explicitly pinned to origin; PRs against a fork's separate upstream repository are not automatically discovered in v0.1.

On macOS:

```sh
brew install python git gh
gh auth login
```

On Linux, install Python 3.11+, Git, and gh through your distribution's package manager. The launcher accepts `HERDR_STATUSBAR_PYTHON=/path/to/python3` if needed. No hard-coded Homebrew paths are shipped.

## Install

```sh
herdr plugin install akhilnalliboina/herdr-statusbar
herdr plugin action invoke akhilnalliboina.herdr-statusbar.configure
```

For a local checkout:

```sh
herdr plugin link /absolute/path/to/herdr-statusbar
herdr plugin action invoke akhilnalliboina.herdr-statusbar.configure
```

Installing or linking only registers actions. **Configure is explicit:** it backs up `config.toml`, adds one marked entry at the beginning of `ui.tab_bar_right`, and reloads the server. It preserves existing entries, comments, tab position, theme, and shortcuts. It does not remove older/custom Git or PR entries; remove those manually to avoid duplicates.

The generated entry uses the Python interpreter detected at setup and absolute paths for this installation. Rerun configure after moving the checkout or interpreter. Run configure on each server/session config you use. Stop other config editors during setup.

Herdr's manifest cannot declare native toolbar entries. Setup supports conventional `[ui]` tables with `tab_bar_right = [...]`; unusual quoted/dotted/inline layouts are refused rather than rewritten. An invalid config or edited ownership marker is also refused. On a rejected reload, setup attempts to restore the prior file without overwriting concurrent edits. Backups live in the plugin state directory with private permissions; they may contain private user settings.

For offline setup/testing:

```sh
sh scripts/run.sh configure --herdr-config /path/to/config.toml --no-reload
```

## Top or bottom placement

The plugin follows Herdr's native tab bar position. It does not override your choice.

To place it at the **bottom**, set this key in the existing `[ui]` section of your Herdr `config.toml`:

```toml
[ui]
tab_bar_position = "bottom"
```

Use `"top"` to place it at the top instead. Do not add a second `[ui]` table if one already exists. Apply the change with:

```sh
herdr server reload-config
```

This moves **both the tab row and its status entries**. Herdr 0.9.3 does not expose an independent position for just this plugin's status text. Configure, reconfigure, and unconfigure preserve either position.

## Optional open-PR shortcut

No shortcut is installed automatically. Pick an unused key; do not take `prefix+p`, which Herdr normally uses for the previous tab.

Add this block to your Herdr config if `ctrl+alt+p` is free in your terminal:

```toml
[[keys.command]]
key = "ctrl+alt+p"
type = "plugin_action"
command = "akhilnalliboina.herdr-statusbar.open-pr"
description = "Open current branch PR in browser"
```

Then run `herdr server reload-config`. You can also invoke the action directly:

```sh
herdr plugin action invoke akhilnalliboina.herdr-statusbar.open-pr
```

The action runs `gh pr view --repo <origin repository> --web` in the selected pane's directory. It never sends keystrokes to a terminal. On remote servers, browser opening follows gh's behavior on that server; this plugin does not bridge URLs to the local desktop.

**The toolbar text is not clickable.** Herdr strips terminal control sequences, including OSC 8 links.

## Configuration

Find the plugin configuration directory:

```sh
herdr plugin config-dir akhilnalliboina.herdr-statusbar
```

Edit its `config.toml`:

```toml
show_git = true
show_pr = true
show_pr_files = true
show_errors = true
pr_refresh_seconds = 120
failure_retry_seconds = 30
command_timeout_seconds = 3
```

Changes take effect on the next toolbar tick; no reload needed. Numeric settings must be whole numbers from 1 to 3600; `command_timeout_seconds` is limited to 1–3 seconds. Invalid or unreadable settings show `Status config?` and make no GitHub request. Toolbar polling stays at five seconds; edit the generated entry manually only after removing its ownership marker, or use a manual command entry.

The GitHub CLI handles credentials and repository resolution. The plugin does not read credential files, ask for authentication, perform token refresh itself, or install dependencies. Set `show_pr = false` for local-only operation with no GitHub calls.

## Refresh and pane switching

Local status is collected every five seconds. PR snapshots refresh at most once per configured interval **per repository, branch, origin, and GH_HOST**. No-PR results are cached, too. Switching to another repository, branch, remote, or worktree selects another cache; the previous branch's PR is never reused. Herdr may retain an entry's previous output until the next scheduled command completes (usually within five seconds, plus a bounded initial lookup).

Network failures replace the expired snapshot with an error marker; old statistics are not presented as current. Failures use the shorter retry interval. Concurrent windows use a non-blocking per-key file lock, so only one request runs; another window temporarily shows `PR …`. Locked requests are still bounded by the subprocess timeout.

Cache files have mode 0600. They contain only timestamp, result status, and validated numeric PR fields. Repository/branch/remote identity is hashed in filenames; raw paths, URLs, tokens, PR bodies, and raw stderr are not cached. Plugin state persists after unlink/uninstall; delete its cache directory yourself when no sessions are using it. No automatic cache eviction is included in v0.1.

## Diagnostics

```sh
herdr plugin action invoke akhilnalliboina.herdr-statusbar.doctor
herdr plugin log list --plugin akhilnalliboina.herdr-statusbar
```

| Display | Meaning |
| --- | --- |
| `Git Δ0` | The active working tree is clean. |
| No entry | Active pane is not a repository, Git failed, or both segments are disabled. |
| Git only | No open PR, detached HEAD, or no `origin` remote. |
| `PR gh?` | GitHub CLI is unavailable on the server's PATH. |
| `PR remote?` | Origin is a local path or an unsupported remote URL. |
| `PR ?` | Authentication, network, timeout, or invalid GitHub data. Run `gh pr view` in that pane to diagnose. |
| `PR cache?` | Plugin state cannot be safely written. Fix ownership/permissions; do not make it world-writable. |
| `PR …` | Another window is refreshing this branch's snapshot. |
| `Status config?` | Plugin configuration is invalid/unreadable. |

Herdr may hide the entire status area when it cannot fit next to the tabs. Shorten other entries or set `show_pr_files = false`.

## Remove

Remove the managed entry **before** unregistering the plugin:

```sh
herdr plugin action invoke akhilnalliboina.herdr-statusbar.unconfigure
herdr plugin uninstall akhilnalliboina.herdr-statusbar
```

For a local link, use `herdr plugin unlink akhilnalliboina.herdr-statusbar` instead. Remove any optional keybinding you added yourself. Unconfigure removes only its marked toolbar line and preserves later user edits, plugin settings, cache, and backups. It does not restore an old whole-config backup over newer settings. An empty toolbar array/table created by setup may remain.

## Development

```sh
python3 -B -m unittest discover -s tests -v
sh -n scripts/run.sh
python3 scripts/smoke_herdr.py  # optional: real server in a disposable /tmp profile
python3 scripts/package.py
```

Tests exercise real Git repositories, worktrees, unusual filenames, renames, cache isolation/expiry, errors, locking, config preservation, permissions, and rollback. GitHub responses are controlled in tests; no credentials or network access are needed. CI runs the suite on macOS and Linux with Python 3.11 and 3.14.

See [release checklist](docs/RELEASING.md) and [manual verification](docs/SMOKE_TEST.md). Windows and system/weather/AI-usage segments are intentionally outside v0.1. Existing custom entries for those features can remain beside this plugin.

## License

MIT — [LICENSE](LICENSE).
