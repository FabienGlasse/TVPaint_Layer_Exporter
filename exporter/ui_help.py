"""Small hover explanations and a contextual tour using Tk only."""
import tkinter as tk
from tkinter import ttk


class Tooltip:
    def __init__(self, widget, text):
        self.widget, self.text = widget, text
        self.job = self.window = None
        widget.bind("<Enter>", self.schedule, add="+")
        widget.bind("<Leave>", self.hide, add="+")
        widget.bind("<ButtonPress>", self.hide, add="+")
        widget.bind("<FocusIn>", self.schedule, add="+")
        widget.bind("<FocusOut>", self.hide, add="+")
        widget.bind("<Destroy>", self.hide, add="+")

    def schedule(self, *_):
        self.hide()
        self.job = self.widget.after(550, self.show)

    def show(self):
        self.job = None
        if not self.text or not self.widget.winfo_exists() or not self.widget.winfo_ismapped():
            return
        self.window = tk.Toplevel(self.widget)
        self.window.withdraw()
        self.window.overrideredirect(True)
        tk.Label(self.window, text=self.text, wraplength=310, justify="left",
                 background="#303030", foreground="#ffffff", relief="solid",
                 borderwidth=1, padx=10, pady=7).pack()
        position_popup(self.window, self.widget)
        self.window.deiconify()

    def hide(self, *_):
        if self.job is not None:
            self.widget.after_cancel(self.job)
            self.job = None
        if self.window is not None:
            self.window.destroy()
            self.window = None


def position_popup(window, target):
    window.update_idletasks()
    width, height = window.winfo_reqwidth(), window.winfo_reqheight()
    # Keep contextual windows inside the application, including on a second monitor.
    root = target.winfo_toplevel()
    left, top = root.winfo_rootx(), root.winfo_rooty()
    right, bottom = left + root.winfo_width(), top + root.winfo_height()
    x = max(left, min(target.winfo_rootx(), right - width))
    y = target.winfo_rooty() + target.winfo_height() + 6
    if y + height > bottom:
        y = max(top, target.winfo_rooty() - height - 6)
    window.geometry(f"+{x}+{y}")


class Tutorial:
    def __init__(self, root, steps):
        self.root, self.steps, self.index = root, steps, 0
        self.window = tk.Toplevel(root)
        self.window.withdraw()
        self.window.title("Exporter tutorial")
        self.window.configure(background="#3c3c3c")
        self.window.transient(root)
        self.window.resizable(False, False)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Escape>", lambda event: self.close())
        box = ttk.Frame(self.window, padding=16)
        box.pack(fill="both", expand=True)
        self.heading = ttk.Label(box, foreground="#ff9933", font=("Segoe UI", 11, "bold"))
        self.heading.pack(anchor="w")
        self.body = ttk.Label(box, wraplength=350, justify="left")
        self.body.pack(anchor="w", pady=(10, 14))
        buttons = ttk.Frame(box)
        buttons.pack(fill="x")
        self.back = ttk.Button(buttons, text="Back", command=lambda: self.move(-1))
        self.back.pack(side="left")
        self.next = ttk.Button(buttons, command=lambda: self.move(1))
        self.next.pack(side="left", padx=6)
        self.show()
        self.window.deiconify()

    def show(self):
        target, title, text = self.steps[self.index]
        self.heading.configure(text=f"{self.index + 1} / {len(self.steps)}  {title}")
        self.body.configure(text=text)
        self.back.configure(state="normal" if self.index else "disabled")
        self.next.configure(text="Finish" if self.index == len(self.steps)-1 else "Next")
        position_popup(self.window, target)
        self.window.lift()

    def move(self, delta):
        self.index = max(0, self.index + delta)
        if self.index >= len(self.steps):
            self.close()
        else:
            self.show()

    def close(self):
        self.window.destroy()
