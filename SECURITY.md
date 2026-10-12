# Security and privacy

This plugin runs with your user's permissions. It is not sandboxed.

- Git collection runs Git's read-only status/repository commands, with optional index locks disabled. Git can still use your configured helpers and filesystem-monitor settings.
- PR collection invokes GitHub CLI, pinned to the repository's origin. GitHub CLI owns authentication. The plugin never reads credential files or prints tokens.
- Install and runtime commands inherit the environment. Only the fields needed for rendering are cached. Raw stderr, PR bodies, and complete provider responses are not retained.
- The installer writes one marked toolbar entry, plugin settings, and private backups. It takes no shortcut by default and never installs a hook into Claude Code or another agent.
- Symlink config targets and direct cache/config/state symlinks are refused. The user-level configuration/state directory and its ancestors must be trusted; this is not a hardened multi-user storage service.
- Cache and setup use atomic file replacement. Setup checks for concurrent config changes, but it is not a transaction across the filesystem and Herdr. Close other editors during setup. A timeout can mean Herdr applied a reload; setup attempts a restore and second reload and keeps a backup for manual recovery.
- Only validated numeric GitHub fields enter the toolbar. Remote-controlled labels, repository names, and terminal escape sequences are not rendered.
- No telemetry, dependency download, background daemon, browser launch, or publishing runs automatically. Browser launch happens only through the explicit open-pr action.

Do not attach credential files, environment dumps, private config backups, or PR bodies to issue reports. Share the plugin/Herdr/Python versions, error marker, and a minimal synthetic reproduction instead. Report security issues privately to the repository owner through GitHub's private vulnerability-reporting feature if it is enabled. If it is unavailable, request a private contact channel without publishing sensitive details.
