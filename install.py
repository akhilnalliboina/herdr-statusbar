"""Conservative, reversible edits to conventional Herdr TOML configuration."""
import copy
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import tomllib

ID = "akhilnalliboina.herdr-statusbar"
MARKER = "# herdr-statusbar:entry"
DEFAULTS = """# Full status-bar options. No credentials belong in this file.
show_git = true
show_pr = true
show_pr_files = true
show_errors = true
show_cpu = true
show_ram = true
show_battery = true
show_datetime = true
datetime_format = "%Y-%m-%d %H:%M"
# Weather sends configured coordinates to Open-Meteo. Enable and set a location to use it.
show_weather = false
# Example: Heidelberg, Germany. Replace with your own coordinates before enabling.
# weather_latitude = 49.3988
# weather_longitude = 8.6724
weather_refresh_seconds = 600
pr_refresh_seconds = 120
failure_retry_seconds = 30
command_timeout_seconds = 3
"""


def managed_entry(root, settings, state):
    argv = [sys.executable, str(root / "cli.py"), "bar", "--settings", str(settings),
            "--state", str(state)]
    command = shlex.join(argv)
    return ('  { type = "command", command = ' + json.dumps(command, ensure_ascii=False)
            + ', interval_seconds = 5, timeout_seconds = 10 }, ' + MARKER + '\n')


def array_end(text, start):
    """Find a TOML array end without treating quoted brackets/comments as syntax."""
    depth = 0
    index = start
    while index < len(text):
        char = text[index]
        if char == "#":
            end = text.find("\n", index)
            index = len(text) if end < 0 else end + 1
            continue
        if char in "\"'":
            quote = char * (3 if text.startswith(char * 3, index) else 1)
            index += len(quote)
            while index < len(text):
                if char == '"' and text[index] == "\\":
                    index += 2
                elif text.startswith(quote, index):
                    index += len(quote)
                    break
                else:
                    index += 1
            continue
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    raise ValueError("Cannot locate tab_bar_right array")


def patch_config(text, entry=None):
    original = tomllib.loads(text)
    lines = text.splitlines(keepends=True)
    owned = [line for line in lines if MARKER in line]
    if len(owned) > 1:
        raise ValueError("Multiple managed entries; inspect the config manually")
    for line in owned:
        # Never use a marker buried in an unrelated string as permission to delete.
        if not re.fullmatch(r'\s*\{ type = "command", command = .+, interval_seconds = 5, timeout_seconds = 10 \}, # herdr-statusbar:entry\s*', line):
            raise ValueError("Managed entry was edited; inspect the config manually")
    cleaned = "".join(line for line in lines if line not in owned)
    parsed = tomllib.loads(cleaned)
    # Confirm removing marked lines changed exactly one command, nothing else.
    expected = copy.deepcopy(original)
    old_entries = expected.get("ui", {}).get("tab_bar_right", [])
    if owned:
        owned_command = tomllib.loads("values = [\n" + owned[0] + "]")["values"][0]
        try:
            old_entries.remove(owned_command)
        except ValueError as error:
            raise ValueError("Marker is outside the toolbar array") from error
    if expected != parsed:
        raise ValueError("Managed entry is not an isolated toolbar entry")
    if entry is None:
        return cleaned

    ui = parsed.get("ui", {})
    if not isinstance(ui, dict) or not isinstance(ui.get("tab_bar_right", []), list):
        raise ValueError("Expected [ui] and an array tab_bar_right")
    header = re.search(r'(?m)^\[ui\][ \t]*(?:#[^\n]*)?$', cleaned)
    if not header:
        if "tab_bar_right" in ui:
            raise ValueError("Use a conventional [ui] table before configuring")
        result = cleaned.rstrip() + "\n\n[ui]\ntab_bar_right = [\n" + entry + "]\n"
    else:
        following = re.search(r'(?m)^\s*\[', cleaned[header.end():])
        stop = header.end() + following.start() if following else len(cleaned)
        section = cleaned[header.end():stop]
        assignment = re.search(r'(?m)^[ \t]*tab_bar_right[ \t]*=[ \t]*\[', section)
        if assignment:
            start = header.end() + assignment.end() - 1
            end = array_end(cleaned, start)
            existing = cleaned[start + 1:end]
            if existing.startswith("\n"):
                existing = existing[1:]
            result = cleaned[:start + 1] + "\n" + entry + existing + cleaned[end:]
        elif "tab_bar_right" in ui:
            raise ValueError("Use an unquoted tab_bar_right = [...] assignment")
        else:
            result = (cleaned[:header.end()] + "\ntab_bar_right = [\n" + entry + "]"
                      + cleaned[header.end():])
    updated = tomllib.loads(result)
    expected = copy.deepcopy(parsed)
    expected.setdefault("ui", {}).setdefault("tab_bar_right", []).insert(
        0, tomllib.loads("values = [\n" + entry + "]")["values"][0])
    if expected != updated:
        raise ValueError("Unsupported TOML layout; no changes made")
    # Do not grow whitespace on repeated configure runs.
    if original == updated and owned and owned[0] == entry:
        return text
    return result


def regular_file(path):
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError(f"Refusing symlink: {path}")
    if path.exists() and not path.is_file():
        raise ValueError(f"Expected a regular file: {path}")


def atomic_text(path, text, mode=0o600):
    regular_file(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix=".statusbar-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as output:
            output.write(text)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def configure(config, settings, state, root, remove=False, reload=True):
    """Validate, back up, patch, reload; restore on a rejected reload."""
    regular_file(config)
    regular_file(settings)
    original = config.read_text() if config.exists() else ""
    mode = config.stat().st_mode & 0o777 if config.exists() else 0o600
    entry = None if remove else managed_entry(root, settings, state)
    replacement = patch_config(original, entry)
    if not remove and not settings.exists():
        atomic_text(settings, DEFAULTS)
    if original == replacement:
        return None
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    if state.is_symlink():
        raise ValueError("Refusing symlink state directory")
    backups = state / "backups"
    backups.mkdir(exist_ok=True, mode=0o700)
    if backups.is_symlink():
        raise ValueError("Refusing symlink backup directory")
    fd, backup_name = tempfile.mkstemp(prefix="config-", suffix=".toml", dir=backups)
    backup = Path(backup_name)
    with os.fdopen(fd, "w") as output:
        output.write(original)
    existed = config.exists()
    if not existed:
        atomic_text(Path(str(backup) + ".absent"), "")
    # Avoid overwriting an edit made after the snapshot (also checked on rollback).
    if (config.read_text() if config.exists() else "") != original:
        raise ValueError("Config changed during setup; retry after closing other editors")
    atomic_text(config, replacement, mode)
    if reload:
        try:
            result = subprocess.run([os.environ.get("HERDR_BIN_PATH", "herdr"), "server", "reload-config"],
                                    check=True, capture_output=True, timeout=10)
            if json.loads(result.stdout).get("result", {}).get("status") != "applied":
                raise ValueError("Herdr did not confirm config application")
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            if config.read_text() == replacement:
                if existed:
                    atomic_text(config, original, mode)
                else:
                    config.unlink()
                # Best effort: the server may have applied a reload before a
                # timeout. Reload the restored config, too.
                try:
                    subprocess.run([os.environ.get("HERDR_BIN_PATH", "herdr"), "server", "reload-config"],
                                   capture_output=True, timeout=10)
                except (OSError, subprocess.SubprocessError):
                    pass
            raise ValueError(f"Herdr reload failed; inspect config and backup {backup}") from error
    return backup
