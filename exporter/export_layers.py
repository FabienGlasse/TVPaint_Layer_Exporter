"""Standalone TVPaint current-clip image exporter. Python 3.10+, PyTVPaint 1.1.2."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import threading
import queue
import unicodedata
import tempfile
import shutil
import ctypes
import sys
import time
import hashlib
from datetime import datetime

# The launcher uses isolated Python; load only our adjacent application modules.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from export_options import Options, IMAGE_FORMATS, plan, frame_path, identity, check_writable, atomic_json, report, report_header, check_sequence_conflicts, sequence_conflicts


def transport_path(path):
    """TVPaint 11's SDK filename handling requires an unquoted safe path."""
    value = str(path.resolve())
    if os.name == "nt":
        function = ctypes.windll.kernel32.GetShortPathNameW
        function.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint]
        function.restype = ctypes.c_uint
        size = function(value, None, 0)
        if size:
            buffer = ctypes.create_unicode_buffer(size)
            if function(value, buffer, size):
                value = buffer.value
    value = value.replace("\\", "/")
    if not re.fullmatch(r"[A-Za-z0-9_./:~\-]+", value):
        raise RuntimeError("TVPaint needs a temporary path without spaces or special characters. "
                           "Set TEMP to a writable folder such as D:\\TVPaintTemp and restart the exporter.")
    return value


def folder_names(names):
    """Preserve valid names; resolve Windows-invalid names and case collisions."""
    used = set()
    result = []
    for name in names:
        base = unicodedata.normalize("NFC", name)
        base = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", base).rstrip(" .")
        base = base[:80].rstrip(" .") or "Layer"
        if re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])(?:\..*)?", base):
            base = "_" + base
        candidate, suffix = base, 2
        while candidate.casefold() in used:
            candidate = f"{base}__{suffix}"
            suffix += 1
        used.add(candidate.casefold())
        result.append(candidate)
    return result


class TVPaint:
    def __init__(self):
        # All communication is local. Do not inherit studio/server connection settings.
        os.environ["PYTVPAINT_WS_HOST"] = "ws://127.0.0.1"
        os.environ["PYTVPAINT_WS_TIMEOUT"] = "10"
        if sys.stdout is None:
            sys.stdout = open(os.devnull, "w")
        if sys.stderr is None:
            sys.stderr = open(os.devnull, "w")
        from pytvpaint import george
        from pytvpaint.george.client import send_cmd
        self.g = george
        self.send = send_cmd

    def inspect(self):
        g = self.g
        project_id = g.tv_project_current_id()
        clip_id = g.tv_clip_current_id()
        layers = []
        position = 0
        while True:
            value = self.send("tv_LayerGetID", position).strip()
            if value.lower() == "none":
                break
            layer = g.tv_layer_info(int(value))
            kind = getattr(layer, "type", "")
            layers.append(dict(id=layer.id, name=layer.name, visible=layer.visibility,
                               is_folder=getattr(kind, "value", kind) == "folder"))
            position += 1
        if not layers:
            raise RuntimeError("The current clip has no layers.")
        project = g.tv_project_info(project_id)
        self.scene_layer_ids = [layer["id"] for layer in layers]
        self.folder_ids = {layer["id"] for layer in layers if layer["is_folder"]}
        self.frame_offset = project.start_frame
        return dict(version=list(g.tv_version()), project_id=project_id, clip_id=clip_id,
                    project_path=str(project.path), width=project.width, height=project.height,
                    fps=project.frame_rate, clip_name=g.tv_clip_name_get(clip_id),
                    frame_offset=self.frame_offset,
                    start=g.tv_first_image() + self.frame_offset,
                    end=g.tv_last_image() + self.frame_offset, layers=layers)

    def snapshot(self):
        return dict(layer=self.g.tv_layer_current_id(), frame=self.g.tv_layer_image_get(),
                    background=self.send("tv_Background"), save=self.send("tv_SaveMode"),
                    alpha=self.send("tv_AlphaSaveMode"))

    def prepare(self, state, options=None):
        options = options or {}
        self.image_format = options.get("image_format", "PNG")
        # tv_Display returns the previous mode when switching it.
        state["display"] = self.send("tv_Display", "all" if options.get("combine") else "current")
        if options.get("background", False):
            background = state["background"]
            # A checkerboard is an editing aid, not an export background.
            if not background.lower().startswith("color "):
                background = "color 255 255 255"
            self.send("tv_Background", background, handle_string=False)
            state["background_description"] = background
        else:
            self.send("tv_Background", "none")
            state["background_description"] = "None (transparent)"
        self.send("tv_SaveMode", IMAGE_FORMATS[self.image_format][0])
        self.send("tv_AlphaSaveMode", "noalpha" if options.get("background", False) else "nopremultiply")

    def activate(self, layer):
        self.g.tv_layer_set(layer["id"])
        if "source_ids" in layer:
            for layer_id in self.scene_layer_ids:
                self.g.tv_layer_display_set(layer_id, layer_id in layer["source_ids"] or layer_id in getattr(self, "folder_ids", set()))
        else:
            for folder_id in getattr(self, "folder_ids", set()):
                self.g.tv_layer_display_set(folder_id, True)
            self.g.tv_layer_display_set(layer["id"], True)

    def render(self, frame, path):
        self.g.tv_layer_image(frame - getattr(self, "frame_offset", 0))
        # Quoted SDK filenames fail on TVPaint 11. Use an ASCII temporary name,
        # then move it with Python so final paths may contain spaces/Unicode.
        with tempfile.TemporaryDirectory(prefix="tvpexport_") as directory:
            staging = Path(directory)
            sdk_folder = transport_path(staging)
            image_format = getattr(self, "image_format", "PNG")
            filename = "frame." + IMAGE_FORMATS[image_format][1]
            self.send("tv_SaveDisplay", sdk_folder + "/" + filename, handle_string=False)
            source = staging / filename
            check_image(source, image_format)
            shutil.move(str(source), str(path))

    def restore(self, state, layers):
        actions = [("visibility " + str(x["id"]), lambda x=x:
                    self.g.tv_layer_display_set(x["id"], x["visible"])) for x in layers]
        actions += [("current layer", lambda: self.g.tv_layer_set(state["layer"])),
                    ("current frame", lambda: self.g.tv_layer_image(state["frame"]))]
        for key, command in [("background", "tv_Background"), ("save", "tv_SaveMode"),
                             ("alpha", "tv_AlphaSaveMode"), ("display", "tv_Display")]:
            if key in state:
                actions.append((key, lambda key=key, command=command:
                                self.send(command, state[key], handle_string=False)))
        errors = []
        for label, action in actions:
            try:
                action()
            except Exception as exc:
                errors.append(f"{label}: {exc}")
        return errors


def check_png(path):
    check_image(path, "PNG")


def check_image(path, image_format):
    if not path.is_file() or path.stat().st_size < 18:
        raise RuntimeError(f"TVPaint did not write a {image_format} image: {path}")
    with path.open("rb") as stream:
        header = stream.read(33)
    valid = {
        "PNG": len(header) >= 33 and header.startswith(b"\x89PNG\r\n\x1a\n"),
        "JPEG": header.startswith(b"\xff\xd8\xff"),
        "TIFF": header.startswith((b"II*\x00", b"MM\x00*")),
        "BMP": header.startswith(b"BM"),
        "TGA": header[2] in (1, 2, 3, 9, 10, 11) and int.from_bytes(header[12:14], "little") > 0
               and int.from_bytes(header[14:16], "little") > 0 and header[16] in (8, 15, 16, 24, 32),
    }[image_format]
    if not valid:
        raise RuntimeError(f"TVPaint returned an invalid {image_format} file: {path}")


def file_hash(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest() if hasattr(hashlib, "file_digest") else hashlib.sha256(stream.read()).hexdigest()


def export(api, output, cancel=None, progress=lambda text: None, *, options=None,
           resume=False, expected=None, on_progress=lambda event: None, reuse_folder=False,
           overwrite=False):
    """Export with per-frame checkpoints; resume verifies completed images first."""
    output = Path(output).resolve()
    info = api.inspect()
    if expected is not None and identity(info) != identity(expected):
        raise ValueError("The active scene changed. Refresh the connection before exporting.")
    manifest_path = output / "export_manifest.json"
    previous = None
    if resume:
        previous = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(previous, dict) or previous.get("schema") != 2 or previous.get("status") == "complete":
            raise ValueError("Choose an interrupted export folder.")
        if previous.get("identity") != identity(info):
            raise ValueError("This export belongs to a different scene or changed layer list. Start a new export.")
        options = Options(**previous["options"])
    task = plan(info, output, options)
    image_format = task["options"]["image_format"]
    check_writable(output if resume or (reuse_folder and output.exists()) else output.parent)
    if not resume:
        if reuse_folder:
            if overwrite:
                for path in sequence_conflicts(output, task):
                    # The helper only returns regular image/file collisions one
                    # level below this export folder; never follow redirects.
                    if (path.suffix.casefold() not in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".tga", ".bmp"}
                            or path.is_symlink() or not path.is_file() or output not in path.resolve().parents):
                        raise ValueError("An existing export points outside this folder and cannot be overwritten.")
                    path.unlink()
            else:
                check_sequence_conflicts(output, task)
        output.mkdir(exist_ok=reuse_folder)
    for layer in task["layers"]:
        if not task["options"]["layer_folders"]:
            continue
        folder = output / layer["folder"]
        if folder.is_symlink() or folder.resolve().parent != output:
            raise ValueError("An output layer folder points outside this export. Choose a new folder.")
    manifest = {**info, **task, "source_stack": info["layers"], "schema": 2, "identity": identity(info), "status": "running",
                "files": {}, "restore_errors": [], "created": (previous or {}).get("created", datetime.now().isoformat())}
    # Reject altered manifests/paths instead of trusting arbitrary filenames.
    expected_files = {str(frame_path(output, layer, frame, task["options"]).relative_to(output)): (layer, frame)
                      for layer in task["layers"]
                      for frame in range(task["options"]["first"], task["options"]["last"] + 1)}
    old_files = dict((previous or {}).get("files", {}))
    if not isinstance(old_files, dict) or set(old_files) - set(expected_files):
        raise ValueError("The resume record is invalid. Start a new export.")
    for relative in expected_files:
        path = output / relative
        expected_parent = output / expected_files[relative][0]["folder"] if task["options"]["layer_folders"] else output
        if path.is_symlink() or path.resolve().parent != expected_parent:
            raise ValueError("An output file points outside this export. Choose a new folder.")
        if path.exists() and relative not in old_files:
            # A crash may occur between writing a PNG and its checkpoint. Such
            # files are adopted only after comparison with a fresh source render.
            check_image(path, image_format)
            old_files[relative] = file_hash(path)
    started = time.monotonic()
    completed = 0
    rendered = 0
    render_started = started
    state = api.snapshot()

    def record():
        manifest["elapsed_seconds"] = time.monotonic() - started
        atomic_json(manifest_path, manifest, hidden=True)

    def interrupted():
        if cancel and cancel.is_set():
            raise InterruptedError("Export cancelled. You can resume from this output folder.")

    def notify(phase, layer, frame, checked=0):
        elapsed = time.monotonic() - started
        remaining = ((time.monotonic() - render_started) / rendered * (task["total"] - completed)) if rendered else None
        on_progress(dict(phase=phase, layer=layer["name"], frame=frame, completed=completed,
                         total=task["total"], elapsed=elapsed, remaining=remaining, checked=checked,
                         verify_total=len(old_files)))
        progress(f"{layer['name']} — frame {frame} ({completed}/{task['total']})")

    error = None
    try:
        api.prepare(state, task["options"])
        manifest["background_description"] = state.get("background_description", "Included" if task["options"]["background"] else "None (transparent)")
        # Re-render recorded frames to verify that even unsaved drawing edits have
        # not changed the source. Existing files are never overwritten on resume.
        if previous:
            checked = 0
            with tempfile.TemporaryDirectory(prefix="tvpe_verify_") as temp:
                sample = Path(temp) / ("frame." + IMAGE_FORMATS[image_format][1])
                for layer in task["layers"]:
                    api.activate(layer)
                    for relative, (entry_layer, frame) in expected_files.items():
                        if entry_layer["id"] != layer["id"] or relative not in old_files:
                            continue
                        interrupted()
                        target = output / relative
                        if target.exists():
                            check_image(target, image_format)
                            if file_hash(target) != old_files[relative]:
                                raise ValueError("An exported image was modified. Start a new export to preserve it.")
                        api.render(frame, sample)
                        if file_hash(sample) != old_files[relative]:
                            raise ValueError("The source drawings changed since this export. Start a new export.")
                        if target.exists():
                            manifest["files"][relative] = old_files[relative]
                            layer["frames_written"] += 1
                            completed += 1
                        checked += 1
                        notify("Checking previous frames", layer, frame, checked)
        # Do not replace an old checkpoint until its source has been validated.
        record()
        render_started = time.monotonic()
        for layer in task["layers"]:
            interrupted()
            folder = output / layer["folder"] if task["options"]["layer_folders"] else output
            if task["options"]["layer_folders"]:
                folder.mkdir(exist_ok=resume or reuse_folder)
            api.activate(layer)
            for frame in range(task["options"]["first"], task["options"]["last"] + 1):
                interrupted()
                path = frame_path(output, layer, frame, task["options"])
                relative = str(path.relative_to(output))
                if relative in manifest["files"]:
                    continue
                # Commit the PNG only after validation; checkpoint each frame.
                descriptor, temporary = tempfile.mkstemp(prefix=".tvpe_", suffix=".partial." + IMAGE_FORMATS[image_format][1], dir=folder)
                os.close(descriptor)
                staging = Path(temporary)
                try:
                    api.render(frame, staging)
                    check_image(staging, image_format)
                    digest = file_hash(staging)
                    if path.exists():
                        raise FileExistsError(f"An output image already exists: {path.name}")
                    staging.rename(path)
                finally:
                    if staging.exists():
                        staging.unlink()
                manifest["files"][relative] = digest
                layer["frames_written"] += 1
                completed += 1
                rendered += 1
                record()
                notify("Exporting", layer, frame)
        manifest["status"] = "complete"
    except BaseException as exc:
        error = exc
        manifest["status"] = "cancelled" if isinstance(exc, (InterruptedError, KeyboardInterrupt)) else "failed"
        manifest["error"] = str(exc)
        if previous and not manifest_path.exists():
            atomic_json(manifest_path, previous, hidden=True)
    finally:
        manifest["restore_errors"] = api.restore(state, info["layers"])
        if manifest["restore_errors"]:
            manifest["status"] = "restore_failed"
        # A rejected resume must keep its original, complete checkpoint.
        if previous and rendered == 0 and error:
            manifest = {**previous, "error": str(error), "restore_errors": manifest["restore_errors"]}
            if manifest["restore_errors"]:
                manifest["status"] = "restore_failed"
        record()
        with (output / "Delivery Report.txt").open("a", encoding="utf-8") as stream:
            if not stream.tell():
                stream.write(report_header(manifest))
            stream.write("\n" + "=" * 64 + "\n\n")
            stream.write(report(manifest))
    if manifest["restore_errors"]:
        raise RuntimeError("TVPaint settings could not all be restored. See " + str(manifest_path)) from error
    if error:
        raise error
    return output


def gui():
    from exporter_ui import run
    run()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inspect", action="store_true", help="Read current clip/layers; do not export or change settings")
    parser.add_argument("--output", type=Path, help="New output directory (must not exist)")
    parser.add_argument("--self-check", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.self_check:
        os.environ["PYTVPAINT_WS_STARTUP_CONNECT"] = "0"
        if sys.stdout is None:
            sys.stdout = open(os.devnull, "w")
        if sys.stderr is None:
            sys.stderr = open(os.devnull, "w")
        import tkinter
        from pytvpaint import george
        args.self_check.write_text(json.dumps({"python": sys.version, "tk": tkinter.Tcl().eval("info patchlevel"),
                                              "api": hasattr(george, "tv_layer_info")}), encoding="utf-8")
    elif args.inspect:
        print(json.dumps(TVPaint().inspect(), indent=2, ensure_ascii=False))
    elif args.output:
        print(export(TVPaint(), args.output, progress=print))
    else:
        gui()
