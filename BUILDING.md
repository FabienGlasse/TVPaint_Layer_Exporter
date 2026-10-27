# Build and test

The source checkout contains the exporter and both installer recipes. Ready-to-use installer packages belong on the repository's Releases page.

## Tests

On Windows, use Python 3.10 or newer with Tk installed:

```powershell
python -m unittest discover -s exporter -p 'test_*.py'
python -m unittest discover -s packaging -p 'test_*.py'
```

The UI tests create a Tk window with a fake TVPaint connection. They do not export a live project. One optional installer test verifies previously downloaded bridge archives if they are present under `exporter/bridge/`; a clean checkout skips it.

## Installer packages

The guided package needs no compiler. The conventional package uses [Inno Setup](https://jrsoftware.org/isinfo.php). Install Inno Setup 6 in its usual Windows location, put its compiler files under `packaging/tools/InnoSetup/`, or set `INNO_SETUP_COMPILER` to the full path of `ISCC.exe`. Compiler files are excluded from Git.

The editable guide is [User Guide.html](docs/assets/User%20Guide.html). `build_guide.py` renders [User Guide.pdf](docs/assets/User%20Guide.pdf); it needs `reportlab` and Windows Segoe UI fonts. Then `build_installers.ps1` assembles both ZIP files in `dist/`:

```powershell
python -m pip install reportlab
python packaging/build_guide.py
powershell -ExecutionPolicy Bypass -File packaging/build_installers.ps1
```

Review the resulting files and their SHA-256 checksums before uploading them to a release. Installing either package may download Python, PyPI dependencies and the matching BRUNCH Studio connection component. TVPaint itself is not included.

## Publishing updates

Set the next version in `exporter/version.ini` before building, for example `1.0.1`. Package names and the conventional installer's version use this file. Publish a stable GitHub release tagged `v1.0.1` and upload `TVPaint_Layer_Exporter_1.0.1_CMD.zip` and the Setup ZIP. Pushing source to main does not publish an update.

The updater downloads the CMD ZIP for both installation methods. It uses the GitHub release asset's SHA-256 digest, checks its flat payload and embedded version, and waits for the exporter to exit before replacing application files. Keep the update payload names in `exporter/updater.py` and the build recipes in sync. A release with changed requirements, changed TVPaint bridge configuration or a different payload layout requires the full installer.

Updater logs and the previous application files are kept in a session folder under `%LOCALAPPDATA%\TVPaintLayerExporterUpdates`. Settings, the installation record, uninstall registration, Python, the bridge and exports are not part of the update payload. The updater does not change files in a source checkout or install anything during a version check.
