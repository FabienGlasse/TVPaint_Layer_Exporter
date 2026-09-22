"""Export planning, preferences and readable delivery reports (standard library only)."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import json
import os
import tempfile
import re
from datetime import datetime

# TVPaint save modes, file extensions and transparency support.
IMAGE_FORMATS = {
    "PNG": ("png", "png", True),
    "JPEG": ("jpeg", "jpg", False),
    "TIFF": ("Mode=15", "tiff", True),
    "TGA": ("tga", "tga", True),
    "BMP": ("bmp", "bmp", False),
}


@dataclass
class Options:
    layer_ids: list[int] | None = None
    first: int | None = None
    last: int | None = None
    prefix: str = ""
    numbering: int = 1
    padding: int = 3
    image_format: str = "PNG"
    background: bool = False
    layer_folders: bool = True
    combine: bool = False
    sequence_name: str = ""
    folder_prefix: str = ""

    def __post_init__(self):
        if self.layer_ids is not None and (not isinstance(self.layer_ids, list) or
                                         any(type(value) is not int for value in self.layer_ids)):
            raise ValueError("The selected layer list is invalid.")
        if not isinstance(self.prefix, str) or not isinstance(self.folder_prefix, str) or any(type(value) is not int for value in (self.numbering, self.padding)):
            raise ValueError("The filename settings are invalid.")
        if any(value is not None and type(value) is not int for value in (self.first, self.last)):
            raise ValueError("The frame range is invalid.")
        if self.image_format not in IMAGE_FORMATS or type(self.background) is not bool or type(self.layer_folders) is not bool:
            raise ValueError("Choose a supported image format and background option.")
        if type(self.combine) is not bool or not isinstance(self.sequence_name, str):
            raise ValueError("The sequence settings are invalid.")


def identity(info):
    # Session IDs deliberately prevent resuming against another open scene.
    keys = ("project_id", "clip_id", "project_path", "clip_name", "width", "height", "fps", "start", "end", "frame_offset")
    return {**{k: info.get(k) for k in keys},
            "layers": [{k: layer[k] for k in ("id", "name")} for layer in info["layers"]]}


def plan(info, output, options=None):
    from export_layers import folder_names
    options = options or Options()
    first = info["start"] if options.first is None else options.first
    last = info["end"] if options.last is None else options.last
    if not info["start"] <= first <= last <= info["end"]:
        raise ValueError(f"Choose a range within {info['start']}–{info['end']}.")
    if options.numbering < 0 or not 1 <= options.padding <= 9:
        raise ValueError("Start numbering at 0 or higher; use 1–9 digits.")
    prefix = options.prefix.strip()
    folder_prefix = options.folder_prefix.strip()
    if folder_prefix and folder_names([folder_prefix])[0] != folder_prefix:
        raise ValueError("Use a shorter folder prefix without filename punctuation or trailing spaces/dots.")
    if prefix and folder_names([prefix])[0] != prefix:
        raise ValueError("Use a shorter shot name without filename punctuation or trailing spaces/dots.")
    layers = [dict(layer) for layer in info["layers"]
              if not layer.get("is_folder", False) and (options.layer_ids is None or layer["id"] in options.layer_ids)]
    if not layers or (options.layer_ids is not None and set(options.layer_ids) != {x['id'] for x in layers}):
        raise ValueError("Select at least one available layer.")
    notices = []
    selected_ids = [x["id"] for x in layers]
    if options.combine:
        name = options.sequence_name.strip() or layers[0]["name"]
        layers = [dict(id=layers[0]["id"], name=name, visible=True,
                       source_ids=selected_ids, source_names=[x["name"] for x in layers])]
    names = folder_names([x["name"] for x in layers])
    for layer, name in zip(layers, names):
        layer.update(folder=(folder_prefix + "_" if folder_prefix else "") + name,
                     filename=name, frames_written=0)
        if name != layer["name"]:
            notices.append(f"Folder: {layer['name']} → {name} (duplicate or unsupported name).")
    background = options.background or not IMAGE_FORMATS[options.image_format][2]
    if background and not options.background:
        notices.append(f"{options.image_format} uses a background because it cannot store transparency.")
    opts = Options(selected_ids, first, last, prefix, options.numbering, options.padding,
                   options.image_format, background, options.layer_folders,
                   options.combine, layers[0]["name"] if options.combine else "", folder_prefix)
    result = dict(options=asdict(opts), layers=layers, total=len(layers) * (last-first+1), notices=notices)
    for layer in layers:
        path = frame_path(output, layer, last, result["options"])
        if len(str(path.resolve())) >= 250:
            raise ValueError("The output path is too long. Choose a shorter folder or shot name.")
        if len(str(path.resolve())) >= 220:
            notices.append("Output paths are close to the Windows length limit.")
    return result


def new_output_folder(parent, now=None):
    """Seconds are sufficient; a simple counter protects against rare collisions."""
    base = "TVPaint_export_" + (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    path = Path(parent) / base
    number = 2
    while path.exists():
        path = Path(parent) / f"{base}_{number}"
        number += 1
    return path


def sequence_conflicts(output, task):
    """Return existing images belonging to the sequences in *task*."""
    output = Path(output)
    if not output.exists():
        return []
    root_files = [p for p in output.iterdir() if p.is_file()]
    conflicts = []
    prefix = task["options"]["prefix"]
    for layer in task["layers"]:
        files = list(root_files)
        if task["options"]["layer_folders"]:
            for child in output.iterdir():
                if (child.name.casefold() == layer["folder"].casefold() and child.is_dir()
                        and not child.is_symlink() and child.resolve().parent == output.resolve()):
                    files.extend(p for p in child.iterdir() if p.is_file())
        stem = (prefix + "_" if prefix else "") + layer.get("filename", layer["folder"])
        pattern = re.compile(re.escape(stem) + r"_\d+\.(png|jpg|jpeg|tiff?|tga|bmp)$", re.I)
        folder_exists = task["options"]["layer_folders"] and any(
            p.name.casefold() == layer["folder"].casefold() and not p.is_dir() for p in output.iterdir())
        matches = [path for path in files if pattern.fullmatch(path.name)]
        if folder_exists or matches:
            conflicts.extend(matches)
            if folder_exists:
                conflicts.append(next(p for p in output.iterdir()
                                      if p.name.casefold() == layer["folder"].casefold() and not p.is_dir()))
    return list(dict.fromkeys(conflicts))


def check_sequence_conflicts(output, task):
    """Protect prior sequences even after their manifest has been replaced."""
    conflicts = sequence_conflicts(output, task)
    if conflicts:
        prefix = task["options"]["prefix"]
        layer = task["layers"][0]
        stem = (prefix + "_" if prefix else "") + layer.get("filename", layer["folder"])
        if any(path.is_file() and path.parent == Path(output) and path.name.casefold() == layer["folder"].casefold()
               for path in conflicts):
            stem = layer["folder"]
            raise ValueError(f'"{stem}" is already an export in this folder. Choose another sequence name or prefix.')
        raise ValueError(f'"{stem}" is already an export in this folder. Choose another sequence name or prefix.')


def frame_path(output, layer, frame, options):
    number = options["numbering"] + frame - options["first"]
    prefix = options["prefix"] + "_" if options["prefix"] else ""
    extension = IMAGE_FORMATS[options.get("image_format", "PNG")][1]
    folder = Path(output) / layer["folder"] if options.get("layer_folders", True) else Path(output)
    return folder / f"{prefix}{layer.get('filename', layer['folder'])}_{number:0{options['padding']}d}.{extension}"


def check_writable(parent):
    parent = Path(parent)
    if not parent.is_dir():
        raise ValueError("Choose an existing output folder.")
    try:
        with tempfile.TemporaryFile(dir=parent) as stream:
            stream.write(b"export permission check")
            stream.flush()
    except OSError as exc:
        raise ValueError("Cannot write to this folder. Choose a different output folder.") from exc


def settings_path():
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "TVPaintLayerExporter" / "settings.json"


def read_settings():
    try:
        data = json.loads(settings_path().read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        return {k: v for k, v in data.items() if k in ("parent", "prefix", "folder_prefix", "numbering", "padding", "image_format", "background", "flat_output") and isinstance(v, str)}
    except (OSError, ValueError):
        return {}


def write_settings(values):
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(path, values)


def atomic_json(path, data, *, hidden=False):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)
    if hidden and os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetFileAttributesW.argtypes = [wintypes.LPCWSTR]
        kernel.GetFileAttributesW.restype = wintypes.DWORD
        kernel.SetFileAttributesW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]
        kernel.SetFileAttributesW.restype = wintypes.BOOL
        attributes = kernel.GetFileAttributesW(str(path))
        if attributes == 0xFFFFFFFF or not kernel.SetFileAttributesW(str(path), attributes | 0x2):
            raise ctypes.WinError(ctypes.get_last_error())


def report_header(manifest):
    lines = ["TVPAINT / LAYER EXPORTER - (•ᆺ•)づ  DELIVERY REPORT", "",
             f"Project: {manifest.get('project_path') or manifest['project_id']}",
             f"Clip: {manifest.get('clip_name') or manifest['clip_id']}", "", "Layer structure (top to bottom):"]
    for layer in manifest.get("source_stack", manifest["layers"]):
        name = f"[{layer['name']}]" if layer.get("is_folder") else "- " + layer["name"]
        lines.append(name + (" (hidden)" if not layer.get("visible", True) else ""))
    return "\n".join(lines) + "\n"


def report(manifest):
    opts = manifest["options"]
    image_format = opts.get("image_format", "PNG")
    lines = [f"Export started: {manifest.get('created', '')}",
             f"Status: {manifest['status']}. {manifest.get('elapsed_seconds', 0):.1f} seconds", "",
             f"Frames: {opts['first']}–{opts['last']}",
             f"Numbering starts at: {opts['numbering']}",
             f"Image format: {image_format}",
             f"Layout: {'One folder per layer' if opts.get('layer_folders', True) else 'All images in the output folder'}",
             f"Background: {manifest.get('background_description', 'Included' if opts.get('background') else 'None (transparent)')}",
             f"Files: {sum(x['frames_written'] for x in manifest['layers'])} / {manifest['total']}", "",
             "Layers / folders:"]
    for layer in manifest['layers']:
        destination = layer['folder']
        if not opts.get('layer_folders', True):
            prefix = opts['prefix'] + '_' if opts['prefix'] else ''
            destination = './' + prefix + layer.get('filename', layer['folder']) + '_…'
        lines.append(f"  {layer['name']} → {destination} ({layer['frames_written']} {image_format} files)")
    for layer in manifest["layers"]:
        if layer.get("source_names"):
            lines.append("  Combined layers: " + ", ".join(layer["source_names"]))
    lines += ["", *manifest.get("notices", [])]
    if manifest.get("error"):
        lines += ["", "Stopped: " + manifest["error"]]
    if manifest.get("restore_errors"):
        lines += ["", "TVPaint settings could not all be restored:", *manifest["restore_errors"]]
    return "\n".join(lines).strip() + "\n"
