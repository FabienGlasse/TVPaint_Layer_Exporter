"""Manual GitHub release updates for recognized per-user installations."""
from __future__ import annotations

import argparse
import ast
import configparser
import ctypes
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
import webbrowser
import zipfile

REPOSITORY = "FabienGlasse/TVPaint_Layer_Exporter"
RELEASES_URL = f"https://github.com/{REPOSITORY}/releases"
LATEST_URL = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
APP_ID = "FabienGlasse.TVPaintLayerExporter"
MAX_PACKAGE = 50 * 1024 * 1024
PAYLOAD_FILES = (
    "Install.bat", "setup_steps.py", "Uninstall.bat", "uninstall.py", "component_cleanup.py",
    "export_layers.py", "export_options.py", "colour_names.py", "exporter_ui.py", "ui_help.py",
    "updater.py", "version.ini", "requirements.txt", "TVPaint_Exporter_Logo.png",
    "TVPaint_Exporter_Logo.ico", "User Guide.html", "User Guide.pdf",
)


def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(r"v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", value):
        raise ValueError("The release version is not supported.")
    return tuple(map(int, value.removeprefix("v").split(".")))


def version_from_bytes(data):
    config = configparser.ConfigParser()
    config.read_string(data.decode("utf-8"))
    version = config.get("app", "version")
    version_tuple(version)
    return version


def installed_version(root=None):
    return version_from_bytes((Path(root or Path(__file__).parent) / "version.ini").read_bytes())


def check_release(current, opener=urllib.request.urlopen):
    request = urllib.request.Request(LATEST_URL, headers={"User-Agent": "TVPaint-Layer-Exporter", "Accept": "application/vnd.github+json"})
    try:
        with opener(request, timeout=15) as response:
            raw = response.read(1024 * 1024 + 1)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise
    if len(raw) > 1024 * 1024:
        raise ValueError("The release response is too large.")
    data = json.loads(raw)
    if data.get("draft") or data.get("prerelease"):
        return None
    version = data["tag_name"].removeprefix("v")
    if version_tuple(version) <= version_tuple(current):
        return None
    name = f"TVPaint_Layer_Exporter_{version}_CMD.zip"
    assets = [asset for asset in data.get("assets", []) if asset.get("name") == name]
    if len(assets) != 1:
        raise ValueError("This release has no supported update package. Use the release download page.")
    asset = assets[0]
    expected_url = f"https://github.com/{REPOSITORY}/releases/download/{data['tag_name']}/{name}"
    if asset.get("browser_download_url") != expected_url or not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", asset.get("digest") or ""):
        raise ValueError("The update download or checksum could not be verified. Use the release download page.")
    size = asset.get("size")
    if type(size) is not int or not 0 < size <= MAX_PACKAGE:
        raise ValueError("The update package size is not supported.")
    return dict(version=version, url=expected_url, sha256=asset["digest"][7:].lower(), size=size,
                notes=str(data.get("body") or "No release notes provided."))


def download_package(release, destination, opener=urllib.request.urlopen):
    destination = Path(destination)
    request = urllib.request.Request(release["url"], headers={"User-Agent": "TVPaint-Layer-Exporter"})
    digest, total, created = hashlib.sha256(), 0, False
    try:
        with opener(request, timeout=30) as response, destination.open("xb") as stream:
            created = True
            while True:
                chunk = response.read(65536)
                if not chunk:
                    break
                total += len(chunk)
                if total > release["size"] or total > MAX_PACKAGE:
                    raise ValueError("The update download is larger than expected.")
                digest.update(chunk)
                stream.write(chunk)
        if total != release["size"] or digest.hexdigest() != release["sha256"]:
            raise ValueError("The update download did not pass its checksum check. No application files were changed.")
    except BaseException:
        if created:
            destination.unlink(missing_ok=True)
        raise
    return destination


def installation_root(root):
    root = Path(root).absolute()
    if root.is_symlink() or root.resolve() != root:
        raise ValueError("The installation folder is redirected. Use the full installer.")
    marker = json.loads((root / "installation.json").read_text(encoding="utf-8"))
    if marker.get("app_id") != APP_ID or Path(marker.get("root", "")).resolve() != root:
        raise ValueError("This is not a recognized exporter installation. Use the full installer.")
    for name in PAYLOAD_FILES:
        path = root / name
        if path.is_symlink() or path.resolve().parent != root or (path.exists() and not path.is_file()):
            raise ValueError("An application file is redirected or unavailable. Use the full installer.")
    return root


def validated_payload(archive, version, sha256):
    if Path(archive).stat().st_size > MAX_PACKAGE:
        raise ValueError("The update package is too large.")
    if hashlib.sha256(Path(archive).read_bytes()).hexdigest() != sha256:
        raise ValueError("The update package checksum does not match.")
    with zipfile.ZipFile(archive) as package:
        entries = package.infolist()
        names = [entry.filename for entry in entries]
        if len(names) != len(set(names)) or set(names) != set(PAYLOAD_FILES):
            raise ValueError("The update package contents are not supported. Use the full installer.")
        if sum(entry.file_size for entry in entries) > MAX_PACKAGE or any(entry.is_dir() for entry in entries):
            raise ValueError("The unpacked update is too large or has an unsupported layout.")
        payload = {name: package.read(name) for name in PAYLOAD_FILES}
    if version_from_bytes(payload["version.ini"]) != version:
        raise ValueError("The package version does not match the published release.")
    return payload


def compatible_payload(root, payload):
    def requirements(data):
        return sorted(line.strip() for line in data.decode("utf-8").splitlines() if line.strip() and not line.lstrip().startswith("#"))
    if requirements((root / "requirements.txt").read_bytes()) != requirements(payload["requirements.txt"]):
        raise ValueError("This release needs different components. Download the full installer from the release page.")
    def bridge_config(data):
        tree = ast.parse(data.decode("utf-8"))
        assignment = next(node for node in tree.body if isinstance(node, ast.Assign) and
                          any(isinstance(target, ast.Name) and target.id == "CONFIG" for target in node.targets))
        return ast.literal_eval(assignment.value)
    try:
        unchanged_bridge = bridge_config((root / "setup_steps.py").read_bytes()) == bridge_config(payload["setup_steps.py"])
    except (OSError, ValueError, SyntaxError, StopIteration):
        unchanged_bridge = False
    if not unchanged_bridge:
        raise ValueError("This release changes the TVPaint connection component. Use the full installer from the release page.")


def atomic_write(path, data):
    descriptor, name = tempfile.mkstemp(prefix=".update_", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def apply_payload(root, archive, version, sha256, backup):
    root = installation_root(root)
    payload = validated_payload(archive, version, sha256)
    if version_tuple(version) <= version_tuple(installed_version(root)):
        raise ValueError("This version is already installed or is older than the installed exporter.")
    compatible_payload(root, payload)
    backup = Path(backup)
    backup.mkdir(exist_ok=False)
    originals = {}
    # Back up every replaceable file before changing any of them.
    for name in PAYLOAD_FILES:
        path = root / name
        originals[name] = path.read_bytes() if path.exists() else None
        if originals[name] is not None:
            (backup / name).write_bytes(originals[name])
    changed = []
    try:
        for name in [name for name in PAYLOAD_FILES if name != "version.ini"] + ["version.ini"]:
            changed.append(name)
            atomic_write(root / name, payload[name])
    except BaseException as exc:
        failed = []
        for name in reversed(changed):
            try:
                if originals[name] is None:
                    (root / name).unlink(missing_ok=True)
                else:
                    atomic_write(root / name, originals[name])
            except OSError as restore_error:
                failed.append(f"{name}: {restore_error}")
        if failed:
            raise RuntimeError(f"The update stopped and some files could not be restored. Backup: {backup}\n" + "\n".join(failed)) from exc
        raise RuntimeError("The update stopped. The previous application files were restored. " + str(exc)) from exc


def launch_helper(root, archive, release, workspace):
    runner = Path(workspace) / "update_runner.py"
    shutil.copy2(Path(__file__), runner)
    return subprocess.Popen([sys.executable, "-I", str(runner), "--apply", str(root), str(archive),
                             "--version", release["version"], "--sha256", release["sha256"], "--wait-pid", str(os.getpid())],
                            close_fds=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def wait_for_parent(pid):
    if os.name != "nt":
        raise RuntimeError("The updater currently supports Windows installations.")
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x00100000, False, pid)
    if not handle:
        if ctypes.get_last_error() == 87:  # The parent already exited.
            return
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        if kernel.WaitForSingleObject(handle, 30000) != 0:
            raise RuntimeError("The exporter has not closed. No update was installed.")
    finally:
        kernel.CloseHandle(handle)


def helper_main(args):
    import tkinter as tk
    from tkinter import messagebox
    root = tk.Tk()
    root.withdraw()
    log = Path(__file__).with_name("update.log")
    try:
        wait_for_parent(args.wait_pid)
        destination = installation_root(args.apply[0])
        # Verify imports with the installed Python before touching installed files.
        payload = validated_payload(args.apply[1], args.version, args.sha256)
        compatible_payload(destination, payload)
        staged = Path(__file__).with_name("staged")
        staged.mkdir(exist_ok=False)
        for name, data in payload.items():
            (staged / name).write_bytes(data)
        subprocess.run([sys.executable, "-I", str(staged / "export_layers.py"), "--self-check", str(staged / "check.json")],
                       check=True, timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        subprocess.run([sys.executable, "-I", "-c", "import sys; sys.path.insert(0,sys.argv[1]); import exporter_ui, updater", str(staged)],
                       check=True, timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        apply_payload(destination, args.apply[1], args.version, args.sha256, Path(__file__).with_name("backup"))
        log.write_text(f"Updated to {args.version}\n", encoding="utf-8")
        subprocess.Popen([sys.executable, "-I", str(destination / "export_layers.py")], close_fds=True)
    except Exception as exc:
        log.write_text(str(exc), encoding="utf-8")
        messagebox.showerror("Update stopped", f"{exc}\n\nUpdate log: {log}", parent=root)
    finally:
        root.destroy()


class UpdateWindow:
    def __init__(self, parent, can_install, finish):
        import tkinter as tk
        from tkinter import ttk
        self.folder = Path(__file__).resolve().parent
        self.current = installed_version(self.folder)
        self.can_install, self.finish = can_install, finish
        self.release = None
        self.poll_job = None
        self.events = queue.Queue()
        self.window = tk.Toplevel(parent)
        self.window.title("Exporter updates")
        self.window.configure(background="#3c3c3c")
        self.window.transient(parent)
        self.window.resizable(False, False)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        box = ttk.Frame(self.window, padding=18)
        box.pack(fill="both", expand=True)
        ttk.Label(box, text=f"Installed version: {self.current}").pack(anchor="w")
        self.status = tk.StringVar(value="Checking for updates…")
        ttk.Label(box, textvariable=self.status, wraplength=440).pack(anchor="w", pady=10)
        self.notes = tk.Text(box, width=62, height=9, wrap="word", background="#303030", foreground="white", relief="flat", state="disabled")
        self.notes.pack(fill="x")
        ttk.Label(box, text="The exporter will close and reopen. Settings and exports are kept.", wraplength=440, style="Muted.TLabel").pack(anchor="w", pady=10)
        row = ttk.Frame(box)
        row.pack(fill="x")
        self.install = ttk.Button(row, text="Download and update", command=self.download, state="disabled")
        self.install.pack(side="left")
        ttk.Button(row, text="Open release page", command=lambda: webbrowser.open(RELEASES_URL)).pack(side="left", padx=6)
        self.check = ttk.Button(row, text="Check again", command=self.check_now, state="disabled")
        self.check.pack(side="left")
        self.poll_job = self.window.after(100, self.poll)
        self.check_now()

    def check_now(self):
        self.check.configure(state="disabled")
        self.install.configure(state="disabled")
        self.status.set("Checking for updates…")
        def worker():
            try:
                self.events.put(("release", check_release(self.current)))
            except Exception as exc:
                self.events.put(("error", f"Could not check for updates: {exc}"))
        threading.Thread(target=worker, daemon=True).start()

    def download(self):
        if not self.can_install():
            self.status.set("Finish or cancel the current export before updating.")
            return
        self.install.configure(state="disabled")
        self.check.configure(state="disabled")
        self.status.set("Downloading and checking the update…")
        release = dict(self.release)
        def worker():
            try:
                location = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "TVPaintLayerExporterUpdates"
                location.mkdir(parents=True, exist_ok=True)
                workspace = Path(tempfile.mkdtemp(prefix="update_", dir=location))
                archive = download_package(release, workspace / "update.zip")
                payload = validated_payload(archive, release["version"], release["sha256"])
                compatible_payload(installation_root(self.folder), payload)
                self.events.put(("downloaded", (archive, release, workspace)))
            except Exception as exc:
                self.events.put(("error", f"The update was not installed: {exc}"))
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        try:
            while True:
                kind, data = self.events.get_nowait()
                self.check.configure(state="normal")
                if kind == "release":
                    self.release = data
                    self.status.set(f"Version {data['version']} is available." if data else "You're up to date.")
                    self.notes.configure(state="normal")
                    self.notes.delete("1.0", "end")
                    if data:
                        self.notes.insert("1.0", data["notes"])
                        try:
                            installation_root(self.folder)
                            self.install.configure(state="normal")
                        except (OSError, ValueError):
                            self.status.set("A newer version is available. This source checkout updates through Git or the full installer.")
                    self.notes.configure(state="disabled")
                elif kind == "downloaded":
                    if not self.can_install():
                        self.status.set("An export is running. Finish it, then choose Download and update again.")
                        self.install.configure(state="normal")
                    else:
                        try:
                            self.finish(lambda: launch_helper(self.folder, *data))
                            return
                        except Exception as exc:
                            self.status.set(f"Could not start the updater: {exc}")
                else:
                    self.status.set(data)
        except queue.Empty:
            pass
        self.poll_job = self.window.after(100, self.poll)

    def close(self):
        if self.poll_job is not None:
            self.window.after_cancel(self.poll_job)
        self.window.destroy()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", nargs=2, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--wait-pid", type=int, required=True)
    helper_main(parser.parse_args())
