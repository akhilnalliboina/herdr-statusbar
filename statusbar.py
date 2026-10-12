"""Git and PR status behind one read-only collection interface."""
from dataclasses import dataclass
import fcntl
import hashlib
import json
import math
import os
import re
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import tomllib
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Settings:
    show_git: bool = True
    show_pr: bool = True
    show_pr_files: bool = True
    show_errors: bool = True
    show_cpu: bool = True
    show_ram: bool = True
    show_battery: bool = True
    show_weather: bool = False
    show_datetime: bool = True
    datetime_format: str = "%Y-%m-%d %H:%M"
    weather_latitude: float = 0.0
    weather_longitude: float = 0.0
    weather_refresh_seconds: int = 600
    pr_refresh_seconds: int = 120
    failure_retry_seconds: int = 30
    command_timeout_seconds: int = 3

    @classmethod
    def load(cls, path):
        if not path.exists():
            return cls()
        data = tomllib.loads(path.read_text())
        if set(data) - set(cls.__dataclass_fields__):
            raise ValueError("Unknown status-bar setting")
        for key, value in data.items():
            if key.startswith("show_"):
                if type(value) is not bool:
                    raise ValueError(f"{key} must be a boolean")
            elif key == "datetime_format":
                if (not isinstance(value, str) or not value or len(value) > 80
                        or any(ord(char) < 32 or ord(char) == 127 for char in value)
                        or "%n" in value or "%t" in value):
                    raise ValueError("Invalid datetime format")
            elif key in ("weather_latitude", "weather_longitude"):
                maximum = 90 if key == "weather_latitude" else 180
                if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > maximum:
                    raise ValueError("Invalid weather coordinates")
            elif type(value) is not int or not 1 <= value <= 3600:
                raise ValueError(f"{key} must be an integer from 1 to 3600")
        if data.get("command_timeout_seconds", 3) > 3:
            raise ValueError("command_timeout_seconds must be at most 3")
        if data.get("show_weather") and not {"weather_latitude", "weather_longitude"} <= data.keys():
            raise ValueError("Weather requires latitude and longitude")
        return cls(**data)


def execute(argv, cwd, timeout=1):
    """Return bounded command output; never expose raw stderr in the toolbar."""
    try:
        return subprocess.run(argv, cwd=cwd, capture_output=True, timeout=timeout,
                              env=dict(os.environ, LC_ALL="C", GH_PROMPT_DISABLED="1"))
    except (OSError, subprocess.TimeoutExpired):
        return None


def changed_files(raw):
    records = raw.split(b"\0")
    count = index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if not record:
            continue
        if len(record) < 4 or record[2:3] != b" ":
            raise ValueError("Invalid Git status record")
        count += 1
        if b"R" in record[:2] or b"C" in record[:2]:
            if index >= len(records) or not records[index]:
                raise ValueError("Missing rename path")
            index += 1
    return count


def github_repository(remote):
    """Convert common Git remote URLs into gh's explicit host/owner/repo form."""
    if "://" in remote:
        parsed = urlsplit(remote)
        if parsed.scheme not in ("https", "http", "ssh") or not parsed.hostname:
            return None
        host = parsed.hostname
        if parsed.scheme in ("http", "https") and parsed.port:
            host += f":{parsed.port}"
        path = parsed.path.lstrip("/")
    else:
        match = re.fullmatch(r"(?:[^@/:]+@)?([^/:]+):(.+)", remote)
        if not match:
            return None
        host, path = match.groups()
    path = path.rstrip("/").removesuffix(".git")
    parts = path.split("/")
    if (len(parts) != 2 or not re.fullmatch(r"[A-Za-z0-9.-]+(?::[0-9]+)?", host)
            or any(not re.fullmatch(r"[A-Za-z0-9_.-]+", part) for part in parts)):
        return None
    return f"{host}/{'/'.join(parts)}"


def valid_pr(data):
    if not isinstance(data, dict) or data.get("state") != "OPEN":
        return None
    names = ("number", "changedFiles", "additions", "deletions")
    values = [data.get(name) for name in names]
    if any(type(value) is not int or value < 0 for value in values) or values[0] == 0:
        return None
    return dict(zip(names, values), state="OPEN")


def atomic_json(path, data):
    """Keep snapshots private and prevent partial writes. Never overwrite links."""
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError("Refusing a symlink cache")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix=".statusbar-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as output:
            json.dump(data, output)
            output.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class StatusBar:
    def __init__(self, state_dir, settings=Settings(), run=execute, clock=time.time):
        self.state_dir = Path(state_dir)
        self.settings = settings
        self.run = run
        self.clock = clock

    def _git(self, cwd, *args):
        result = self.run(["git", "--no-optional-locks", "-C", str(cwd), *args], cwd)
        return result.stdout if result and result.returncode == 0 else None

    def _pr(self, cwd, root, branch, remote):
        # Branch and remote changes select a different cache immediately. Do not
        # put paths, remote URLs, credentials, or raw provider output in the cache.
        identity = json.dumps([root, branch, remote, os.environ.get("GH_HOST", "")])
        key = hashlib.sha256(identity.encode()).hexdigest()
        path = self.state_dir / "pr" / f"{key}.json"
        lock_path = path.with_suffix(".lock")
        if (path.is_symlink() or lock_path.is_symlink()
                or (path.exists() and not path.is_file())):
            return {"status": "cache-error"}
        # A per-repository/branch lock prevents simultaneous windows from
        # making duplicate network requests. No background processes needed.
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "w") as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    return {"status": "pending"}
                return self._locked_pr(cwd, branch, github_repository(remote), path)
        except (OSError, ValueError):
            return {"status": "cache-error"}

    def _locked_pr(self, cwd, branch, repository, path):
        now = self.clock()
        try:
            if path.is_symlink():
                raise ValueError("Symlink cache")
            cached = json.loads(path.read_text())
            status = cached.get("status")
            ttl = (self.settings.pr_refresh_seconds if status in ("open", "none")
                   else self.settings.failure_retry_seconds)
            stamp = cached.get("observed_at")
            if (type(stamp) in (int, float) and math.isfinite(stamp)
                    and 0 <= now - stamp < ttl and status in ("open", "none", "error")
                    and (status != "open" or valid_pr(cached.get("pr")))):
                return cached
        except (OSError, ValueError, AttributeError):
            pass

        result = self.run(["gh", "pr", "view", branch, "--repo", repository, "--json",
                           "number,changedFiles,additions,deletions,state"], cwd,
                          timeout=self.settings.command_timeout_seconds)
        snapshot = {"status": "error", "observed_at": now}
        if result and result.returncode == 0:
            try:
                data = json.loads(result.stdout)
                pr = valid_pr(data)
                if pr:
                    snapshot.update(status="open", pr=pr)
                elif isinstance(data, dict) and data.get("state") in ("CLOSED", "MERGED"):
                    snapshot["status"] = "none"
            except (ValueError, UnicodeError):
                pass
        elif result and b"no pull requests found" in result.stderr.lower():
            snapshot["status"] = "none"
        try:
            atomic_json(path, snapshot)
        except (OSError, ValueError):
            # A write race or full disk can still fail after the preflight.
            # Report the failure instead of displaying an uncached success.
            snapshot = {"status": "cache-error", "observed_at": now}
        return snapshot

    def collect(self, cwd):
        """Return plain, numeric-only status text for one active working tree."""
        if not cwd:
            return ""
        parts = []
        if self.settings.show_git:
            result = self.run(["git", "--no-optional-locks", "-C", str(cwd), "status",
                               "--porcelain=v1", "-z", "--untracked-files=normal"], cwd)
            if result is None:
                # Timed out or could not start: keep the bar alive, and PR still shows.
                parts.append("Git …")
            elif result.returncode != 0:
                # Git failure (including a non-repository) must not query GitHub.
                return ""
            else:
                try:
                    parts.append(f"Git Δ{changed_files(result.stdout)}")
                except ValueError:
                    return ""
        if self.settings.show_pr:
            root = self._git(cwd, "rev-parse", "--show-toplevel")
            branch = self._git(cwd, "symbolic-ref", "--quiet", "--short", "HEAD")
            remote = self._git(cwd, "remote", "get-url", "origin")
            if root and branch and remote:
                remote_text = remote.decode(errors="replace").strip()
                try:
                    repository = github_repository(remote_text)
                except ValueError:
                    repository = None
                if not repository:
                    if self.settings.show_errors:
                        parts.append("PR remote?")
                    return " · ".join(parts)
                # Cache availability is checked before network access. Missing
                # tools, no write permission, or unsafe links never hammer APIs.
                if not shutil.which("gh"):
                    if self.settings.show_errors:
                        parts.append("PR gh?")
                    return " · ".join(parts)
                cache_dir = self.state_dir / "pr"
                try:
                    if cache_dir.is_symlink() or self.state_dir.is_symlink():
                        raise ValueError("Unsafe cache directory")
                    cache_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
                    # Use a unique private file rather than a predictable name.
                    fd, probe = tempfile.mkstemp(prefix=".check-", dir=cache_dir)
                    os.close(fd)
                    os.unlink(probe)
                except (OSError, ValueError):
                    if self.settings.show_errors:
                        parts.append("PR cache?")
                    return " · ".join(parts)
                snapshot = self._pr(cwd, root.decode(errors="replace").strip(),
                                    branch.decode(errors="replace").strip(),
                                    remote_text)
                if snapshot["status"] == "open":
                    pr = snapshot["pr"]
                    parts.append(f"PR #{pr['number']}")
                    if self.settings.show_pr_files:
                        parts.append(f"{pr['changedFiles']} files")
                    parts.append(f"+{pr['additions']} −{pr['deletions']}")
                elif self.settings.show_errors:
                    if snapshot["status"] == "error":
                        parts.append("PR ?")
                    elif snapshot["status"] == "cache-error":
                        parts.append("PR cache?")
                    elif snapshot["status"] == "pending":
                        parts.append("PR …")
        return " · ".join(parts)
