# Release

For a small release:

1. Run unit tests, shell validation, packaging, and the isolated Herdr smoke test on top and bottom placement. Run the macOS/Linux and Python 3.11/3.14 CI matrix.
2. Review the generated archive and checksum. Push the version tag only after all CI jobs pass.
3. Attach the archive and `.sha256` file to the GitHub release. Test install and configure from that tag in a disposable Herdr profile.

The workflow tests and packages source. It does not publish releases. Never include config files, state, credentials, or backups in the archive.
