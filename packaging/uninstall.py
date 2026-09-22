"""Remove this user's exporter installation, preserving projects and shared tools."""
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import component_cleanup

APP_ID = "FabienGlasse.TVPaintLayerExporter"
FILES = ("export_layers.py", "export_options.py", "exporter_ui.py", "User Guide.html", "User Guide.pdf", "Freelancer Guide.html", "Freelancer Guide.pdf",
         "TVPaint_Exporter_Logo.png", "TVPaint_Exporter_Logo.ico", "requirements.txt",
         "setup_steps.py", "component_cleanup.py", "python_path.txt", "Install.bat", "uninstall.py", "installation.json",
         "settings.json", "settings.tmp", "setup.log")
REGISTRY_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\TVPaintLayerExporter"


def removal_plan(root):
    """Resolve and validate every deletion target before removing anything."""
    root = Path(root).absolute()
    if root.is_symlink() or root.resolve() != root:
        raise ValueError("The installation folder is redirected; no files were removed.")
    marker = json.loads((root / "installation.json").read_text(encoding="utf-8"))
    if marker.get("app_id") != APP_ID or Path(marker.get("root", "")).resolve() != root:
        raise ValueError("This folder is not a recognized exporter installation.")
    files = [root / name for name in FILES if (root / name).exists()]
    venv = root / "venv"
    directories = [venv] if venv.exists() else []
    for target in files + directories:
        if target.resolve().parent != root or target.is_symlink():
            raise ValueError("An installation item points outside the exporter folder.")
    # Do not traverse Windows junctions/reparse points when deleting the environment.
    if venv.exists():
        for parent, dirs, names in os.walk(venv, followlinks=False):
            for name in dirs + names:
                path = Path(parent) / name
                if name == "export_manifest.json" or path.suffix.lower() == ".tvpp":
                    raise ValueError("Project or export files were found inside the exporter environment. Move them out before uninstalling.")
                if path.is_symlink() or getattr(path.lstat(), "st_file_attributes", 0) & 0x400:
                    raise ValueError("The exporter environment contains a redirected folder or file.")
                if not path.resolve().is_relative_to(venv.resolve()):
                    raise ValueError("An environment item points outside the exporter folder.")
    return files, directories


def remove(root):
    files, directories = removal_plan(root)
    for directory in directories:
        shutil.rmtree(directory)
    for path in files:
        path.unlink()
    # Unknown files (including exports), Python and TVPaint's bridge remain untouched.


def main(components_only=False, gui=False):
    root = Path(__file__).resolve().parent
    conventional = root / "unins000.exe"
    if conventional.is_file() and not components_only:
        subprocess.Popen([str(conventional)])
        return
    removal_plan(root)
    print("TVPAINT / LAYER EXPORTER — Uninstall\n")
    print("Remove the exporter, its settings and its desktop shortcut.")
    print("Your exports will be kept. Python and the connection component are optional.\n")
    if not components_only and input("Uninstall? [Y/N]: ").strip().lower() not in ("y", "yes"):
        print("Nothing was removed.")
        return 2
    choices = component_cleanup.choose_components(root, gui=gui)
    installer = component_cleanup.prepare_removal(root, choices)
    if choices["bridge"]:
        component_cleanup.remove_bridge(root)
        with (root / "component_removal.log").open("a", encoding="utf-8") as stream:
            stream.write("Recorded TVPaint connection component removed.\n")
    if components_only:
        if installer:
            component_cleanup.schedule_python_uninstall(root, installer)
        return 0
    # Read the recorded shortcut; never remove a path supplied by the manifest.
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as key:
        desktop = Path(os.path.expandvars(winreg.QueryValueEx(key, "Desktop")[0]))
    shortcut = desktop / "TVPaint Layer Exporter.lnk"
    if shortcut.is_file():
        # Only remove it if its target arguments point at this installation.
        environment = os.environ.copy()
        environment.update(TVPE_SHORTCUT=str(shortcut), TVPE_SCRIPT=str(root / "export_layers.py"))
        command = "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:TVPE_SHORTCUT); if($s.Arguments.Contains($env:TVPE_SCRIPT)){Remove-Item -LiteralPath $env:TVPE_SHORTCUT}"
        subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command], env=environment, check=True)
    remove(root)
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY)
    except FileNotFoundError:
        pass
    if installer:
        component_cleanup.schedule_python_uninstall(root, installer)
    print("\nExporter uninstalled. Your exports were kept.")
    if installer:
        print("Python's official uninstall window will open next. Complete it to remove Python.")


if __name__ == "__main__":
    try:
        sys.exit(main(components_only="--components-only" in sys.argv, gui="--gui" in sys.argv) or 0)
    except Exception as exc:
        print(f"Uninstall could not finish: {exc}")
        if "--gui" in sys.argv:
            import tkinter as tk
            from tkinter import messagebox
            window = tk.Tk()
            window.withdraw()
            messagebox.showerror("Optional removal stopped", str(exc) + "\n\nShared components that were not removed are kept. Exporter removal can continue.")
            window.destroy()
        sys.exit(1)
