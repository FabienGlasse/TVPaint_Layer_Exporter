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
