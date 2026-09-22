"""Freelancer-facing v2 interface. All TVPaint work runs off the UI thread."""
from pathlib import Path
import json
import os
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog
from datetime import datetime

from export_options import Options, IMAGE_FORMATS, plan, frame_path, check_writable, read_settings, write_settings, new_output_folder, check_sequence_conflicts, sequence_conflicts
from export_layers import TVPaint, export


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
        self.sequence_name = tk.StringVar()
        self.session_status = tk.StringVar(value="Auto Mode creates a new folder for each export.")
        self.format_note = tk.StringVar()
        self.first = tk.StringVar()
        self.last = tk.StringVar()
        self.connection = tk.StringVar(value="Checking TVPaint…")
        self.scene = tk.StringVar()
        self.preview = tk.StringVar(value="Connect to TVPaint to preview filenames.")
        self.notice = tk.StringVar()
        self.status = tk.StringVar(value="Choose your layers and output folder.")
        self.counter = tk.StringVar(value="0 / 0 frames")
        self.timing = tk.StringVar(value="Elapsed 0:00  ·  Remaining —")
        self.checks = {}
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
        style.configure("Notice.TLabel", foreground=orange)
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
        self.refresh_button = self.button(buttons, "Refresh connection", self.connect)
        self.refresh_button.pack(side="right")
        self.mode_button = self.button(buttons, "Manual Mode", self.toggle_mode)
        self.mode_button.pack(side="right", padx=(0, 8))
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
        ttk.Label(bottom, text="by Fabien Glasse", foreground="#777777", font=("Segoe UI", 10, "italic")).pack(side="right")
        for value in (self.parent, self.prefix, self.folder_prefix, self.numbering, self.padding, self.first, self.last, self.image_format, self.background, self.flat_output, self.combine):
            value.trace_add("write", self.schedule_check)
        self.sequence_name.trace_add("write", self.name_edited)
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(100, self.poll)
        root.after(150, self.connect)
        root.after_idle(self.set_minimum_size)

    def button(self, parent, text, command):
        widget = ttk.Button(parent, text=text, command=command)
        self.controls.append(widget)
        return widget

    def settings_section(self, parent, key, title):
        holder = ttk.Frame(parent)
        holder.pack(fill="x", pady=(0, 3))
        toggle = ttk.Button(holder, text="▸  " + title, style="Section.TButton",
                            command=lambda: self.toggle_section(key))
        toggle.pack(fill="x")
        content = ttk.Frame(holder, padding=(2, 6, 2, 6))
        self.sections[key] = dict(toggle=toggle, content=content, title=title, opened=False)
        return content

    def toggle_section(self, key):
        item = self.sections[key]
        item["opened"] = not item["opened"]
        self.configure_sections(reset=False)
        self.root.after_idle(self.set_minimum_size)

    def configure_sections(self, reset=True):
        manual = self.mode.get() == "Manual Mode"
        self.settings_panel.configure(padding=12 if manual else 0,
                                      relief="solid" if manual else "flat", borderwidth=1 if manual else 0)
        self.preview_box.configure(padding=(0, 12, 0, 0) if manual else 12,
                                   relief="flat" if manual else "solid", borderwidth=0 if manual else 1)
        for item in self.sections.values():
            if reset:
                item["opened"] = manual
            if manual:
                item["toggle"].pack_forget()
            else:
                item["toggle"].pack(fill="x", before=item["content"] if item["content"].winfo_manager() else None)
            if manual or item["opened"]:
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
        for widget in self.layer_box.winfo_children():
            widget.destroy()
        for layer in info["layers"]:
            if layer.get("is_folder"):
                divider = ttk.Frame(self.layer_box)
                divider.pack(fill="x", pady=(9, 5))
                label = "[" + layer["name"] + "]" + ("  (hidden)" if not layer["visible"] else "")
                ttk.Label(divider, text=label, style="Muted.TLabel").pack(side="left")
                ttk.Separator(divider, orient="horizontal").pack(side="left", fill="x", expand=True, padx=(8, 0))
                continue
            value = tk.BooleanVar(value=True)
            self.checks[layer["id"]] = value
            label = layer["name"] + ("  (hidden)" if not layer["visible"] else "")
            check = ttk.Checkbutton(self.layer_box, text=label, variable=value, command=self.schedule_check)
            check.pack(anchor="w", pady=3)
            check.bind("<MouseWheel>", self.scroll_layers)
        self.full_range()
        version = " ".join(map(str, info["version"]))
        project = Path(info.get("project_path", "")).name or str(info["project_id"])
        self.connection.set(f"Connected · {version}")
        self.scene.set(f"{project} / {info.get('clip_name', info['clip_id'])}")

    def full_range(self):
        if self.info:
            self.first.set(str(self.info["start"]))
            self.last.set(str(self.info["end"]))

    def select(self, mode):
        if self.info:
            for layer in self.info["layers"]:
                if layer["id"] not in self.checks:
                    continue
                self.checks[layer["id"]].set(mode == "all" or (mode == "visible" and layer["visible"]))
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
                           self.combine.get(), self.sequence_name.get() if self.combine.get() else "", self.folder_prefix.get())
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
                raise ValueError("Open TVPaint with your scene, then refresh the connection.")
            if self.resume_folder:
                self.notice.set("Resume uses the original settings. Previous frames will be checked before continuing.")
                for widget in self.controls:
                    if widget not in (self.refresh_button, self.mode_button, self.start_button, self.resume_button):
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
            options = Options(**data["options"])
            if not self.info:
                raise ValueError("Connect to TVPaint first.")
            from export_options import identity
            if data["identity"] != identity(self.info):
                raise ValueError("Connect to the original scene with the same layer list before resuming.")
            task = plan(self.info, selected, options)
            check_writable(selected)
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
            self.name_overridden = True
            self.updating_name = True
            self.sequence_name.set(options.sequence_name)
            self.updating_name = False
            for key, value in self.checks.items():
                value.set(key in options.layer_ids)
            self.last_selection = tuple(key for key, value in self.checks.items() if value.get())
            self.preview.set(str(frame_path(Path("<export folder>"), task["layers"][0], options.first, task["options"])))
            self.start_button.configure(text="Resume export")
            self.status.set("Resume selected. Refresh the connection to return to a new export.")
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
                    self.connection.set("Not connected · Open TVPaint and refresh. If it is already open, restart it.")
                    self.scene.set("")
                    self.status.set("Connection details: " + data)
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
        self.mode_button.configure(text="Auto Mode" if self.mode.get() == "Manual Mode" else "Manual Mode")
        self.overwrite_key = None
        self.name_overridden = False
        self.session_status.set("Manual Mode keeps the same folder until you return to Auto Mode."
                                if self.mode.get() == "Manual Mode" else "Auto Mode creates a new folder for each export.")
        self.start_button.configure(text="Export layers")
        self.configure_sections()
        self.root.after_idle(self.set_minimum_size)
        self.set_busy(False)

    def toggle_mode(self):
        self.mode.set("Manual Mode" if self.mode.get() == "Auto Mode" else "Auto Mode")
        self.mode_changed()

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
