"""Shared guided setup for the BAT and conventional installers."""
from __future__ import annotations

import argparse
import atexit
import csv
import ctypes
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import urllib.request
import zipfile
from datetime import datetime
from textwrap import fill

ROOT = Path(__file__).resolve().parent
APP = Path(os.environ.get("TVPE_APP", str(Path(os.environ.get("LOCALAPPDATA", str(ROOT))) / "TVPaintLayerExporter")))
CONFIG = {
    "11.7.3": {
        "url": "https://github.com/brunchstudio/tvpaint-rpc/releases/download/1.1.0/tvpaint-rpc-1.1.0-tvp-11.dll",
        "sha256": "35c9217b879e1cc2173aec602c1cf45a0f737090841f55d37d5ec429541b9455",
        "target": "plugins/tvpaint-rpc-1.1.0-tvp-11.dll",
    },
    "12.1.0": {
        "url": "https://github.com/brunchstudio/tvpaint-rpc/releases/download/1.2.0/tvpaint-rpc-1.2.0-tvp-12.1.zip",
        "sha256": "b60e2e0f991a1b4f116c19bbc16b123fe70594db04a52aa5b71208d5d7db85b4",
        "target": "Resources/plugins/tvpaint-rpc-Windows.plugin/Contents/Windows/tvpaint-rpc.dll",
        "member": "tvpaint-rpc-Windows.plugin/Contents/Windows/tvpaint-rpc.dll",
    },
}


STAGE_TITLES = {
    "S1": "Select TVPaint",
    "S2": "Install required components",
    "S3": "Install the exporter",
    "S4": "Download the TVPaint connection component",
    "S5": "Connect the exporter to TVPaint",
    "S6": "Create the desktop shortcut",
}


def enable_colour():
    if "NO_COLOR" in os.environ or not sys.stdout.isatty():
        return False
    if os.name != "nt":
        return os.environ.get("TERM") != "dumb"
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetStdHandle.argtypes = [wintypes.DWORD]
    kernel.GetStdHandle.restype = wintypes.HANDLE
    kernel.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    handle = kernel.GetStdHandle(-11)
    mode = wintypes.DWORD()
    if not kernel.GetConsoleMode(handle, ctypes.byref(mode)):
        return False
    if not kernel.SetConsoleMode(handle, mode.value | 0x0004):
        return False
    atexit.register(kernel.SetConsoleMode, handle, mode.value)
    return True


COLOUR = enable_colour()
PALETTE = {"heading": "1;38;2;255;153;51", "choice": "1;38;2;255;153;51", "success": "1;36",
           "warning": "1;33", "error": "1;31", "muted": "90"}


def styled(text, tone):
    return f"\033[{PALETTE[tone]}m{text}\033[0m" if COLOUR else text


def banner():
    print(styled("\n  TVPAINT / LAYER EXPORTER", "heading"))
    print(styled("  Guided Installation - Fabien Glasse", "muted"))


def log(message, *, display=None):
    APP.mkdir(parents=True, exist_ok=True)
    line = f"{datetime.now().isoformat(timespec='seconds')} {message}"
    with (APP / "setup.log").open("a", encoding="utf-8") as stream:
        stream.write(line + "\n")
    if display is not None:
        tone = "error" if message.startswith("STOPPED") else "success"
        print(styled(display, tone), flush=True)


def stage_heading(stage):
    number = int(stage[1:])
    rule = "-" * min(72, max(30, shutil.get_terminal_size().columns - 4))
    print("\n\n" + styled(rule, "muted"))
    print(styled(f"  STAGE {number} / 6   {STAGE_TITLES[stage]}", "heading"))
    print(flush=True)


def confirm(stage, description):
    stage_heading(stage)
    for paragraph in description.split("\n"):
        text = fill(paragraph, width=80, break_long_words=False, break_on_hyphens=False)
        if paragraph.startswith("Administrator rights:"):
            text = styled(text, "warning")
        print(text)
    print()
    log(f"{stage} waiting for user: {description}")
    print(styled("  [Y] Continue    [N] Stop setup", "choice"))
    if input("\nYour choice: ").strip().lower() not in ("y", "yes"):
        raise InterruptedError(f"Stopped before {stage}.")
    log(f"{stage} START")
    print(styled("\n  ... Working, please wait.", "muted"), flush=True)


def executable_details(exe):
    """Read the PE machine and Windows version resource without running TVPaint."""
    with exe.open("rb") as stream:
        if stream.read(2) != b"MZ":
            raise ValueError("The selected application is not a Windows executable.")
        stream.seek(60)
        offset = struct.unpack("<I", stream.read(4))[0]
        stream.seek(offset)
        if stream.read(4) != b"PE\0\0":
            raise ValueError("The selected application has an invalid executable header.")
        machine = struct.unpack("<H", stream.read(2))[0]
    from ctypes import wintypes
    library = ctypes.WinDLL("version", use_last_error=True)
    library.GetFileVersionInfoSizeW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
    library.GetFileVersionInfoSizeW.restype = wintypes.DWORD
    library.GetFileVersionInfoW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
    library.VerQueryValueW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.UINT)]
    size = library.GetFileVersionInfoSizeW(str(exe), None)
    if not size:
        return machine, None
    buffer = ctypes.create_string_buffer(size)
    pointer, length = ctypes.c_void_p(), wintypes.UINT()
    if not library.GetFileVersionInfoW(str(exe), 0, size, buffer) or not library.VerQueryValueW(buffer, "\\", ctypes.byref(pointer), ctypes.byref(length)):
        return machine, None
    if length.value < 52:
        return machine, None
    fixed = ctypes.cast(pointer, ctypes.POINTER(wintypes.DWORD))
    if fixed[0] != 0xFEEF04BD:
        return machine, None
    major_minor, patch_build = fixed[2], fixed[3]
    return machine, f"{major_minor >> 16}.{major_minor & 65535}.{patch_build >> 16}"


def version_of(exe, *, allow_unconfirmed=False, confirmed_version=None):
    exe = Path(exe)
    if (not exe.is_file() or "uninstall" in exe.name.lower()
            or not exe.name.lower().startswith("tvpaint animation") or exe.suffix.lower() != ".exe"):
        raise ValueError("Choose the TVPaint application, not its uninstaller.")
    try:
        machine, version = executable_details(exe)
    except (OSError, struct.error) as exc:
        raise ValueError(f"Could not read the selected TVPaint application: {exe}") from exc
    if machine != 0x8664:
        raise ValueError("Choose the Windows 64-bit (x64) TVPaint application.")
    if version is None:
        # Older TVPaint builds may omit the Windows version resource.
        match = re.search(r"TVPaint Animation (11\.7\.3|12\.1\.0)(?!\d)", exe.name, re.I)
        version = match.group(1) if match else None
    if version == "12.0.0" and (allow_unconfirmed or confirmed_version == "12.1.0"):
        return confirmed_version or version
    if version not in CONFIG:
        raise ValueError(f"Detected TVPaint version: {version or 'unavailable'}. This setup supports 11.7.3 or 12.1.0. Selected file: {exe}")
    return version


def choose_tvpaint():
    found = []
    for variable in ("ProgramW6432", "ProgramFiles", "ProgramFiles(x86)"):
        base = Path(os.environ.get(variable, "C:/Program Files")) / "TVPaint Developpement"
        for exe in base.glob("*/*.exe"):
            try:
                version_of(exe, allow_unconfirmed=True)
            except ValueError:
                continue
            if exe not in found:
                found.append(exe)
    print(styled("A. Found versions:\n", "heading"))
    if not found:
        print(styled("   No supported versions were found automatically.\n", "warning"))
    for index, exe in enumerate(found, 1):
        version = version_of(exe, allow_unconfirmed=True)
        label = "12 (exact version needs confirmation)" if version == "12.0.0" else version
        print(styled(f"   [{index}] TVPaint {label}", "choice"))
        print(f"       {exe}\n")
    print(styled("B. Browse for TVPaint\n", "choice"))
    selection = input(styled("Choose TVPaint (number or option B): ", "choice")).strip()
    if selection.lower() == "b":
        import tkinter as tk
        from tkinter import filedialog
        window = tk.Tk()
        window.withdraw()
        selected = filedialog.askopenfilename(title="Select the TVPaint application", filetypes=[("Applications", "*.exe")])
        window.destroy()
        if not selected:
            raise InterruptedError("No TVPaint application selected.")
        exe = Path(selected)
    else:
        if not selection.isdigit() or not 1 <= int(selection) <= len(found):
            raise ValueError("No matching selection. Run setup again and choose a listed number or B.")
        exe = found[int(selection) - 1]
    version_of(exe, allow_unconfirmed=True)
    return exe.resolve()


def selected_version(exe):
    version = version_of(exe, allow_unconfirmed=True)
    log(f"S1 executable {exe}; embedded version {version}; architecture x64")
    if version != "12.0.0":
        return version
    print("\nWindows reports version 12.0.0 for this application.\n"
          "Check the version shown inside TVPaint (Help > About).\n"
          "If it says 12.1.0, type 12.1.0 below to use its connection component.\n"
          "Otherwise press Enter to stop setup.")
    answer = input("\nVersion shown inside TVPaint: ").strip()
    if answer != "12.1.0":
        raise InterruptedError("TVPaint 12.1.0 was not confirmed. Setup stopped before installing components.")
    log("S1 user confirmed TVPaint 12.1.0; embedded Windows version is 12.0.0")
    return version_of(exe, confirmed_version=answer)


def checked_run(arguments, **kwargs):
    result = subprocess.run(arguments, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, errors="replace", **kwargs)
    log(result.stdout)
    if result.returncode:
        print("\n" + result.stdout, flush=True)
        raise RuntimeError(f"Command failed (exit {result.returncode}). See setup.log.")


def verified_bridge(archive, version):
    data = archive.read_bytes()
    if hashlib.sha256(data).hexdigest() != CONFIG[version]["sha256"]:
        raise RuntimeError("Downloaded TVPaint component failed its integrity check.")
    if version == "11.7.3":
        return data
    with zipfile.ZipFile(io.BytesIO(data)) as bundle:
        return bundle.read(CONFIG[version]["member"])


def plugin_conflict(exe, version, expected):
    plugin_root = exe.parent / ("plugins" if version == "11.7.3" else "Resources/plugins")
    matching = None
    for path in plugin_root.rglob("*rpc*.dll"):
        if path.read_bytes() != expected:
            raise RuntimeError(f"Another TVPaint connection component exists. Ask the studio to check it: {path}")
        matching = path
    return matching


def require_tvpaint_closed():
    result = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True,
                            text=True, errors="replace", check=True)
    if any(row and row[0].lower().startswith("tvpaint animation") for row in csv.reader(io.StringIO(result.stdout))):
        raise RuntimeError("Save your work and close TVPaint, then run setup again.")


def admin_copy(exe, archive, confirmed_version=None):
    version = version_of(exe, confirmed_version=confirmed_version)
    expected = verified_bridge(archive, version)
    require_tvpaint_closed()
    if plugin_conflict(exe, version, expected):
        return
    target = exe.parent / CONFIG[version]["target"]
    target.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation: never replace an existing component, even on a race.
    with target.open("xb") as stream:
        stream.write(expected)


def elevate_plugin(exe, archive, version):
    environment = os.environ.copy()
    environment["TVPE_ADMIN_PYTHON"] = sys.executable
    environment["TVPE_ADMIN_ARGS"] = subprocess.list2cmdline([
        "-I", str(Path(__file__).resolve()), "--copy-plugin", str(exe), str(archive),
        "--confirmed-version", version])
    # The only elevated action is the explicit validated plugin copy.
    command = "$p=Start-Process -FilePath $env:TVPE_ADMIN_PYTHON -ArgumentList $env:TVPE_ADMIN_ARGS -Verb RunAs -WindowStyle Hidden -Wait -PassThru; exit $p.ExitCode"
    checked_run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command], env=environment)


def main():
    if os.environ.get("TVPE_BANNER_SHOWN") != "1":
        banner()
    stage_heading("S1")
    log("S1 select TVPaint")
    exe = choose_tvpaint()
    version = selected_version(exe)
    log(f"S1 selected {exe}", display=f"\nSelected: TVPaint {version}")
    confirm("S2", "Download and install the components needed by the exporter from pypi.org.")
    venv = APP / "venv"
    python = venv / "Scripts/python.exe"
    if not python.exists():
        checked_run([sys.executable, "-I", "-m", "venv", str(venv)])
    checked_run([str(python), "-I", "-m", "pip", "install", "--index-url", "https://pypi.org/simple", "--disable-pip-version-check", "-r", str(ROOT / "requirements.txt")])
    checked_run([str(python), "-I", "-m", "pip", "check"])
    log("S2 COMPLETE", display="\nRequired components installed.")
    confirm("S3", f"Copy the exporter and its guide to:\n{APP}")
    for name in ("export_layers.py", "export_options.py", "exporter_ui.py", "User Guide.html", "Freelancer Guide.pdf", "TVPaint_Exporter_Logo.png", "TVPaint_Exporter_Logo.ico", "Uninstall.bat", "uninstall.py", "component_cleanup.py", "setup_steps.py"):
        source, target = ROOT / name, APP / name
        if source.resolve() != target.resolve():
            shutil.copy2(source, target)
    runtime = json.loads(subprocess.check_output([str(python), "-I", "-c",
        "import json,sys; print(json.dumps({'executable':sys._base_executable,'version':'.'.join(map(str,sys.version_info[:3]))}))"], text=True))
    runtime["executable"] = str(Path(runtime["executable"]).resolve())
    runtime["installed_by_exporter"] = Path(runtime["executable"]).parent == (APP / "python").resolve()
    installation = {"app_id": "FabienGlasse.TVPaintLayerExporter", "root": str(APP.resolve()), "python": runtime}
    (APP / "installation.json").write_text(json.dumps(installation), encoding="utf-8")
    (APP / "python_path.txt").write_text(runtime["executable"], encoding="utf-8")
    if not (APP / "unins000.exe").exists():
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall\TVPaintLayerExporter") as key:
            for name, value in {"DisplayName": "TVPaint Layer Exporter", "DisplayVersion": "2.0.0",
                                "Publisher": "Fabien Glasse", "InstallLocation": str(APP),
                                "DisplayIcon": str(APP / "TVPaint_Exporter_Logo.ico"),
                                "UninstallString": subprocess.list2cmdline([os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", str(APP / "Uninstall.bat")])}.items():
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
            for name in ("NoModify", "NoRepair"):
                winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, 1)
    log("S3 COMPLETE", display="\nExporter installed.")
    confirm("S4", f"Download the official connection component for TVPaint {version}\nfrom github.com/brunchstudio and check the downloaded file.")
    downloads = APP / "downloads"
    downloads.mkdir(exist_ok=True)
    archive = downloads / CONFIG[version]["url"].rsplit("/", 1)[1]
    urllib.request.urlretrieve(CONFIG[version]["url"], archive)
    expected = verified_bridge(archive, version)
    log("S4 COMPLETE: checksum verified", display="\nDownload complete. File verified.")
    matching = plugin_conflict(exe, version, expected)
    if matching:
        stage_heading("S5")
        log(f"S5 SKIPPED: matching component already installed at {matching}",
            display="The correct connection component is already installed.\nNo action needed.")
    else:
        confirm("S5", f"Copy the connection component to:\n{exe.parent / CONFIG[version]['target']}\n\nSave your work and close TVPaint before continuing.\n\nAdministrator rights: required. Windows will ask for permission.")
        require_tvpaint_closed()
        elevate_plugin(exe, archive, version)
        if not plugin_conflict(exe, version, expected):
            raise RuntimeError("The TVPaint component was not installed.")
        log("S5 COMPLETE", display="\nTVPaint connection component installed.")
    installed_bridge = plugin_conflict(exe, version, expected)
    installation["bridge"] = {"tvpaint_exe": str(exe), "path": str(installed_bridge.resolve()),
                              "sha256": hashlib.sha256(expected).hexdigest()}
    (APP / "installation.json").write_text(json.dumps(installation), encoding="utf-8")
    confirm("S6", "Add a TVPaint Layer Exporter shortcut to your desktop.")
    environment = os.environ.copy()
    environment["TVPE_TARGET"] = str(venv / "Scripts/pythonw.exe")
    environment["TVPE_ARGUMENTS"] = subprocess.list2cmdline(["-I", str(APP / "export_layers.py")])
    environment["TVPE_ICON"] = str(APP / "TVPaint_Exporter_Logo.ico")
    command = "$d=[Environment]::GetFolderPath('Desktop'); $s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d 'TVPaint Layer Exporter.lnk')); $s.TargetPath=$env:TVPE_TARGET; $s.Arguments=$env:TVPE_ARGUMENTS; $s.IconLocation=$env:TVPE_ICON; $s.Save()"
    checked_run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command], env=environment)
    log("S6 COMPLETE. Open or restart TVPaint and use the desktop shortcut.",
        display="\nDesktop shortcut created.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--copy-plugin", nargs=2, metavar=("TVPAINT_EXE", "VERIFIED_DOWNLOAD"))
    parser.add_argument("--confirmed-version", choices=tuple(CONFIG))
    parser.add_argument("--preview", action="store_true", help="Show the console design without installing anything")
    args = parser.parse_args()
    if args.preview:
        banner()
        stage_heading("S1")
        print(styled("A. Found versions:\n", "heading"))
        print(styled("   [1] TVPaint 11.7.3", "choice"))
        print("       C:\\Program Files\\TVPaint\\TVPaint Animation 11.7.3 Pro (64bits).exe\n")
        print(styled("B. Browse for TVPaint\n", "choice"))
        print(styled("Choose TVPaint (number or option B): ", "choice"))
        stage_heading("S5")
        print("Copy the connection component into TVPaint.\n")
        print(styled("Administrator rights: required. Windows will ask for permission.\n", "warning"))
        print(styled("  [Y] Continue    [N] Stop setup\n", "choice"))
        print(styled("Connection component installed successfully.\n", "success"))
        print(styled("Example error: setup could not finish.\n", "error"))
        print("Preview only - no changes made.")
    elif args.copy_plugin:
        try:
            admin_copy(*(Path(value).resolve() for value in args.copy_plugin), confirmed_version=args.confirmed_version)
        except Exception:
            sys.exit(1)
    else:
        try:
            main()
        except (Exception, KeyboardInterrupt) as exc:
            log(f"STOPPED: {exc}", display=f"\n\nSetup stopped\n\n{exc}\n")
            sys.exit(1)
