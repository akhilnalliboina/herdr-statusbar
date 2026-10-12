#!/usr/bin/env python3
"""Command entrypoint. Standard library only; Python 3.11 or newer."""
import sys

if sys.version_info < (3, 11):
    sys.exit("herdr-statusbar requires Python 3.11 or newer")

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

from install import ID, configure
from statusbar import Settings, StatusBar, execute, github_repository

ROOT = Path(__file__).resolve().parent


def active_cwd(explicit=None):
    if explicit:
        return explicit
    if os.environ.get("HERDR_ACTIVE_PANE_CWD"):
        return os.environ["HERDR_ACTIVE_PANE_CWD"]
    # Plugin actions have pane IDs, not necessarily the toolbar's ACTIVE vars.
    pane = os.environ.get("HERDR_PANE_ID")
    if pane:
        result = execute([os.environ.get("HERDR_BIN_PATH", "herdr"), "pane", "get", pane], ROOT)
        if result and result.returncode == 0:
            try:
                info = json.loads(result.stdout)["result"]["pane"]
                return info.get("foreground_cwd") or info.get("cwd")
            except (ValueError, KeyError, TypeError):
                pass
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version="herdr-statusbar 0.1.0")
    parser.add_argument("command", choices=["bar", "doctor", "open-pr", "configure", "unconfigure"])
    base = Path(os.environ.get("HERDR_CONFIG_PATH", Path.home() / ".config/herdr/config.toml"))
    config_dir = Path(os.environ.get("HERDR_PLUGIN_CONFIG_DIR", base.parent / "plugins/config" / ID))
    state_dir = Path(os.environ.get("HERDR_PLUGIN_STATE_DIR", base.parent / "plugins/state" / ID))
    parser.add_argument("--settings", type=Path, default=config_dir / "config.toml")
    parser.add_argument("--state", type=Path, default=state_dir)
    parser.add_argument("--herdr-config", type=Path, default=base)
    parser.add_argument("--cwd", help="Explicit repository directory (otherwise use active Herdr pane)")
    parser.add_argument("--no-reload", action="store_true", help="For offline setup and isolated tests")
    args = parser.parse_args()
    try:
        if args.command in ("configure", "unconfigure"):
            # Invalid user settings must fail before any config is modified.
            Settings.load(args.settings)
            backup = configure(args.herdr_config, args.settings, args.state, ROOT,
                               remove=args.command == "unconfigure", reload=not args.no_reload)
            print("Already configured; no changes" if backup is None else f"Config updated. Backup: {backup}")
            return 0
        settings = Settings.load(args.settings)
        cwd = active_cwd(args.cwd)
        if args.command == "bar":
            text = StatusBar(args.state, settings).collect(cwd)
            if text:
                print(text)
            return 0
        if args.command == "doctor":
            print("Python:", sys.version.split()[0])
            print("Git:", shutil.which("git") or "missing")
            print("GitHub CLI:", shutil.which("gh") or "missing (PR disabled)")
            print("Active repository directory:", cwd or "not supplied")
            print("Settings:", args.settings)
            print("State:", args.state)
            print("Toolbar:", StatusBar(args.state, settings).collect(cwd) or "hidden (no repository/data)")
            print("PR ? means lookup failed (authentication/network/timeout/invalid data).")
            print("PR gh? means gh is missing. PR cache? means state is not writable/safe.")
            return 0
        if not cwd or not shutil.which("gh"):
            raise ValueError("Open PR requires an active repository and GitHub CLI")
        # Pin the same origin repository used by the toolbar, even when gh
        # has a different repository selected as its default.
        remote = execute(["git", "-C", cwd, "remote", "get-url", "origin"], cwd)
        repository = (github_repository(remote.stdout.decode(errors="replace").strip())
                      if remote and remote.returncode == 0 else None)
        if not repository:
            raise ValueError("Open PR requires a supported GitHub origin URL")
        result = subprocess.run(["gh", "pr", "view", "--repo", repository, "--web"], cwd=cwd,
                                capture_output=True, timeout=15,
                                env=dict(os.environ, GH_PROMPT_DISABLED="1"))
        if result.returncode:
            raise ValueError("Could not open PR; check gh authentication and the current branch")
        print("Opened current branch PR")
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        if args.command == "bar":
            print("Status config?")
            return 0
        # Do not print raw command stderr, environment, or provider payloads.
        print(f"herdr-statusbar: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
