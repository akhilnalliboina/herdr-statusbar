# Herdr Git + system status bar

[![CI](https://github.com/akhilnalliboina/herdr-statusbar/actions/workflows/ci.yml/badge.svg)](https://github.com/akhilnalliboina/herdr-statusbar/actions/workflows/ci.yml)

A configurable Herdr toolbar for local Git changes, GitHub PR statistics, CPU, RAM, battery, weather, and date/time. It uses one native Herdr status entry and follows Herdr's top/bottom tab-bar position.

```text
Git Δ3 · PR #42 · 5 files · +128 −34 · CPU 37% · RAM 64% · ϟ93% · 12°C · 2026-10-12 11:29
```

## Install

```sh
herdr plugin install akhilnalliboina/herdr-statusbar
herdr plugin action invoke akhilnalliboina.herdr-statusbar.configure
```

Configure backs up the Herdr config, adds one marked toolbar entry, and reloads Herdr. It preserves the rest of your settings and shortcuts. It does not remove older/custom status entries; remove duplicate Git/PR, CPU/RAM, battery, weather, or clock entries yourself if you replace them with this plugin.

Requirements: Herdr 0.9.3+, Python 3.11+, and Git on the Herdr server's PATH. GitHub CLI (`gh`) is optional; it provides PR data and the optional open-PR action. No Python packages are installed.

## Included segments

- **Git ΔN:** staged, unstaged, untracked, and conflicted files. Each file counts once; a rename counts once.
- **PR #N · F files · +A −D:** open PR for the active branch. These are remote, pushed PR statistics, not local edits. Local status updates every five seconds; PR data has a separate cache per repository/branch and refreshes every 120 seconds by default.
- **CPU N%:** latest CPU user+system utilization sample.
- **RAM N%:** used physical memory percentage. On macOS this uses Herdr's `top` PhysMem used amount; on Linux it uses `MemTotal - MemAvailable`, so reclaimable filesystem cache is not counted as used (kernels without `MemAvailable` fall back to `MemFree`). On macOS, `top` rounds the figure, so it moves in coarse steps.
- **ϟN%:** battery percentage. Hidden when no battery is present.
- **N°C:** current temperature from Open-Meteo for the configured latitude/longitude. Weather is off until you set coordinates and enable it. The city name is never displayed.
- **Date/time:** local system time, ISO `YYYY-MM-DD HH:MM` (24-hour) by default; change `datetime_format` for another layout.

System measurements update every 10 seconds; battery every 30 seconds; weather every 10 minutes. Each segment is independently configurable. A missing sensor or failed request does not prevent other segments from showing.

## Configure

Run `herdr plugin config-dir akhilnalliboina.herdr-statusbar`, then edit its `config.toml`. Setup enables Git, PR, CPU, RAM, battery, and date/time by default. Weather stays off until you configure a location:

```toml
show_weather = true
weather_latitude = 49.3988
weather_longitude = 8.6724
weather_refresh_seconds = 600
```

The example coordinates are Heidelberg, Germany. Replace them with your own. When weather is enabled, the plugin sends those coordinates to `api.open-meteo.com`; it does not send a city name. A short-lived temperature cache limits requests. Set `show_weather = false` to make no weather requests.

Other options:

```toml
show_git = true
show_pr = true
show_pr_files = true
show_errors = true
show_cpu = true
show_ram = true
show_battery = true
show_datetime = true
datetime_format = "%Y-%m-%d %H:%M"
pr_refresh_seconds = 120
failure_retry_seconds = 30
command_timeout_seconds = 3
```

Set any `show_*` option to `false` to hide that segment. `show_errors = false` hides metric error markers. PR lookup targets GitHub `origin`; fork-upstream PR discovery is not automatic. GitHub CLI owns authentication; this plugin does not read credential files or print tokens.

To move the tabs and status bar to the bottom, set `tab_bar_position = "bottom"` in the existing `[ui]` section of Herdr's `config.toml`, then run `herdr server reload-config`. Use `"top"` to put them at the top. The position applies to the full native tab row, not only this plugin.

## Optional PR shortcut

No shortcut is installed automatically. Choose a free key. The action is also available as:

```sh
herdr plugin action invoke akhilnalliboina.herdr-statusbar.open-pr
```

It opens the active branch's PR with `gh pr view --web`; it does not send keystrokes to a pane. Herdr strips terminal links, so the status text is not clickable.

## Diagnose and remove

```sh
herdr plugin action invoke akhilnalliboina.herdr-statusbar.doctor
herdr plugin log list --plugin akhilnalliboina.herdr-statusbar
```

Remove the managed entry before uninstalling:

```sh
herdr plugin action invoke akhilnalliboina.herdr-statusbar.unconfigure
herdr plugin uninstall akhilnalliboina.herdr-statusbar
```

## Development

```sh
python3 -B -m unittest discover -s tests -v
sh -n scripts/run.sh
python3 -B scripts/smoke_herdr.py --position bottom
python3 scripts/package.py
```

CI runs Python 3.11 and 3.14 on macOS and Linux. GitHub responses in unit tests are fixtures; actual PR lookup needs an authenticated `gh` on the Herdr server. This is an unofficial community plugin and is not affiliated with Herdr or GitHub.

MIT license. See [CHANGELOG.md](CHANGELOG.md).
