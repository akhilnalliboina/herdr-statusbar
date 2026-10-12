# Changelog

## 0.2.1 — 2026-10-12

- Linux RAM now uses `MemAvailable` (falling back to `MemFree` on old kernels), so filesystem cache no longer makes the metric sit at 85–95%.
- Git status uses `--untracked-files=normal` and shows `Git …` when the lookup times out, instead of hiding Git and PR in large repositories.
- The CLI version is read from `herdr-plugin.toml`; the packaging check for a second copy is gone.
- Rename the marketplace name to "Git + system status bar" (plugin id unchanged).
- Replace `docs/CI_RESULTS.md` (v0.1.0 local run notes) with a CI badge in the README.
- Default `datetime_format` is now ISO `%Y-%m-%d %H:%M`. Existing settings files that set `datetime_format` are unaffected; remove the key or set it to `%d.%m.%Y %H:%M` to choose a layout explicitly.
- Keep the whole bar alive when a system segment fails unexpectedly: truncated weather responses (`HTTPException`) and malformed `/proc/meminfo` values (`IndexError`) now show `Weather ?` / `CPU ?` instead of crashing `bar`.
- Show the last cached reading, or omit the segment, when another render holds the refresh lock, instead of a spurious `CPU ?` / `Battery ?` / `Weather ?`.
- Bound system and weather refreshes to a 3 s per-render budget so slow DNS or `top` cannot push the bar past the Herdr entry timeout.
- Skip unreadable Linux power-supply entries instead of failing the battery reading for all of them.

## 0.2.0 — 2026-10-12

- Expand the plugin from Git/PR only to the complete configurable status bar: CPU, RAM, battery, weather temperature, and local date/time.
- Enable CPU, RAM, battery, and German-format date/time by default. Weather requires user-configured coordinates and remains disabled until enabled.
- Cache system readings and weather separately; safely show independent metric errors.
- Document cache-inclusive RAM accounting and weather coordinate privacy.
- Preserve native top/bottom placement and existing user shortcuts.

## 0.1.0 — 2026-10-12

- Count local staged, unstaged, untracked, and conflicted Git files.
- Show open GitHub PR number, changed files, added lines, and deleted lines.
- Cache PR data by repository, branch, origin, and GitHub host; bound network calls and use per-key locks.
- Add explicit configure/unconfigure actions with private backups, preservation checks, and reload rollback.
- Provide optional open-PR and doctor actions without claiming default shortcuts.
- Support macOS/Linux, Python 3.11+, and Herdr 0.9.3+.
- Follow the user's native top/bottom tab bar placement; preserve it through setup and removal.
