# v0.2.0 verification

- The operator confirmed the Git/PR toolbar in v0.1.0. The v0.2.0 combined toolbar is now installed in the live config; its command output is verified below.
- 60 unit tests passed on macOS with Python 3.11 and 3.14.
- 60 unit tests passed on Ubuntu 24.04 x86_64 with Python 3.11 and 3.14.
- Real Herdr 0.9.3 configure/reload/unconfigure smoke tests passed on macOS and Linux, with top and bottom placement.
- A real Open-Meteo request using the configured Heidelberg coordinates returned a Celsius temperature. Coordinates are sent only when weather is enabled.
- Live macOS system output included CPU, RAM percentage, battery percentage, weather temperature, and the German date/time format: `CPU 19% · RAM 94% · ϟ80% · 13°C · 12.10.2026 12:05` (sample values).
- The RAM metric includes cache and buffers; see the README for platform-specific accounting.

Linux ran in an emulated x86_64 Docker container on an arm64 Mac. GitHub CI still needs to run on the v0.2.0 source commit before tagging. The live Herdr toolbar now uses the plugin's integrated segments; visual confirmation of the full combined line is pending.
