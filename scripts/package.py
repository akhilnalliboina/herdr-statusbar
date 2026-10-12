#!/usr/bin/env python3
"""Build a reproducible, source-only release archive and SHA-256 checksum."""
import gzip
import hashlib
from io import BytesIO
from pathlib import Path
import re
import tarfile
import tomllib

root = Path(__file__).resolve().parents[1]
manifest = tomllib.loads((root / "herdr-plugin.toml").read_text())
version = manifest["version"]
if not re.fullmatch(r"\d+\.\d+\.\d+", version):
    raise SystemExit("Invalid release version")
files = [root / name for name in ["README.md", "LICENSE", "SECURITY.md", "CHANGELOG.md", ".gitignore",
                                  "herdr-plugin.toml", "cli.py", "install.py", "statusbar.py", "dashboard.py"]]
for directory in ["scripts", "tests", "docs", ".github/workflows"]:
    files.extend(path for path in (root / directory).rglob("*")
                 if path.is_file() and path.suffix in (".py", ".sh", ".md", ".yml")
                 and "__pycache__" not in path.parts)
buffer = BytesIO()
with tarfile.open(fileobj=buffer, mode="w", format=tarfile.PAX_FORMAT) as archive:
    for path in sorted(files):
        if path.is_symlink():
            raise SystemExit(f"Refusing symlink in release: {path}")
        info = tarfile.TarInfo("herdr-statusbar/" + str(path.relative_to(root)))
        data = path.read_bytes()
        info.size = len(data)
        info.mode = 0o644
        info.mtime = 0
        archive.addfile(info, BytesIO(data))
output = root / "dist" / f"herdr-statusbar-{version}.tar.gz"
output.parent.mkdir(exist_ok=True)
with output.open("wb") as raw:
    with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
        compressed.write(buffer.getvalue())
checksum = hashlib.sha256(output.read_bytes()).hexdigest()
output.with_suffix(output.suffix + ".sha256").write_text(f"{checksum}  {output.name}\n")
print(output)
print(checksum)
