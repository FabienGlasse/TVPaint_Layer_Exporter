"""Explicit, optional removal of recorded shared components."""
from pathlib import Path
import ctypes
import hashlib
import json
import os
import subprocess
import sys
import re


def metadata(root):
    root = Path(root).resolve()
    data = json.loads((root / "installation.json").read_text(encoding="utf-8"))
    if data.get("app_id") != "FabienGlasse.TVPaintLayerExporter" or Path(data.get("root", "")).resolve() != root:
        raise ValueError("The exporter installation record is invalid.")
    return data


def bridge_target(root):
    from setup_steps import version_of
    data = metadata(root).get("bridge")
    if not data:
        raise ValueError("No connection component is recorded. Run setup again to record its location.")
    exe = Path(data["tvpaint_exe"])
    version = version_of(exe)
    plugin_root = exe.parent / ("plugins" if version == "11.7.3" else "Resources/plugins")
    target = Path(data["path"])
    if target.is_symlink() or target.resolve() != target.absolute() or not target.resolve().is_relative_to(plugin_root.resolve()):
        raise ValueError("The connection component location is redirected or outside TVPaint's plugins folder.")
    if target.suffix.lower() != ".dll" or "rpc" not in target.name.lower():
        raise ValueError("The recorded file is not a TVPaint connection component.")
    if not target.is_file():
        raise ValueError("The recorded connection component is already absent.")
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    if digest != data["sha256"]:
        raise ValueError("The connection component changed since setup. It will be kept.")
    return target


def remove_bridge_file(root):
    from setup_steps import require_tvpaint_closed
    require_tvpaint_closed()
    target = bridge_target(root)
    # Delete this exact verified DLL only; never recurse through a plugin folder.
    target.unlink()


def remove_bridge(root):
    target = bridge_target(root)
    try:
        remove_bridge_file(root)
    except PermissionError:
        environment = os.environ.copy()
        environment["TVPE_CLEANUP_PYTHON"] = sys.executable
        environment["TVPE_CLEANUP_ARGS"] = subprocess.list2cmdline([
            "-I", str(Path(__file__).resolve()), "--remove-bridge", str(Path(root).resolve())])
        command = "$p=Start-Process -FilePath $env:TVPE_CLEANUP_PYTHON -ArgumentList $env:TVPE_CLEANUP_ARGS -Verb RunAs -WindowStyle Hidden -Wait -PassThru; exit $p.ExitCode"
        result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command], env=environment)
        if result.returncode or target.exists():
            raise RuntimeError("The connection component was not removed. Administrator permission may have been declined; save your work and close TVPaint before retrying.")


def split_windows_command(command):
    from ctypes import wintypes
    argc = ctypes.c_int()
    function = ctypes.windll.shell32.CommandLineToArgvW
    function.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int)]
    function.restype = ctypes.POINTER(wintypes.LPWSTR)
    argv = function(command, ctypes.byref(argc))
    if not argv:
        raise ValueError("The Python uninstall command is invalid.")
    try:
        return [argv[i] for i in range(argc.value)]
    finally:
        free = ctypes.windll.kernel32.LocalFree
        free.argtypes = [ctypes.c_void_p]
        free(argv)


def registered_python_uninstaller(executable, version):
    """Only match a CPython registration for this exact interpreter directory."""
    import winreg
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                tag = ".".join(version.split(".")[:2])
                with winreg.OpenKey(hive, rf"Software\Python\PythonCore\{tag}\InstallPath", 0, winreg.KEY_READ | view) as key:
                    registered = Path(winreg.QueryValue(key, None)) / "python.exe"
                if registered.resolve() != Path(executable).resolve():
                    continue
                with winreg.OpenKey(hive, r"Software\Microsoft\Windows\CurrentVersion\Uninstall", 0, winreg.KEY_READ | view) as base:
                    for i in range(winreg.QueryInfoKey(base)[0]):
                        try:
                            with winreg.OpenKey(base, winreg.EnumKey(base, i)) as key:
                                if winreg.QueryValueEx(key, "DisplayName")[0] != f"Python {version} (64-bit)":
                                    continue
                                if winreg.QueryValueEx(key, "Publisher")[0] != "Python Software Foundation":
                                    continue
                                parts = split_windows_command(winreg.QueryValueEx(key, "UninstallString")[0])
                                if len(parts) == 2 and parts[1].lower() == "/uninstall":
                                    return Path(parts[0])
                        except OSError:
                            continue
            except OSError:
                continue
    raise ValueError("No official uninstaller was found for this Python. Use Windows Settings > Apps if it was installed separately.")


def python_uninstaller(root):
    root = Path(root).resolve()
    data = metadata(root).get("python")
    if not data:
        raise ValueError("Python's installation details were not recorded. Run setup again before removing it here.")
    executable = Path(data["executable"])
    if not re.fullmatch(r"\d+\.\d+\.\d+", data.get("version", "")):
        raise ValueError("The recorded Python version is invalid.")
    if not executable.is_file():
        raise ValueError("The recorded Python installation is already absent.")
    if data.get("installed_by_exporter"):
        if executable.resolve() != root / "python/python.exe":
            raise ValueError("The recorded exporter Python location is invalid.")
        installer = root / f"python-{data['version']}-amd64.exe"
        if not installer.is_file():
            installer = registered_python_uninstaller(executable, data["version"])
    else:
        installer = registered_python_uninstaller(executable, data["version"])
    if not installer.is_file() or installer.suffix.lower() != ".exe":
        raise ValueError("Python's official uninstaller is unavailable.")
    return installer


def verify_python_publisher(installer):
    environment = os.environ.copy()
    environment["TVPE_PYTHON_UNINSTALLER"] = str(installer)
    command = "$s=Get-AuthenticodeSignature -LiteralPath $env:TVPE_PYTHON_UNINSTALLER; if($s.Status -ne 'Valid' -or $s.SignerCertificate.Subject -notmatch 'O=Python Software Foundation'){exit 1}"
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command], env=environment)
    if result.returncode:
        raise ValueError("Python's uninstaller publisher could not be verified. Python will be kept.")


def schedule_python_uninstall(root, installer):
    """Wait for this interpreter to exit before opening Python's own uninstall UI."""
    environment = os.environ.copy()
    environment.update(TVPE_PYTHON_UNINSTALLER=str(installer), TVPE_CLEANUP_PID=str(os.getpid()),
                       TVPE_CLEANUP_LOG=str(Path(root) / "component_removal.log"))
    command = ("Wait-Process -Id ([int]$env:TVPE_CLEANUP_PID) -ErrorAction SilentlyContinue; "
               "try { $p=Start-Process -FilePath $env:TVPE_PYTHON_UNINSTALLER -ArgumentList '/uninstall' -Wait -PassThru; "
               "Add-Content -LiteralPath $env:TVPE_CLEANUP_LOG -Value ('Python uninstaller exit code: '+$p.ExitCode) } "
               "catch { Add-Content -LiteralPath $env:TVPE_CLEANUP_LOG -Value ('Python uninstall could not start: '+$_.Exception.Message) }")
    subprocess.Popen(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command], env=environment,
                     creationflags=subprocess.CREATE_NO_WINDOW)


def availability(root):
    result = {}
    for name, resolver in (("python", python_uninstaller), ("bridge", bridge_target)):
        try:
            result[name] = (resolver(root), "")
        except (ValueError, OSError, KeyError) as exc:
            result[name] = (None, str(exc))
    return result


def choose_components(root, gui=False):
    choices = availability(root)
    if not gui:
        print("\nOptional shared components (press Enter to keep each):")
        selected = {}
        for key, label in (("python", "Python"), ("bridge", "TVPaint connection component")):
            target, reason = choices[key]
            if target is None:
                print(f"\n{label}: {reason}")
                selected[key] = False
            else:
                print(f"\n{label}: {target}")
                print("Other tools using this component will stop working.")
                if key == "bridge":
                    print("Save your work and close TVPaint. Windows may ask for administrator permission.")
                selected[key] = input(f"Also remove {label}? [y/N]: ").strip().lower() in ("y", "yes")
        return selected
    import tkinter as tk
    from tkinter import ttk
    window = tk.Tk()
    window.title("TVPaint Layer Exporter - Optional removal")
    window.resizable(False, False)
    box = ttk.Frame(window, padding=22)
    box.pack(fill="both", expand=True)
    ttk.Label(box, text="Also remove shared components?", font=("Segoe UI", 14, "bold")).pack(anchor="w", pady=(0, 12))
    ttk.Label(box, text="Both are kept unless selected. Your exported files are always kept.", wraplength=600).pack(anchor="w")
    variables = {}
    for key, label in (("python", "Remove Python"), ("bridge", "Remove the TVPaint connection component")):
        target, reason = choices[key]
        value = tk.BooleanVar(value=False)
        variables[key] = value
        ttk.Checkbutton(box, text=label, variable=value, state="normal" if target else "disabled").pack(anchor="w", pady=(18, 4))
        ttk.Label(box, text=str(target) if target else reason, wraplength=600, foreground="#666666").pack(anchor="w")
    ttk.Label(box, text="Other tools using a removed component will stop working.\nClose TVPaint before removing its connection component.\nPython opens its own uninstall window; Windows may ask for permission.", wraplength=600).pack(anchor="w", pady=18)
    selected = {"python": False, "bridge": False}
    def finish():
        selected.update({key: value.get() for key, value in variables.items()})
        window.destroy()
    ttk.Button(box, text="Continue", command=finish).pack(anchor="e")
    window.protocol("WM_DELETE_WINDOW", window.destroy)  # Closing keeps both.
    window.mainloop()
    return selected


def prepare_removal(root, choices):
    """Validate both choices before changing anything."""
    installer = python_uninstaller(root) if choices["python"] else None
    if installer:
        verify_python_publisher(installer)
    if choices["bridge"]:
        bridge_target(root)
        from setup_steps import require_tvpaint_closed
        require_tvpaint_closed()
    return installer


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    if len(sys.argv) == 3 and sys.argv[1] == "--remove-bridge":
        try:
            remove_bridge_file(Path(sys.argv[2]))
        except Exception:
            sys.exit(1)
    else:
        sys.exit(2)
