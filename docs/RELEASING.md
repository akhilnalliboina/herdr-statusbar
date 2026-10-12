# Release checklist

No publishing step runs during configure, installation, tests, or packaging.

1. Run `python3 -B -m unittest discover -s tests -v` and `sh -n scripts/run.sh`.
2. Complete the [manual checks](SMOKE_TEST.md), including a real macOS and Linux Herdr session. Record the release commit and result. Automated tests do not prove screen rendering.
3. Run the macOS/Linux and Python 3.11/3.14 matrix locally; record the environments and commands. See [local matrix results](CI_RESULTS.md). These do not prove GitHub-hosted CI passes.
4. Confirm the version in `herdr-plugin.toml`, `cli.py --version`, and `CHANGELOG.md` matches. Use a `v0.1.0` tag for the initial release.
5. Run `python3 scripts/package.py`. Review the archive contents and SHA-256 checksum; they must contain no credentials, state, backups, or machine-specific config.
6. Create the public `akhilnalliboina/herdr-statusbar` GitHub repository only with the owner's approval. Push the reviewed source, then confirm GitHub CI passes all four matrix jobs. Push the reviewed tag only after those hosted checks pass. Do not claim this repository exists before that step.
7. Publish a GitHub release with the archive and checksum. Explain minimum versions, platform coverage, privacy, and limitations.
8. Test the documented GitHub install command from a clean profile, including configure, update/reconfigure, and unconfigure/uninstall.
9. Submit the plugin through Herdr's current [marketplace process](https://herdr.dev/docs/marketplace/). Do not use an outdated submission URL.

The CI workflow uploads build artifacts only. It does not create releases or push tags. There is no automatic dependency installation in the plugin manifest.
