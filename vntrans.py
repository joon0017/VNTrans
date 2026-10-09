"""VNTrans Windows desktop application (Tkinter)."""
from __future__ import annotations
import ctypes
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from vntrans_core import Preset, Store, capture_worker
from eztrans_bridge import detect_eztrans

PROVIDERS = {"Azure Translator (online)": "azure", "EZTrans XP (offline)": "eztrans"}


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("VNTrans — Settings")
        root.resizable(False, False)
        self.store = Store()
        self.saved, self.key = [Preset()], ""
        warnings = []
        try:
            self.saved = self.store.load_presets()
        except Exception as exc:
            warnings.append(f"Could not load presets: {exc}")
        try:
            self.key = self.store.load_key()
        except Exception as exc:
            warnings.append(f"Could not load saved API key: {exc}")
        self.thread = None
        self.stop = threading.Event()
        self.updates = queue.Queue(maxsize=1)
        self.viewer = None
        self.closing = self.quitting = False
        frame = ttk.Frame(root, padding=20)
        frame.grid(sticky="nsew")
        ttk.Label(frame, text="Welcome to VNTrans / 비주얼 노벨 번역기", font=("Segoe UI", 14)).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))
        ttk.Label(frame, text="Choose a game preset and the dialogue area to translate.").grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 12))
        self.combo = ttk.Combobox(frame, state="readonly", width=52)
        self.combo.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        self.combo.bind("<<ComboboxSelected>>", self.choose)
        self.detected_eztrans = detect_eztrans()
        self.provider_var = tk.StringVar(value="Azure Translator (online)")
        ttk.Label(frame, text="Translation engine").grid(row=3, column=0, sticky="w", pady=5)
        provider = ttk.Combobox(frame, textvariable=self.provider_var, values=list(PROVIDERS), state="readonly")
        provider.grid(row=3, column=1, sticky="ew", pady=5)
        provider.bind("<<ComboboxSelected>>", lambda event: self.provider_changed())
        self.fields = {}
        self.entries = {}
        labels = [("name", "Preset name"), ("source", "OCR language (ja, en, ko…)"),
                  ("target", "Translate to (ko, en…)"), ("x", "Screen X (pixels)"),
                  ("y", "Screen Y (pixels)"), ("w", "Width (pixels)"), ("h", "Height (pixels)"),
                  ("interval", "Capture interval (milliseconds)"), ("region", "Azure Translator region")]
        for row, (name, label) in enumerate(labels, 4):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=5, padx=(0, 15))
            self.fields[name] = tk.StringVar()
            entry = ttk.Entry(frame, textvariable=self.fields[name], width=30)
            entry.grid(row=row, column=1, sticky="ew", pady=5)
            self.entries[name] = entry
        self.key_var = tk.StringVar(value=self.key)
        ttk.Label(frame, text="Azure Translator key").grid(row=13, column=0, sticky="w", pady=5)
        self.key_entry = ttk.Entry(frame, textvariable=self.key_var, show="•")
        self.key_entry.grid(row=13, column=1, sticky="ew", pady=5)
        self.fields["eztrans_path"] = tk.StringVar()
        ttk.Label(frame, text="EZTrans XP folder").grid(row=14, column=0, sticky="w", pady=5)
        folder = ttk.Frame(frame)
        folder.grid(row=14, column=1, sticky="ew", pady=5)
        folder.columnconfigure(0, weight=1)
        self.eztrans_entry = ttk.Entry(folder, textvariable=self.fields["eztrans_path"])
        self.eztrans_entry.grid(row=0, column=0, sticky="ew")
        self.browse_button = ttk.Button(folder, text="Browse…", command=self.browse_eztrans)
        self.browse_button.grid(row=0, column=1, padx=(5, 0))
        buttons = ttk.Frame(frame)
        buttons.grid(row=15, column=0, columnspan=2, sticky="ew", pady=12)
        for label, command in (("Select screen area", self.select_area), ("Save preset", self.save), ("Delete preset", self.delete)):
            ttk.Button(buttons, text=label, command=command).pack(side="left", padx=(0, 8))
        self.provider_note = tk.StringVar()
        ttk.Label(frame, textvariable=self.provider_note).grid(row=16, column=0, columnspan=2, sticky="w", pady=(0, 12))
        ttk.Button(frame, text="시작", command=self.start).grid(row=17, column=1, sticky="e", ipadx=30, ipady=5)
        self.refresh(0)
        root.protocol("WM_DELETE_WINDOW", self.quit)
        root.after(100, self.poll)
        if warnings:
            root.after_idle(lambda: messagebox.showwarning("Saved settings", "\n\n".join(warnings), parent=root))

    def refresh(self, index):
        self.combo["values"] = [p.name for p in self.saved]
        self.combo.current(index)
        self.choose()

    def choose(self, event=None):
        preset = self.saved[self.combo.current()]
        for name, variable in self.fields.items():
            variable.set(str(getattr(preset, name)))
        if not preset.eztrans_path:
            self.fields["eztrans_path"].set(self.detected_eztrans)
        self.provider_var.set(next(label for label, value in PROVIDERS.items() if value == preset.provider))
        self.provider_changed()

    def provider_changed(self):
        local = PROVIDERS[self.provider_var.get()] == "eztrans"
        for widget in (self.entries["region"], self.key_entry):
            widget.configure(state="disabled" if local else "normal")
        for widget in (self.eztrans_entry, self.browse_button):
            widget.configure(state="normal" if local else "disabled")
        for name in ("source", "target"):
            self.entries[name].configure(state="disabled" if local else "normal")
        if local:
            self.fields["source"].set("ja")
            self.fields["target"].set("ko")
            self.provider_note.set("EZTrans XP: offline Japanese → Korean. No Azure key needed.\nKeep the translation window outside the capture rectangle.")
        else:
            self.provider_note.set("OCR runs locally. Recognized text is sent to Azure.\nKeep the translation window outside the capture rectangle.")

    def browse_eztrans(self):
        folder = filedialog.askdirectory(title="Choose EZTrans XP installation folder", parent=self.root,
                                         initialdir=self.fields["eztrans_path"].get() or None)
        if folder:
            self.fields["eztrans_path"].set(folder)

    def read(self):
        import mss
        values = {name: var.get().strip() for name, var in self.fields.items()}
        values["provider"] = PROVIDERS[self.provider_var.get()]
        try:
            for name in ("x", "y", "w", "h", "interval"):
                values[name] = int(values[name])
        except ValueError:
            raise ValueError("Coordinates, dimensions and interval must be whole numbers.") from None
        preset = Preset(**values)
        with mss.MSS() as screen:
            preset.validate(screen.monitors[0])
        key = self.key_var.get().strip()
        if preset.provider == "azure" and (len(key) > 512 or "\r" in key or "\n" in key):
            raise ValueError("Invalid Azure API key.")
        return preset, key

    def save(self):
        try:
            preset, key = self.read()
            updated = list(self.saved)
            index = next((i for i, p in enumerate(updated) if p.name == preset.name), len(updated))
            if index == len(updated):
                updated.append(preset)
            else:
                updated[index] = preset
            self.store.save(updated, key)
            self.saved = updated
            self.refresh(index)
            messagebox.showinfo("VNTrans", "Preset saved.", parent=self.root)
        except Exception as exc:
            messagebox.showerror("Cannot save preset", str(exc), parent=self.root)

    def delete(self):
        try:
            updated = list(self.saved)
            del updated[self.combo.current()]
            updated = updated or [Preset()]
            self.store.save(updated, self.key_var.get().strip())
            self.saved = updated
            self.refresh(0)
        except Exception as exc:
            messagebox.showerror("Cannot delete preset", str(exc), parent=self.root)

    def select_area(self):
        try:
            import mss
            with mss.MSS() as screen:
                desktop = screen.monitors[0]
            self.root.withdraw()
            overlay = tk.Toplevel(self.root)
            overlay.overrideredirect(True)
            overlay.attributes("-topmost", True)
            overlay.attributes("-alpha", 0.4)
            overlay.geometry(f'{desktop["width"]}x{desktop["height"]}+0+0')
            overlay.update_idletasks()
            # Tk negative geometry offsets are distances from screen edges;
            # use Win32 to position at physical virtual-desktop coordinates.
            hwnd = ctypes.windll.user32.GetParent(overlay.winfo_id())
            ctypes.windll.user32.SetWindowPos(hwnd, ctypes.c_void_p(-1), desktop["left"], desktop["top"], desktop["width"], desktop["height"], 0x0040)
            canvas = tk.Canvas(overlay, background="#182030", cursor="crosshair", highlightthickness=0)
            canvas.pack(fill="both", expand=True)
            canvas.create_text(30, 30, anchor="nw", fill="white", text="Drag over the dialogue area. Escape cancels.", font=("Segoe UI", 18))
            origin, rectangle = [], [None]

            def close():
                overlay.destroy()
                self.root.deiconify()
                self.root.lift()

            def press(event):
                origin[:] = [event.x_root, event.y_root]
                if rectangle[0] is not None:
                    canvas.delete(rectangle[0])
                rectangle[0] = canvas.create_rectangle(event.x, event.y, event.x, event.y, outline="#00ffff", width=3)

            def drag(event):
                if origin:
                    canvas.coords(rectangle[0], origin[0] - desktop["left"], origin[1] - desktop["top"], event.x_root - desktop["left"], event.y_root - desktop["top"])

            def release(event):
                if origin:
                    x, y = min(origin[0], event.x_root), min(origin[1], event.y_root)
                    w, h = abs(event.x_root - origin[0]), abs(event.y_root - origin[1])
                    if w >= 10 and h >= 10:
                        for name, number in zip(("x", "y", "w", "h"), (x, y, w, h)):
                            self.fields[name].set(str(number))
                        close()

            canvas.bind("<ButtonPress-1>", press)
            canvas.bind("<B1-Motion>", drag)
            canvas.bind("<ButtonRelease-1>", release)
            overlay.bind("<Escape>", lambda event: close())
            overlay.focus_force()
        except Exception as exc:
            if "overlay" in locals():
                overlay.destroy()
            self.root.deiconify()
            messagebox.showerror("Cannot select area", str(exc), parent=self.root)

    def start(self):
        try:
            preset, key = self.read()
            if preset.provider == "azure" and not key:
                raise ValueError("Enter an Azure Translator key to start.")
            if self.thread and self.thread.is_alive():
                return
            self.stop.clear()
            self.closing = False
            while not self.updates.empty():
                self.updates.get_nowait()
            self.viewer = tk.Toplevel(self.root)
            self.viewer.title(f"VNTrans — {preset.name}")
            self.viewer.geometry("740x590")
            self.viewer.minsize(450, 360)
            self.viewer.columnconfigure(0, weight=1)
            for row in (1, 3):
                self.viewer.rowconfigure(row, weight=1)
            ttk.Label(self.viewer, text="Original / 원문").grid(row=0, column=0, sticky="w", padx=16, pady=(12, 4))
            self.original = ScrolledText(self.viewer, height=8, wrap="word", font=("Segoe UI", 12), state="disabled")
            self.original.grid(row=1, column=0, sticky="nsew", padx=16)
            ttk.Label(self.viewer, text="Translation / 번역").grid(row=2, column=0, sticky="w", padx=16, pady=(12, 4))
            self.translated = ScrolledText(self.viewer, height=8, wrap="word", font=("Segoe UI", 12), state="disabled")
            self.translated.grid(row=3, column=0, sticky="nsew", padx=16)
            self.state = tk.StringVar(value="Starting OCR…")
            ttk.Label(self.viewer, textvariable=self.state, wraplength=680).grid(row=4, column=0, sticky="w", padx=16, pady=10)
            on_top = tk.BooleanVar(value=False)
            ttk.Checkbutton(self.viewer, text="Always on top", variable=on_top, command=lambda: self.viewer.attributes("-topmost", on_top.get())).grid(row=5, column=0, sticky="w", padx=16, pady=(0, 12))
            self.viewer.protocol("WM_DELETE_WINDOW", self.close_viewer)
            self.root.withdraw()
            self.thread = threading.Thread(target=capture_worker, args=(preset, key, self.stop, self.publish), daemon=True)
            self.thread.start()
        except Exception as exc:
            if self.viewer:
                self.viewer.destroy()
                self.viewer = None
            self.root.deiconify()
            messagebox.showerror("Cannot start", str(exc), parent=self.root)

    def publish(self, text, translation, state):
        if self.stop.is_set():
            return
        try:
            self.updates.put_nowait((text, translation, state))
        except queue.Full:
            try:
                self.updates.get_nowait()
            except queue.Empty:
                pass
            self.updates.put_nowait((text, translation, state))

    @staticmethod
    def set_text(widget, text):
        if widget.get("1.0", "end-1c") == text:
            return
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    def poll(self):
        try:
            text, translation, state = self.updates.get_nowait()
            if self.viewer and not self.closing:
                self.set_text(self.original, text)
                self.set_text(self.translated, translation)
                self.state.set(state)
        except queue.Empty:
            pass
        if self.closing and (not self.thread or not self.thread.is_alive()):
            if self.viewer:
                self.viewer.destroy()
                self.viewer = None
            self.thread = None
            self.closing = False
            if self.quitting:
                self.root.destroy()
                return
            self.root.deiconify()
            self.root.lift()
        self.root.after(100, self.poll)

    def close_viewer(self):
        self.closing = True
        self.stop.set()
        if self.viewer:
            self.state.set("Stopping — waiting for the current request to finish…")

    def quit(self):
        if self.thread and self.thread.is_alive():
            self.quitting = True
            self.close_viewer()
        else:
            self.root.destroy()


def main():
    if sys.platform != "win32":
        raise SystemExit("VNTrans requires Windows 10/11.")
    if sys.argv[1:] == ["--check-eztrans"]:
        # A diagnostic usable from Python or the packaged executable.
        from eztrans_bridge import EzTransClient
        try:
            with EzTransClient(detect_eztrans()) as engine:
                result = engine.translate("こんにちは。")
                if not result.strip():
                    raise RuntimeError("EZTrans returned an empty translation.")
                if sys.stdout is not None:
                    print(result)
        except Exception as exc:
            if sys.stderr is not None:
                print(str(exc), file=sys.stderr)
            raise SystemExit(1)
        return
    user32 = ctypes.windll.user32
    user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    user32.GetParent.argtypes = [ctypes.c_void_p]
    user32.GetParent.restype = ctypes.c_void_p
    user32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    root = tk.Tk()
    try:
        import mss
        import winrt.windows.media.ocr
        App(root)
    except Exception as exc:
        messagebox.showerror("VNTrans setup", f"{exc}\n\nRun setup.bat to install the required Python packages.", parent=root)
        root.destroy()
        return
    root.mainloop()


if __name__ == "__main__":
    main()
