#!/usr/bin/env python3
"""Exercise a real Herdr server in a temporary profile, never the live profile."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--position', choices=('top', 'bottom'), default='top')
position = parser.parse_args().position

root = Path(__file__).resolve().parents[1]
herdr = shutil.which("herdr")
if not herdr:
    raise SystemExit("Install Herdr 0.9.3+ before running this optional smoke test")
# Unix socket paths are short. Avoid macOS's long default temporary directory.
with tempfile.TemporaryDirectory(prefix="hs-", dir="/tmp") as directory:
    home = Path(directory)
    config = home / ".config/herdr/config.toml"
    config.parent.mkdir(parents=True)
    config.write_text('onboarding = false\n[ui]\ntab_bar_position = ' + json.dumps(position) + '\ntab_bar_right = [{type="text",text="existing"}]\n')
    env = {key: value for key, value in os.environ.items() if not key.startswith("HERDR_")}
    env.update(HOME=str(home), XDG_CONFIG_HOME=str(home / ".config"),
               XDG_DATA_HOME=str(home / ".local/share"), XDG_STATE_HOME=str(home / ".local/state"),
               HERDR_CONFIG_PATH=str(config),
               HERDR_BIN_PATH=herdr, SHELL="/bin/sh")

    def command(*args):
        result = subprocess.run([herdr, *args], env=env, cwd=home,
                                capture_output=True, text=True, timeout=10)
        if result.returncode:
            raise RuntimeError(result.stderr)
        return json.loads(result.stdout)

    linked = command("plugin", "link", str(root))
    assert len(linked["result"]["plugin"]["actions"]) == 4
    with (home / "server.log").open("w") as log:
        process = subprocess.Popen([herdr, "server"], env=env, cwd=home, stdout=log, stderr=log)
        try:
            socket = config.parent / "herdr.sock"
            for _ in range(100):
                if socket.exists():
                    break
                if process.poll() is not None:
                    raise RuntimeError("Test server exited before becoming ready")
                time.sleep(0.05)
            assert socket.exists(), "Test server never became ready"
            repo = home / "repo"
            repo.mkdir()
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            (repo / "untracked").write_text("fixture")
            command("workspace", "create", "--cwd", str(repo), "--focus")
            actions = command("plugin", "action", "list", "--plugin", "akhilnalliboina.herdr-statusbar")
            for action in ("configure", "unconfigure", "open-pr", "doctor"):
                assert action in json.dumps(actions), actions
            print("Isolated server: all four actions registered")
            args = [sys.executable, "-B", str(root / "cli.py"), "configure", "--herdr-config", str(config),
                    "--settings", str(home / "options.toml"), "--state", str(home / "state")]
            result = subprocess.run(args, env=env, cwd=home, capture_output=True, text=True, timeout=15)
            assert result.returncode == 0, result.stderr
            assert "herdr-statusbar:entry" in config.read_text()
            assert "existing" in config.read_text()
            print("Configure + real server reload: passed")
            result = subprocess.run(args, env=env, cwd=home, capture_output=True, text=True, timeout=15)
            assert result.returncode == 0 and "Already configured" in result.stdout
            print("Repeated configure: exact no-op")
            args[3] = "unconfigure"
            result = subprocess.run(args, env=env, cwd=home, capture_output=True, text=True, timeout=15)
            assert result.returncode == 0, result.stderr
            assert "herdr-statusbar:entry" not in config.read_text()
            assert "existing" in config.read_text()
            print("Unconfigure + real server reload: passed; existing entry preserved")
            assert tomllib.loads(config.read_text())['ui']['tab_bar_position'] == position
            print(f"Native tab bar placement preserved: {position}")
        finally:
            # Environment and socket identify only the test server created above.
            subprocess.run([herdr, "server", "stop"], env=env, cwd=home, capture_output=True, timeout=10)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=5)
