# Local matrix results — 12.10.2026

**All four local matrix equivalents passed before the first GitHub Actions run.**

At the time of these local checks, the GitHub repository did not exist and the local repository had no remote or commit. No repository, push, tag, or release was created to run these checks. For later hosted checks, see this repository's GitHub Actions tab.

## Results

| Environment | Python | Unit tests | Shell syntax | Packaging | Real Herdr smoke |
| --- | --- | --- | --- | --- | --- |
| macOS 27.0.1, arm64 | 3.11.16 | 49 passed | Passed | Passed | Passed |
| macOS 27.0.1, arm64 | 3.14.7 | 49 passed | Passed | Passed | Passed |
| Ubuntu 24.04, x86_64 container | 3.11.16 | 49 passed | Passed | Passed | Passed |
| Ubuntu 24.04, x86_64 container | 3.14.7 | 49 passed | Passed | Passed | Passed |

Each run used Herdr **0.9.3**. The smoke test registered all four actions, configured and reloaded an isolated real server, confirmed reconfigure was a no-op, then unconfigured and reloaded while preserving an existing entry. Each temporary server stopped after its test.

The Linux runs used Docker's linux/amd64 emulation on the arm64 Mac, not GitHub's hosted runner. Ubuntu used Git 2.43.0. The Mac is not the `macos-latest` runner image. GitHub checkout, setup-python, artifact upload, and hosted-runner behavior remain untested. Local results are not a substitute for the hosted checks required before tagging.

All four runs produced the same pre-evidence-update source archive SHA-256:

```text
cc4a28fa4eb215136cf059faeceeed76707509c5b6dceba4ae75a2fd36d1b4b8
```

This binds the tested source snapshot. Adding this document changes the release archive checksum; use the generated `.sha256` file for the current archive. No runtime code changed while recording these results.

## Commands

On macOS, use the selected interpreter for each matrix version:

```sh
sh -n scripts/run.sh
python3.11 -B -m unittest discover -s tests -v
python3.11 scripts/package.py
python3.11 -B scripts/smoke_herdr.py
# Repeat with python3.14.
```

The initial Mac test runs used `-q` instead of `-v`; this changes reporting, not test selection.

Linux image definition:

```dockerfile
FROM ubuntu:24.04
RUN apt-get update && apt-get install -y --no-install-recommends git curl ca-certificates libgcc-s1 libstdc++6 && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.12.19 /uv /usr/local/bin/uv
ENV UV_PYTHON_INSTALL_DIR=/opt/python
RUN uv python install 3.11 3.14
RUN curl --fail --location --retry 3 --max-time 120 https://github.com/herdrdev/herdr/releases/download/v0.9.3/herdr-linux-x86_64 -o /usr/local/bin/herdr && echo '18a8dc65f1c2fa485884344356dea1cfd911c6f06cf46fa78e193f4087f4dba7  /usr/local/bin/herdr' | sha256sum -c - && chmod 755 /usr/local/bin/herdr
```

The binary checksum came from Herdr's official release manifest. Downloads occurred only during image preparation. Image ID used for the tests:

```text
sha256:db6f30b22d67669aedcd1efc3ab0a04f427585019eaa828291a793b5f03f8a82
```

Save the definition as a Dockerfile and build it with:

```sh
docker build --platform linux/amd64 -t herdr-statusbar-ci:local -f /path/to/Dockerfile .
```

Then run from the plugin root:

```sh
for version in 3.11 3.14; do
  docker run --rm --platform linux/amd64 --network none \
    --mount "type=bind,source=$(pwd),target=/source,readonly" \
    --env "TEST_PYTHON=$version" herdr-statusbar-ci:local sh -ec '
      cp -R /source /tmp/plugin
      cd /tmp/plugin
      py=$(uv python find "$TEST_PYTHON")
      mkdir /tmp/test-bin
      ln -s "$py" /tmp/test-bin/python
      ln -s "$py" /tmp/test-bin/python3
      export PATH="/tmp/test-bin:$PATH"
      uname -sm
      python --version
      git --version
      herdr --version
      sh -n scripts/run.sh
      python -B -m unittest discover -s tests -v
      python scripts/package.py
      python -B scripts/smoke_herdr.py
    ' || exit 1
done
```

The source mount was read-only. Execution and packaging used temporary copies. Test containers had no networking, no host home-directory mount, and no forwarded GitHub credentials. GitHub responses in unit tests were fixtures; Linux browser opening, real authenticated GitHub requests, and visible rendering were not tested.
