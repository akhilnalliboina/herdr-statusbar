# Changelog

## 0.1.0 — 2026-10-12

- Count local staged, unstaged, untracked, and conflicted Git files.
- Show open GitHub PR number, changed files, added lines, and deleted lines.
- Cache PR data by repository, branch, origin, and GitHub host; bound network calls and use per-key locks.
- Add explicit configure/unconfigure actions with private backups, preservation checks, and reload rollback.
- Provide optional open-PR and doctor actions without claiming default shortcuts.
- Support macOS/Linux, Python 3.11+, and Herdr 0.9.3+.
- Follow the user's native top/bottom tab bar placement; preserve it through setup and removal.
