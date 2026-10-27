"""TVPaint exporter interface. All TVPaint work runs off the UI thread."""
from pathlib import Path
import json
import os
import queue
import re
import threading
import tkinter as tk
from tkinter import ttk, filedialog
from datetime import datetime

from export_options import Options, IMAGE_FORMATS, plan, frame_path, check_writable, read_settings, write_settings, new_output_folder, check_sequence_conflicts, sequence_conflicts
from export_layers import TVPaint, export
from ui_help import Tooltip, Tutorial
from updater import UpdateWindow


class ExporterWindow:
    def __init__(self, root):
        self.root = root
        self.info = None
        self.busy = False
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.destination = None
        self.resume_folder = None
        self.session_folder = None
        self.name_overridden = False
        self.updating_name = False
        self.last_selection = ()
        self.check_job = None
        self.overwrite_key = None
        self.pending_conflict_key = None
        saved = read_settings()
        self.parent = tk.StringVar(value=saved.get("parent", ""))
        self.prefix = tk.StringVar(value=saved.get("prefix", ""))
        self.folder_prefix = tk.StringVar(value=saved.get("folder_prefix", ""))
        self.sections = {}
        self.numbering = tk.StringVar(value=saved.get("numbering", "1"))
        self.padding = tk.StringVar(value=saved.get("padding", "3"))
        self.image_format = tk.StringVar(value=saved.get("image_format", "PNG") if saved.get("image_format", "PNG") in IMAGE_FORMATS else "PNG")
        self.background = tk.BooleanVar(value=saved.get("background", "0") == "1")
        self.flat_output = tk.BooleanVar(value=saved.get("flat_output", "0") == "1")
        self.mode = tk.StringVar(value="Auto Mode")
        self.active_mode = "Auto Mode"
        self.combine = tk.BooleanVar(value=False)
        self.colour_naming = tk.StringVar(value="top")
        self.tooltips = []
        self.tutorial = None
        self.update_window = None
        self.sequence_name = tk.StringVar()
        self.session_status = tk.StringVar(value="Auto Mode creates a new folder for each export.")
        self.format_note = tk.StringVar()
        self.first = tk.StringVar()
        self.last = tk.StringVar()
        self.connection = tk.StringVar(value="Checking TVPaint…")
        self.scene = tk.StringVar()
        self.preview = tk.StringVar(value="Connect to TVPaint to preview filenames.")
        self.notice = tk.StringVar()
        self.status = tk.StringVar()
        self.counter = tk.StringVar(value="0 / 0 frames")
        self.timing = tk.StringVar(value="Elapsed 0:00  ·  Remaining —")
        self.checks = {}
        self.colour_checks = {}
        self.swatches = []
        self.controls = []
        root.title("TVPaint Layer Exporter")
        root.geometry("940x840")
        root.minsize(880, 820)
        assets = Path(__file__).resolve().parent
        self.logo = tk.PhotoImage(file=str(assets / "TVPaint_Exporter_Logo.png"))
        root.iconphoto(True, self.logo)
        if os.name == "nt":
            root.iconbitmap(str(assets / "TVPaint_Exporter_Logo.ico"))
        style = ttk.Style(root)
        # Native Windows themes ignore custom progress colours; clam honours them.
        style.theme_use("clam")
        grey, field, white, muted, disabled, orange = "#3c3c3c", "#303030", "#ffffff", "#aaaaaa", "#686868", "#ff9933"
        root.configure(background=grey)
        style.configure(".", background=grey, foreground=white, fieldbackground=field,
                        bordercolor="#606060", lightcolor=grey, darkcolor=grey)
        style.configure("TEntry", fieldbackground=field, foreground=white, insertcolor=white)
        style.configure("TButton", background="#505050", foreground=white, padding=(8, 5))
        style.map("TButton", background=[("disabled", "#414141"), ("active", "#626262"), ("pressed", "#707070")],
                  foreground=[("disabled", disabled)])
        style.map("TEntry", foreground=[("disabled", disabled)], fieldbackground=[("disabled", grey)])
        style.configure("TCheckbutton", indicatorbackground=field, indicatorforeground=white)
        style.map("TCheckbutton", background=[("active", grey)], foreground=[("disabled", disabled)],
                  indicatorbackground=[("selected", orange), ("disabled", "#494949")])
        style.configure("TRadiobutton", indicatorbackground=field)
        style.map("TRadiobutton", background=[("active", grey)], foreground=[("disabled", disabled)],
                  indicatorbackground=[("disabled", "#494949"), ("selected", orange)])
        style.configure("TLabelframe.Label", foreground=white)
        style.configure("TCombobox", fieldbackground=field, foreground=white, arrowcolor=white)
        style.map("TCombobox", fieldbackground=[("readonly", field), ("disabled", grey)],
                  foreground=[("disabled", disabled), ("readonly", white)],
                  selectbackground=[("readonly", field)], selectforeground=[("readonly", white)])
        root.option_add("*TCombobox*Listbox.background", field)
        root.option_add("*TCombobox*Listbox.foreground", white)
        root.option_add("*TCombobox*Listbox.selectBackground", "#666666")
        root.option_add("*TCombobox*Listbox.selectForeground", white)
        style.configure("Title.TLabel", font=("Segoe UI", 18, "bold"))
        style.configure("Muted.TLabel", foreground=muted)
        style.configure("Disabled.TLabel", foreground=disabled)
        style.configure("Scene.TLabel", foreground=orange)
        style.configure("Subtle.TLabel", foreground="#858585")
        style.configure("Section.TButton", anchor="w", padding=(8, 2), background=grey)
        style.configure("Quiet.TButton", background=grey, foreground="#929292", borderwidth=0, padding=(5, 3))
        style.map("Quiet.TButton", foreground=[("disabled", disabled), ("active", white)],
                  background=[("active", "#505050")])
        style.configure("Notice.TLabel", foreground=orange)
        style.configure("ActiveMode.TButton", background=orange, foreground=field)
        style.map("ActiveMode.TButton", background=[("disabled", "#414141"), ("active", "#ffad5c")],
                  foreground=[("disabled", disabled)])
        style.configure("Accent.Horizontal.TProgressbar", background=orange, lightcolor=orange,
                        darkcolor=orange, bordercolor=field, troughcolor=field)
        style.layout("Layers.Vertical.TScrollbar", [("Vertical.Scrollbar.trough", {"sticky": "ns", "children": [
            ("Vertical.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})]})])
        style.configure("Layers.Vertical.TScrollbar", background="#717171", troughcolor=field,
                        borderwidth=0, arrowsize=9, width=9, relief="flat")
        style.map("Layers.Vertical.TScrollbar", background=[("active", orange), ("pressed", orange)])
        box = ttk.Frame(root, padding=20)
        box.pack(fill="both", expand=True)
        header = ttk.Frame(box)
        header.pack(fill="x")
        ttk.Label(header, text="TVPaint Layer Exporter", style="Title.TLabel").pack(side="left")
        row = ttk.Frame(box)
        row.pack(fill="x", pady=(8, 12))
        connection_box = ttk.Frame(row)
        connection_box.pack(side="left", fill="x", expand=True)
        ttk.Label(connection_box, textvariable=self.connection, wraplength=450).pack(anchor="w")
        ttk.Label(connection_box, textvariable=self.scene, style="Scene.TLabel", wraplength=450).pack(anchor="w")
        connection_tools = ttk.Frame(row)
        connection_tools.pack(side="right", anchor="n")
        buttons = ttk.Frame(connection_tools)
        buttons.pack(anchor="e")
        self.refresh_button = self.button(buttons, "Connect", self.connect)
        self.refresh_button.pack(side="right")
        self.help_button = self.button(buttons, "?", self.start_tutorial)
        self.help_button.configure(width=3)
        self.help_button.pack(side="right", padx=(14, 8))
        self.mode_buttons = {}
        for label, mode in (("AUTO", "Auto Mode"), ("MANUAL", "Manual Mode"), ("LAYER COLORS", "Colour Mode")):
            button = self.button(buttons, label, lambda value=mode: self.choose_mode(value))
            button.pack(side="left", padx=(0, 5))
            self.mode_buttons[mode] = button
        self.mode_button = self.mode_buttons["Manual Mode"]
        self.update_mode_buttons()
        ttk.Label(connection_tools, textvariable=self.session_status, style="Subtle.TLabel",
                  wraplength=390, justify="right").pack(anchor="e", pady=(4, 0))
        body = ttk.Frame(box)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)
        left = ttk.LabelFrame(body, text="Layers", padding=10)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        tools = ttk.Frame(left)
        tools.pack(fill="x", pady=(0, 8))
        for label, mode in (("All", "all"), ("Visible", "visible"), ("None", "none")):
            self.button(tools, label, lambda m=mode: self.select(m)).pack(side="left", padx=(0, 4))
        self.canvas = tk.Canvas(left, highlightthickness=0, width=220, height=150, background=grey)
        scrollbar = ttk.Scrollbar(left, orient="vertical", command=self.canvas.yview, style="Layers.Vertical.TScrollbar")
        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        def scroll_position(first, last):
            scrollbar.set(first, last)
            if float(first) <= 0 and float(last) >= 1:
                scrollbar.pack_forget()
            elif not scrollbar.winfo_manager():
                scrollbar.pack(side="right", fill="y", before=self.canvas)
        self.canvas.configure(yscrollcommand=scroll_position)
        self.canvas.bind("<MouseWheel>", self.scroll_layers)
        self.layer_box = ttk.Frame(self.canvas)
        self.layer_window = self.canvas.create_window((0, 0), window=self.layer_box, anchor="nw")
        self.layer_box.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.layer_window, width=e.width))
        right = ttk.Frame(body)
        right.grid(row=0, column=1, sticky="nsew")
        ttk.Label(right, text="Export settings").pack(anchor="w", pady=(0, 4))
        self.settings_panel = ttk.Frame(right)
        self.settings_panel.pack(fill="both", expand=True)
        right = self.settings_panel
        formats = self.settings_section(right, "format", "Edit image format")
        frames = self.settings_section(right, "frames", "Edit frame range")
        prefixes = self.settings_section(right, "prefixes", "Edit folder / filename prefixes")
        sequence = self.settings_section(right, "sequence", "Edit sequence name")
        row = ttk.Frame(formats)
        row.pack(fill="x", pady=(0, 4))
        ttk.Label(row, text="Image format ").pack(side="left")
        self.format_picker = ttk.Combobox(row, textvariable=self.image_format, values=list(IMAGE_FORMATS),
                                         state="readonly", width=7)
        self.format_picker.pack(side="left")
        self.controls.append(self.format_picker)
        self.background_check = ttk.Checkbutton(row, text="Background", variable=self.background)
        self.background_check.pack(side="left", padx=(12, 0))
        self.controls.append(self.background_check)
        ttk.Label(formats, textvariable=self.format_note, style="Muted.TLabel", width=52).pack(anchor="w", pady=(0, 10))
        ttk.Label(frames, text="Frame range").pack(anchor="w")
        row = ttk.Frame(frames)
        row.pack(fill="x", pady=(4, 12))
        self.entry(row, self.first, 7).pack(side="left")
        ttk.Label(row, text="  to  ").pack(side="left")
        self.entry(row, self.last, 7).pack(side="left")
        self.button(row, "Set to Full clip", self.full_range).pack(side="left", padx=8)
        row = ttk.Frame(prefixes)
        row.pack(fill="x")
        for label, variable in (("Folder prefix", self.folder_prefix), ("Filename prefix", self.prefix)):
            column = ttk.Frame(row)
            column.pack(side="left", fill="x", expand=True, padx=(0, 8))
            heading = ttk.Frame(column)
            heading.pack(fill="x")
            ttk.Label(heading, text=label + " ").pack(side="left")
            ttk.Label(heading, text="(optional)", style="Muted.TLabel").pack(side="left")
            entry = self.entry(column, variable, 18)
            entry.pack(fill="x", pady=(4, 12))
            if variable is self.folder_prefix:
                self.folder_prefix_entry = entry
        row = ttk.Frame(frames)
        row.pack(fill="x")
        ttk.Label(row, text="Start numbering ").pack(side="left")
        self.entry(row, self.numbering, 7).pack(side="left")
        ttk.Label(row, text="   Extra digits ").pack(side="left")
        self.entry(row, self.padding, 3).pack(side="left")
        self.sequence_label = ttk.Label(sequence, text="Sequence name (when combined)", style="Disabled.TLabel")
        self.sequence_label.pack(anchor="w", pady=(12, 4))
        row = ttk.Frame(sequence)
        row.pack(fill="x")
        self.sequence_entry = self.entry(row, self.sequence_name)
        self.sequence_entry.pack(side="left", fill="x", expand=True)
        self.name_reset = self.button(row, "Use top layer", self.reset_sequence_name)
        self.name_reset.pack(side="left", padx=(6, 0))
        self.name_bottom = self.button(row, "Use bottom layer", self.use_bottom_layer)
        self.name_bottom.pack(side="left", padx=(6, 0))
        colour_naming = self.settings_section(right, "colour_naming", "Edit sequence naming")
        self.colour_name_radios = []
        for text, value in (("Use color group names", "colour"), ("Use universal color names", "universal"),
                            ("Use top layer", "top"), ("Use bottom layer", "bottom")):
            radio = ttk.Radiobutton(colour_naming, text=text, variable=self.colour_naming, value=value)
            radio.pack(anchor="w", pady=2)
            self.controls.append(radio)
            self.colour_name_radios.append(radio)
        preview_box = self.preview_box = ttk.Frame(right, padding=12, relief="solid", borderwidth=1)
        preview_box.pack(side="bottom", fill="x")
        ttk.Label(preview_box, text="Filename preview", style="Muted.TLabel").pack(anchor="w", pady=(0, 4))
        ttk.Label(preview_box, textvariable=self.preview, wraplength=390).pack(anchor="w")
        self.configure_sections()
        ttk.Label(box, text="Output folder").pack(anchor="w", pady=(14, 4))
        row = ttk.Frame(box)
        row.pack(fill="x")
        self.parent_entry = self.entry(row, self.parent)
        self.parent_entry.pack(side="left", fill="x", expand=True)
        self.browse_button = self.button(row, "Browse…", self.browse)
        self.browse_button.pack(side="left", padx=(8, 0))
        row = ttk.Frame(box)
        row.pack(fill="x", pady=(7, 0))
        self.combine_check = ttk.Checkbutton(row, text="Export as one sequence", variable=self.combine)
        self.combine_check.pack(side="left", padx=(0, 18))
        self.controls.append(self.combine_check)
        self.flat_check = ttk.Checkbutton(row, text="Put all files directly in the output folder", variable=self.flat_output)
        self.flat_check.pack(side="left")
        self.controls.append(self.flat_check)
        notice_row = ttk.Frame(box)
        notice_row.pack(fill="x", pady=(6, 8))
        ttk.Label(notice_row, textvariable=self.notice, style="Notice.TLabel", wraplength=700).pack(side="left", fill="x", expand=True)
        self.overwrite_button = self.button(notice_row, "Overwrite layers", self.approve_overwrite)
        row = ttk.Frame(box)
        row.pack(fill="x")
        self.start_button = self.button(row, "Export layers", self.start)
        self.start_button.pack(side="left")
        self.resume_button = self.button(row, "Resume interrupted export…", self.load_resume)
        self.resume_button.configure(style="Quiet.TButton")
        self.resume_button.pack(side="left", padx=8)
        self.cancel_button = ttk.Button(row, text="Cancel", command=self.cancel.set, state="disabled")
        self.cancel_button.pack(side="right")
        self.bar = ttk.Progressbar(box, maximum=1, style="Accent.Horizontal.TProgressbar")
        self.bar.pack(fill="x", pady=(12, 5))
        row = ttk.Frame(box)
        row.pack(fill="x")
        ttk.Label(row, textvariable=self.counter).pack(side="left")
        ttk.Label(row, textvariable=self.timing, style="Muted.TLabel").pack(side="right")
        ttk.Label(box, textvariable=self.status, wraplength=790).pack(anchor="w", pady=(5, 6))
        self.report_box = tk.Text(box, height=5, wrap="word", relief="flat", font=("Segoe UI", 9),
                                  background=field, foreground=white, insertbackground=white,
                                  selectbackground="#666666", selectforeground=white, state="disabled")
        self.report_box.pack(fill="x")
        bottom = ttk.Frame(box)
        bottom.pack(fill="x", pady=(8, 0))
        self.open_button = ttk.Button(bottom, text="Open export folder", command=self.open_folder, state="disabled")
        self.open_button.pack(side="left")
        self.report_button = ttk.Button(bottom, text="Open delivery report", command=self.open_report, state="disabled")
        self.report_button.pack(side="left", padx=8)
        self.update_button = self.button(bottom, "Check for updates", self.check_updates)
        self.update_button.configure(style="Quiet.TButton")
        self.update_button.pack(side="left", padx=(8, 0))
        ttk.Label(bottom, text="by Fabien Glasse", foreground="#565656", font=("Segoe UI", 10, "italic")).pack(side="right")
        for value in (self.parent, self.prefix, self.folder_prefix, self.numbering, self.padding, self.first, self.last, self.image_format, self.background, self.flat_output, self.combine, self.colour_naming):
            value.trace_add("write", self.schedule_check)
        self.add_tooltips()
        self.sequence_name.trace_add("write", self.name_edited)
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(100, self.poll)
        root.after(150, self.connect)
        root.after_idle(self.set_minimum_size)

    def button(self, parent, text, command):
        widget = ttk.Button(parent, text=text, command=command)
        self.controls.append(widget)
        explanations = {
            "AUTO": 'Auto Mode exports checked layers separately.',
            "MANUAL": 'Manual Mode builds a delivery over several exports in the same folder.',
            "LAYER COLORS": 'Layer colors use TVPaint color labels to build your delivery.',
            "Connect": "Connect to TVPaint and load the current clip, layers and colours.",
            "Refresh": "Reload the current clip, layers and colours from TVPaint.",
            "?": "Walk through the exporter with a short guided tutorial.",
            "All": 'Check all available layers, including hidden layers and default groups.',
            "Visible": "Check only layers shown as visible in TVPaint.",
            "None": "Uncheck every layer.",
            "Set to Full clip": 'Get the first and last frames of the current clip.',
            "Use top layer": "Use the highest checked layer's name.",
            "Use bottom layer": "Use the lowest checked layer's name.",
            "Browse…": "Choose where the export folder will be created.",
            "Overwrite layers": "Replace the matching sequence images in this Manual session.",
            "Export layers": '',
            "Resume interrupted export…": "Choose an interrupted export folder to verify existing frames and continue.",
            "Check for updates": "Check published GitHub releases and review an update before installing it.",
        }
        self.tooltips.append(Tooltip(widget, explanations.get(text, text)))
        return widget

    def add_tooltips(self):
        for widget, text in (
            (self.combine_check, "Combine all checked layers into one image sequence."),
            (self.flat_check, 'Exports directly in the export folder, without subfolders.'),
            (self.background_check, ''),
            (self.cancel_button, "Stop after the current operation and restore TVPaint's settings."),
            (self.open_button, "Open the latest export folder in Windows Explorer."),
            (self.report_button, "Open the delivery report for the latest export."),
        ):
            self.tooltips.append(Tooltip(widget, text))
        for radio, text in zip(self.colour_name_radios, (
            "Name each sequence after its TVPaint colour group name.",
            "Name each sequence after the nearest universal color, such as Red, Green or Blue.",
            "Name each colour-group sequence after its highest checked layer.",
            "Name each colour-group sequence after its lowest checked layer.",
        )):
            self.tooltips.append(Tooltip(radio, text))

    def start_tutorial(self):
        if self.tutorial and self.tutorial.window.winfo_exists():
            self.tutorial.window.lift()
            return
        self.tutorial = Tutorial(self.root, [
            (self.refresh_button, "Connect to TVPaint", 'Open your project and clip in TVPaint if needed, then click Connect or Refresh. The project name and layer list will update. Refresh again after changing any clip or layers.'),
            (self.mode_buttons["Auto Mode"], "Choose a mode", 'AUTO exports checked layers separately into a new folder. MANUAL keeps a folder for several exports. LAYER COLORS combines layers by their TVPaint colour group. The orange button shows the active mode.'),
            (self.canvas, "Choose layers", 'Check the layers you want to deliver. You can see folders, visible/hidden statuses and layer colors. In LAYER COLORS, group checkboxes select a whole colour group, and individual checkboxes let you refine it.'),
            (self.settings_panel, "Adjust export settings", 'Click an Edit heading to open its settings. Set things like image format, background, frame range or prefixes if needed.'),
            (self.parent_entry, "Choose the output folder", 'Use Browse to choose a writable folder. AUTO and LAYER COLORS create a new dated folder for each export. MANUAL reuses its folder until you change mode.'),
            (self.start_button, "Export", "When you're ready, click Export layers. Leave TVPaint idle while exporting, it will check and uncheck layers before reverting your scene back to its original state."),
            (self.bar, "Follow progress", 'The orange bar counts exported frames. Cancel stops safely after the current operation. Resume interrupted export lets you continue using the original scene and settings.'),
            (self.open_button, "Check your delivery", 'When the export finishes, Open export folder shows your images. Open delivery report shows the layer structure, exported sequences and completion status.'),
        ])

    @staticmethod
    def connection_error_text(text):
        text = re.sub(r"\btvpaint\b", "TVPaint", str(text), flags=re.I)
        return re.sub(r"\s+!", "!", text)

    def settings_section(self, parent, key, title):
        holder = ttk.Frame(parent)
        holder.pack(fill="x", pady=(0, 3))
        toggle = ttk.Button(holder, text="▸  " + title, style="Section.TButton",
                            command=lambda: self.toggle_section(key))
        self.tooltips.append(Tooltip(toggle, {'format': 'Image format and background colour settings.', 'frames': 'Frame range and numbering settings.', 'prefixes': 'Folder / filename prefixes settings.', 'sequence': 'Sequence name settings.', 'colour_naming': 'Sequence naming settings.'}[key]))
        toggle.pack(fill="x")
        content = ttk.Frame(holder, padding=(2, 6, 2, 6))
        self.sections[key] = dict(holder=holder, toggle=toggle, content=content, title=title, opened=False)
        return content

    def toggle_section(self, key):
        item = self.sections[key]
        item["opened"] = not item["opened"]
        self.configure_sections(reset=False)
        self.root.after_idle(self.set_minimum_size)

    def configure_sections(self, reset=True):
        colour = self.mode.get() == "Colour Mode"
        self.settings_panel.configure(padding=0, relief="flat", borderwidth=0)
        self.preview_box.configure(padding=12, relief="solid", borderwidth=1)
        for key, item in self.sections.items():
            if reset:
                item["opened"] = False
            if (key == "sequence" and colour) or (key == "colour_naming" and not colour):
                item["content"].pack_forget()
                item["holder"].pack_forget()
                continue
            item["holder"].pack(fill="x", pady=(0, 3), before=self.preview_box)
            item["toggle"].pack(fill="x", before=item["content"] if item["content"].winfo_manager() else None)
            if item["opened"]:
                item["content"].pack(fill="x")
            else:
                item["content"].pack_forget()
            item["toggle"].configure(text=("▾  " if item["opened"] else "▸  ") + item["title"])
        self.sections["sequence"]["toggle"].configure(state="normal" if self.combine.get() else "disabled")

    def entry(self, parent, variable, width=None):
        widget = ttk.Entry(parent, textvariable=variable, width=width or 25)
        self.controls.append(widget)
        return widget

    def set_busy(self, busy, exporting=False):
        self.busy = busy
        for widget in self.controls:
            widget.configure(state="disabled" if busy else "normal")
        for widget in self.layer_box.winfo_children():
            if isinstance(widget, ttk.Checkbutton):
                widget.configure(state="disabled" if busy else "normal")
        self.cancel_button.configure(state="normal" if exporting else "disabled")
        if not busy:
            self.format_picker.configure(state="readonly")
            self.validate()

    def connect(self):
        if self.busy:
            return
        self.set_busy(True)
        self.connection.set("Checking TVPaint…")
        if self.status.get().startswith("Connection details:"):
            self.status.set("Checking TVPaint…")
        def worker():
            try:
                self.events.put(("connected", TVPaint().inspect()))
            except Exception as exc:
                self.events.put(("connection_error", str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def populate(self, info):
        self.info = info
        self.resume_folder = None
        self.start_button.configure(text="Export layers")
        self.checks.clear()
        for layer in info["layers"]:
            if not layer.get("is_folder"):
                self.checks[layer["id"]] = tk.BooleanVar(value=True)
        if self.mode.get() == "Colour Mode":
            self.colour_defaults()
        self.render_layer_list()
        self.full_range()
        version = " ".join(map(str, info["version"]))
        project = Path(info.get("project_path", "")).name or str(info["project_id"])
        self.connection.set(f"Connected · {version}")
        self.scene.set(f"{project} / {info.get('clip_name', info['clip_id'])}")
        self.update_connection_button()
        self.status.set("")

    def colour_defaults(self):
        for layer in self.info["layers"]:
            if layer["id"] in self.checks:
                self.checks[layer["id"]].set(bool(layer["visible"] and layer.get("colour_index", 0)))

    def swatch(self, layer):
        rgb = layer.get("colour_rgb")
        image = tk.PhotoImage(width=12, height=12)
        image.put("#" + "".join(f"{value:02x}" for value in rgb) if rgb else "#686868", to=(0, 0, 12, 12))
        self.swatches.append(image)
        return image

    def render_layer_list(self):
        self.colour_checks.clear()
        for widget in self.layer_box.winfo_children():
            widget.destroy()
        self.swatches.clear()
        if self.mode.get() == "Colour Mode":
            groups = {}
            for layer in self.info["layers"]:
                if not layer.get("is_folder") and layer.get("colour_index") is not None:
                    groups.setdefault(layer["colour_index"], []).append(layer)
            ttk.Label(self.layer_box, text="Colour groups", style="Muted.TLabel").pack(anchor="w")
            for index, members in groups.items():
                value = tk.BooleanVar()
                name = members[0].get("colour_name") or f"Colour {index}"
                check = ttk.Checkbutton(self.layer_box, text=f"{name} · {len(members)} {'layer' if len(members) == 1 else 'layers'}",
                                       image=self.swatch(members[0]), compound="left", variable=value,
                                       command=lambda key=index: self.select_colour(key))
                check.pack(anchor="w", pady=3)
                check.bind("<MouseWheel>", self.scroll_layers)
                self.colour_checks[index] = (value, check)
            ttk.Separator(self.layer_box).pack(fill="x", pady=8)
            ttk.Label(self.layer_box, text="Layer stack", style="Muted.TLabel").pack(anchor="w")
        for layer in self.info["layers"]:
            if layer.get("is_folder"):
                divider = ttk.Frame(self.layer_box)
                divider.pack(fill="x", pady=(9, 5))
                label = "[" + layer["name"] + "]" + ("  (hidden)" if not layer["visible"] else "")
                ttk.Label(divider, text=label, style="Muted.TLabel", image=self.swatch(layer), compound="left").pack(side="left")
                ttk.Separator(divider, orient="horizontal").pack(side="left", fill="x", expand=True, padx=(8, 0))
                continue
            value = self.checks[layer["id"]]
            label = layer["name"] + ("  (hidden)" if not layer["visible"] else "")
            check = ttk.Checkbutton(self.layer_box, text=label, variable=value, command=self.schedule_check,
                                    image=self.swatch(layer), compound="left")
            check.pack(anchor="w", pady=3)
            check.bind("<MouseWheel>", self.scroll_layers)
        self.sync_colour_checks()

    def select_colour(self, index):
        selected = self.colour_checks[index][0].get()
        for layer in self.info["layers"]:
            if layer["id"] in self.checks and layer.get("colour_index") == index:
                self.checks[layer["id"]].set(selected)
        self.schedule_check()

    def sync_colour_checks(self):
        if not self.info:
            return
        for index, (variable, widget) in self.colour_checks.items():
            states = [self.checks[layer["id"]].get() for layer in self.info["layers"]
                      if layer["id"] in self.checks and layer.get("colour_index") == index]
            variable.set(all(states))
            widget.state(["alternate" if any(states) and not all(states) else "!alternate"])

    def full_range(self):
        if self.info:
            self.first.set(str(self.info["start"]))
            self.last.set(str(self.info["end"]))

    def select(self, mode):
        if self.info:
            for layer in self.info["layers"]:
                if layer["id"] not in self.checks:
                    continue
                available = self.mode.get() != "Colour Mode" or layer.get("colour_index") is not None
                self.checks[layer["id"]].set(available and (mode == "all" or (mode == "visible" and layer["visible"])))
            self.schedule_check()

    def browse(self):
        selected = filedialog.askdirectory(title="Choose output folder", initialdir=self.parent.get() or None)
        if selected:
            self.parent.set(selected)

    def options(self):
        try:
            return Options([key for key, value in self.checks.items() if value.get()],
                           int(self.first.get()), int(self.last.get()), self.prefix.get(),
                           int(self.numbering.get()), int(self.padding.get()), self.image_format.get(), self.background.get(), not self.flat_output.get(),
                           self.combine.get(), self.sequence_name.get() if self.combine.get() else "", self.folder_prefix.get(),
                           self.mode.get() == "Colour Mode",
                           self.colour_naming.get())
        except ValueError:
            raise ValueError("Enter whole numbers for the frame range and filename numbering.") from None

    def schedule_check(self, *_):
        if self.check_job:
            self.root.after_cancel(self.check_job)
        self.check_job = self.root.after(350, self.validate)

    def validate(self):
        self.check_job = None
        self.pending_conflict_key = None
        if self.overwrite_button.winfo_manager():
            self.overwrite_button.pack_forget()
        if self.busy:
            return False
        self.sync_format()
        self.sync_colour_checks()
        self.combine_check.configure(state="disabled" if self.mode.get() == "Colour Mode" else "normal")
        self.sync_sequence_name()
        self.sections["sequence"]["toggle"].configure(state="normal" if self.combine.get() else "disabled")
        for widget in (self.sequence_entry, self.name_reset, self.name_bottom):
            widget.configure(state="normal" if self.combine.get() else "disabled")
        self.sequence_label.configure(style="Muted.TLabel" if self.combine.get() else "Disabled.TLabel")
        self.folder_prefix_entry.configure(state="disabled" if self.flat_output.get() else "normal")
        for widget in (self.parent_entry, self.browse_button):
            widget.configure(state="disabled" if self.session_folder else "normal")
        try:
            if not self.info:
                raise ValueError("Open TVPaint with your scene, then click Connect.")
            if self.mode.get() == "Colour Mode" and not any(
                    layer.get("colour_index") is not None for layer in self.info["layers"] if not layer.get("is_folder")):
                raise ValueError("Colour information is unavailable. Refresh the connection or use Auto Mode.")
            if self.resume_folder:
                self.notice.set("Resume uses the original settings. Previous frames will be checked before continuing.")
                for widget in self.controls:
                    if widget not in (self.refresh_button, *self.mode_buttons.values(), self.start_button, self.resume_button):
                        widget.configure(state="disabled")
                for widget in self.layer_box.winfo_children():
                    if isinstance(widget, ttk.Checkbutton):
                        widget.configure(state="disabled")
                self.start_button.configure(state="normal")
                return True
            destination = self.session_folder or Path(self.parent.get()) / "TVPaint_export_YYYYMMDD_HHMMSS"
            task = plan(self.info, destination, self.options())
            self.preview.set(str(frame_path(Path("<export folder>"), task["layers"][0], task["options"]["first"], task["options"])))
            if not self.parent.get():
                raise ValueError("Choose an output folder.")
            check_writable(self.session_folder or self.parent.get())
            if self.session_folder:
                key = self.collision_key(task)
                conflicts = sequence_conflicts(self.session_folder, task)
                if conflicts and self.overwrite_key != key:
                    if (self.mode.get() == "Manual Mode" and
                            all(path.suffix.casefold() in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".tga", ".bmp"}
                                for path in conflicts)):
                        self.pending_conflict_key = key
                        self.overwrite_button.pack(side="right", padx=(10, 0))
                    check_sequence_conflicts(self.session_folder, task)
                if conflicts and self.overwrite_key == key:
                    task["notices"].insert(0, "The matching sequence will be overwritten; other exports will be kept.")
            ready = f"Ready • {len(task['options']['layer_ids'])} layers • {len(task['layers'])} sequence(s) • {task['total']} {task['options']['image_format']} files"
            self.notice.set("\n".join([ready, *task["notices"][:3]]))
            if self.info.get("colour_warning"):
                self.notice.set(self.notice.get() + "\n" + self.info["colour_warning"])
            self.start_button.configure(state="normal")
            return True
        except (ValueError, OSError) as exc:
            self.notice.set(str(exc))
            self.start_button.configure(state="disabled")
            return False

    def load_resume(self):
        selected = filedialog.askdirectory(title="Choose the interrupted export folder")
        if not selected:
            return
        try:
            data = json.loads((Path(selected) / "export_manifest.json").read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("schema") != 2 or data.get("status") == "complete":
                raise ValueError("Choose an interrupted export folder.")
            options = Options.from_manifest(data["options"])
            if not self.info:
                raise ValueError("Connect to TVPaint first.")
            from export_options import identity
            if data["identity"] != identity(self.info):
                raise ValueError("Connect to the original scene with the same layer list before resuming.")
            task = plan(self.info, selected, options)
            check_writable(selected)
            if options.colour_mode:
                self.choose_mode("Colour Mode")
            elif self.mode.get() == "Colour Mode":
                self.choose_mode("Auto Mode")
            self.resume_folder = Path(selected)
            self.first.set(str(options.first))
            self.last.set(str(options.last))
            self.prefix.set(options.prefix)
            self.folder_prefix.set(options.folder_prefix)
            self.numbering.set(str(options.numbering))
            self.padding.set(str(options.padding))
            self.image_format.set(options.image_format)
            self.background.set(options.background)
            self.flat_output.set(not options.layer_folders)
            self.combine.set(options.combine)
            self.colour_naming.set(options.colour_naming)
            self.name_overridden = True
            self.updating_name = True
            self.sequence_name.set(options.sequence_name)
            self.updating_name = False
            for key, value in self.checks.items():
                value.set(key in options.layer_ids)
            self.last_selection = tuple(key for key, value in self.checks.items() if value.get())
            self.preview.set(str(frame_path(Path("<export folder>"), task["layers"][0], options.first, task["options"])))
            self.start_button.configure(text="Resume export")
            self.status.set("Resume selected. Refresh to return to a new export.")
            # Settings are fixed for a resume, but refresh and resume chooser remain usable.
            self.validate()
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self.notice.set(f"Cannot resume: {exc}")

    def start(self):
        if self.busy or not self.validate():
            return
        options = self.options()
        resume = self.resume_folder is not None
        manual = self.mode.get() == "Manual Mode"
        output = self.resume_folder or self.session_folder or new_output_folder(self.parent.get())
        task = plan(self.info, output, options)
        overwrite = manual and self.session_folder is not None and self.overwrite_key == self.collision_key(task)
        self.destination = output
        self.cancel.clear()
        self.set_busy(True, exporting=True)
        self.bar.configure(value=0)
        self.status.set("Checking the active scene… Keep TVPaint idle during export.")
        self.show_report("")
        self.open_button.configure(state="disabled")
        self.report_button.configure(state="disabled")
        try:
            write_settings(self.preferences())
        except OSError:
            self.notice.set("Preferences could not be saved; this export can still continue.")
        expected = self.info
        def worker():
            try:
                export(TVPaint(), output, self.cancel, options=options, resume=resume, expected=expected,
                       reuse_folder=manual, overwrite=overwrite,
                       on_progress=lambda value: self.events.put(("progress", value)))
                self.events.put(("finished", "Export complete."))
            except Exception as exc:
                self.events.put(("finished", str(exc)))
        threading.Thread(target=worker, daemon=False).start()

    def show_report(self, text):
        self.report_box.configure(state="normal")
        self.report_box.delete("1.0", "end")
        self.report_box.insert("1.0", text)
        self.report_box.configure(state="disabled")

    @staticmethod
    def duration(seconds):
        if seconds is None:
            return "—"
        seconds = int(seconds)
        return f"{seconds // 60}:{seconds % 60:02d}"

    def poll(self):
        try:
            while True:
                kind, data = self.events.get_nowait()
                if kind == "connected":
                    self.populate(data)
                    self.set_busy(False)
                elif kind == "connection_error":
                    self.info = None
                    self.connection.set("Not connected · Open TVPaint and click Connect. If it is already open, restart it.")
                    self.update_connection_button()
                    self.scene.set("")
                    self.status.set("Connection details: " + self.connection_error_text(data))
                    self.set_busy(False)
                elif kind == "progress":
                    self.bar.configure(maximum=data["total"], value=data["completed"])
                    self.counter.set(f"{data['completed']} / {data['total']} frames")
                    self.timing.set(f"Elapsed {self.duration(data['elapsed'])}  ·  Remaining {self.duration(data['remaining'])}")
                    self.status.set(f"{data['phase']} · {data['layer']} · frame {data['frame']}" +
                                    (f" · {data['checked']}/{data['verify_total']} checked" if data['phase'].startswith('Checking') else ""))
                elif kind == "finished":
                    self.overwrite_key = None
                    self.resume_folder = None
                    if self.mode.get() == "Manual Mode" and self.session_folder is None and self.destination and self.destination.is_dir():
                        self.session_folder = self.destination
                        self.session_status.set("Manual session folder: " + str(self.session_folder))
                    self.set_busy(False)
                    self.status.set(data)
                    if self.destination and self.destination.is_dir():
                        self.open_button.configure(state="normal")
                        report_path = self.destination / "Delivery Report.txt"
                        if report_path.is_file():
                            self.show_report(report_path.read_text(encoding="utf-8"))
                            self.report_box.see("end")
                            self.report_button.configure(state="normal")
                    self.start_button.configure(text="Export layers")
                    self.validate()
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def open_folder(self):
        try:
            os.startfile(str(self.destination))
        except OSError as exc:
            self.status.set(f"Could not open folder: {exc}")

    def check_updates(self):
        if self.busy:
            return
        if self.update_window and self.update_window.window.winfo_exists():
            self.update_window.window.lift()
            return
        self.update_window = UpdateWindow(self.root, lambda: not self.busy, self.finish_for_update)

    def finish_for_update(self, launch):
        if self.busy:
            raise RuntimeError("Finish or cancel the current export before updating.")
        write_settings(self.preferences())
        launch()
        self.root.destroy()

    def open_report(self):
        try:
            os.startfile(str(self.destination / "Delivery Report.txt"))
        except OSError as exc:
            self.status.set(f"Could not open report: {exc}")

    def close(self):
        if self.busy:
            self.cancel.set()
            self.status.set("Finishing the current operation and restoring TVPaint. Close again when it has stopped.")
        else:
            try:
                write_settings(self.preferences())
            except OSError:
                pass
            self.root.destroy()

    def preferences(self):
        return {**{k: getattr(self, k).get() for k in ("parent", "prefix", "folder_prefix", "numbering", "padding", "image_format")},
                "background": "1" if self.background.get() else "0", "flat_output": "1" if self.flat_output.get() else "0"}

    def sync_format(self):
        transparent = IMAGE_FORMATS[self.image_format.get()][2]
        if not transparent and not self.background.get():
            self.background.set(True)
        self.background_check.configure(state="normal" if transparent and not self.resume_folder else "disabled")
        if not transparent:
            self.format_note.set(f"{self.image_format.get()} needs a background (TVPaint colour, or white).")
        elif self.background.get():
            self.format_note.set("Uses TVPaint's background colour, or white if none is set.")
        else:
            self.format_note.set("No background · transparent image")

    def mode_changed(self, *_):
        if self.mode.get() == self.active_mode:
            return
        self.active_mode = self.mode.get()
        self.resume_folder = None
        self.session_folder = None
        self.combine.set(self.mode.get() == "Manual Mode")
        if self.mode.get() == "Colour Mode":
            self.combine_check.pack_forget()
        else:
            self.combine_check.pack(side="left", padx=(0, 18), before=self.flat_check)
        self.update_mode_buttons()
        if self.info:
            if self.mode.get() == "Colour Mode":
                self.colour_defaults()
            self.render_layer_list()
        self.overwrite_key = None
        self.name_overridden = False
        self.session_status.set({
            "Manual Mode": "Manual Mode keeps the same folder until you change mode.",
            "Colour Mode": "Color mode creates a sequence per checked colour group",
            "Auto Mode": "Auto Mode creates a new folder for each export.",
        }[self.mode.get()])
        self.start_button.configure(text="Export layers")
        self.configure_sections()
        self.root.after_idle(self.set_minimum_size)
        self.set_busy(False)

    def toggle_mode(self):
        self.mode.set("Manual Mode" if self.mode.get() == "Auto Mode" else "Auto Mode")
        self.mode_changed()

    def choose_mode(self, mode):
        if self.busy:
            return
        self.mode.set(mode)
        self.mode_changed()

    def update_mode_buttons(self):
        for mode, button in self.mode_buttons.items():
            button.configure(style="ActiveMode.TButton" if self.mode.get() == mode else "TButton")

    def update_connection_button(self):
        connected = self.info is not None
        self.refresh_button.configure(text="Refresh" if connected else "Connect")
        for tip in self.tooltips:
            if tip.widget is self.refresh_button:
                tip.text = ("Reload the current clip, layers and colours from TVPaint." if connected else
                            "Connect to TVPaint and load the current clip, layers and colours.")

    def name_edited(self, *_):
        if not self.updating_name:
            self.name_overridden = bool(self.sequence_name.get().strip())
            self.last_selection = tuple(key for key, value in self.checks.items() if value.get())
            self.schedule_check()

    def sync_sequence_name(self):
        if not self.info:
            return
        selection = tuple(key for key, value in self.checks.items() if value.get())
        if selection != self.last_selection:
            self.name_overridden = False
            self.last_selection = selection
        if self.name_overridden:
            return
        name = next((layer["name"] for layer in self.info["layers"] if layer["id"] in self.checks and self.checks[layer["id"]].get()), "")
        if self.sequence_name.get() != name:
            self.updating_name = True
            self.sequence_name.set(name)
            self.updating_name = False

    def reset_sequence_name(self):
        self.name_overridden = False
        self.validate()

    def use_bottom_layer(self):
        if not self.info:
            return
        name = next((layer["name"] for layer in reversed(self.info["layers"])
                     if layer["id"] in self.checks and self.checks[layer["id"]].get()), "")
        self.name_overridden = True
        self.updating_name = True
        self.sequence_name.set(name)
        self.updating_name = False
        self.validate()

    @staticmethod
    def collision_key(task):
        return json.dumps({"options": task["options"],
                           "layers": [(layer["folder"], layer["name"]) for layer in task["layers"]]},
                          sort_keys=True, ensure_ascii=False)

    def approve_overwrite(self):
        if self.mode.get() != "Manual Mode" or not self.pending_conflict_key:
            return
        self.overwrite_key = self.pending_conflict_key
        self.validate()

    def set_minimum_size(self):
        self.root.update_idletasks()
        self.root.minsize(max(880, self.root.winfo_reqwidth()), max(820, self.root.winfo_reqheight()))

    def scroll_layers(self, event):
        if self.canvas.yview() != (0.0, 1.0):
            self.canvas.yview_scroll(-int(event.delta / 120), "units")
        return "break"


def run():
    root = tk.Tk()
    ExporterWindow(root)
    root.mainloop()
