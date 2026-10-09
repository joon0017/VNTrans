"""Exercise real desktop capture, in-memory Windows OCR and the GUI lifecycle.

Run from the project root with the project virtual environment's Python.
No API calls or screenshots are saved. The GUI test opens windows briefly.
"""
import ctypes
from ctypes import wintypes
from pathlib import Path
import queue
import sys
import tempfile
import threading
import time
import tkinter as tk
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vntrans_core import Preset, Store, capture_worker
from vntrans import App


def synthetic_image(width=800, height=200, text="Hello visual novel"):
    """Draw ordinary Windows font text to an in-memory GDI bitmap."""
    class Header(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("width", wintypes.LONG), ("height", wintypes.LONG),
                    ("planes", wintypes.WORD), ("bits", wintypes.WORD), ("compression", wintypes.DWORD),
                    ("image_size", wintypes.DWORD), ("xpels", wintypes.LONG), ("ypels", wintypes.LONG),
                    ("used", wintypes.DWORD), ("important", wintypes.DWORD)]
    class Info(ctypes.Structure):
        _fields_ = [("header", Header), ("color", wintypes.DWORD)]
    gdi = ctypes.windll.gdi32
    gdi.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi.CreateCompatibleDC.restype = wintypes.HDC
    gdi.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.POINTER(Info), wintypes.UINT,
                                   ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
    gdi.CreateDIBSection.restype = wintypes.HANDLE
    gdi.SelectObject.argtypes = [wintypes.HDC, wintypes.HANDLE]
    gdi.SelectObject.restype = wintypes.HANDLE
    gdi.DeleteObject.argtypes = [wintypes.HANDLE]
    gdi.DeleteDC.argtypes = [wintypes.HDC]
    gdi.CreateFontW.argtypes = [ctypes.c_int] * 5 + [wintypes.DWORD] * 8 + [wintypes.LPCWSTR]
    gdi.CreateFontW.restype = wintypes.HANDLE
    gdi.SetTextColor.argtypes = [wintypes.HDC, wintypes.DWORD]
    gdi.SetBkColor.argtypes = [wintypes.HDC, wintypes.DWORD]
    gdi.TextOutW.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.LPCWSTR, ctypes.c_int]
    dc = gdi.CreateCompatibleDC(None)
    info = Info(Header(ctypes.sizeof(Header), width, -height, 1, 32, 0, 0, 0, 0, 0, 0), 0)
    pixels = ctypes.c_void_p()
    bitmap = gdi.CreateDIBSection(dc, ctypes.byref(info), 0, ctypes.byref(pixels), None, 0)
    if not bitmap:
        raise ctypes.WinError()
    old = gdi.SelectObject(dc, bitmap)
    font = gdi.CreateFontW(-52, 0, 0, 0, 400, 0, 0, 0, 1, 0, 0, 4, 0, "Meiryo" if any(ord(c) > 127 for c in text) else "Arial")
    old_font = gdi.SelectObject(dc, font)
    try:
        ctypes.memset(pixels, 255, width * height * 4)
        gdi.SetTextColor(dc, 0)
        gdi.SetBkColor(dc, 0xffffff)
        assert gdi.TextOutW(dc, 30, 60, text, len(text))
        gdi.GdiFlush()
        return ctypes.string_at(pixels, width * height * 4)
    finally:
        gdi.SelectObject(dc, old_font)
        gdi.SelectObject(dc, old)
        gdi.DeleteObject(font)
        gdi.DeleteObject(bitmap)
        gdi.DeleteDC(dc)


def worker_check():
    import mss
    with mss.MSS() as screen:
        display = screen.monitors[1]
        shot = screen.grab(dict(left=display["left"], top=display["top"], width=40, height=40))
        assert len(shot.bgra) == 40 * 40 * 4
    print("Real screen capture: passed (pixels not saved or printed)")
    bgra = synthetic_image()
    class Shot:
        pass
    shot = Shot()
    shot.bgra = bgra
    class Screen:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def grab(self, rectangle): return shot
    stop = threading.Event()
    updates = queue.Queue()
    def publish(*result):
        updates.put(result)
    with patch("mss.MSS", return_value=Screen()), patch("vntrans_core.translate", return_value="번역 테스트") as translator:
        thread = threading.Thread(target=capture_worker, args=(Preset(source="en", interval=500), "fake", stop, publish))
        thread.start()
        try:
            deadline = time.monotonic() + 15
            unchanged = False
            while time.monotonic() < deadline:
                text, translation, status = updates.get(timeout=15)
                if "Cannot start" in status or "Retrying" in status:
                    raise AssertionError(status)
                if "unchanged" in status:
                    assert "hello visual novel" in text.lower(), repr(text)
                    assert translation == "번역 테스트"
                    unchanged = True
                    break
            assert unchanged, "No OCR result"
            assert translator.call_count == 1, "Unchanged text was translated repeatedly"
        finally:
            stop.set()
            thread.join(timeout=15)
            assert not thread.is_alive(), "Worker did not stop"
    print("Real Windows OCR, translation handoff, duplicate suppression and shutdown: passed")


def eztrans_check():
    from eztrans_bridge import detect_eztrans, EzTransClient
    directory = detect_eztrans()
    assert directory, "EZTrans XP installation was not found"
    with EzTransClient(directory) as engine:
        for _ in range(2):
            assert "안녕하세요" in engine.translate("こんにちは。")
        assert "\n\n" in engine.translate("こんにちは。\n\nありがとう。")
    assert engine.process.poll() is not None
    bgra = synthetic_image(text="こんにちは。")
    class Shot:
        pass
    shot = Shot()
    shot.bgra = bgra
    class Screen:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def grab(self, rectangle): return shot
    stop, updates = threading.Event(), queue.Queue()
    def publish(*result):
        updates.put(result)
    with patch("mss.MSS", return_value=Screen()), patch("vntrans_core.translate", side_effect=AssertionError("Azure must not be called")):
        thread = threading.Thread(target=capture_worker, args=(Preset(provider="eztrans", eztrans_path=directory, interval=500), "", stop, publish))
        thread.start()
        try:
            for _ in range(10):
                text, translation, status = updates.get(timeout=20)
                if "Cannot start" in status or "Retrying" in status:
                    raise AssertionError(status)
                if translation:
                    assert "こんにちは" in text, ascii(text)
                    assert "안녕하세요" in translation, ascii(translation)
                    break
            else:
                raise AssertionError("No EZTrans OCR translation arrived")
        finally:
            stop.set()
            thread.join(timeout=20)
            assert not thread.is_alive()
    print("Real installed EZTrans: repeated calls, multiline text, OCR-to-translation without Azure, and helper cleanup passed")


def gui_check():
    user = ctypes.windll.user32
    user.GetParent.argtypes = [ctypes.c_void_p]
    user.GetParent.restype = ctypes.c_void_p
    user.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p] + [ctypes.c_int] * 4 + [ctypes.c_uint]
    root = tk.Tk()
    def fake_worker(preset, key, stop, publish):
        publish("Original text", "번역된 텍스트", "Running")
        stop.wait(10)
    with tempfile.TemporaryDirectory() as directory, patch("vntrans.Store", return_value=Store(Path(directory))), patch("vntrans.capture_worker", side_effect=fake_worker):
        app = App(root)
        try:
            root.update()
            app.select_area()
            root.update()
            overlays = [child for child in root.winfo_children() if isinstance(child, tk.Toplevel)]
            assert len(overlays) == 1
            overlays[0].event_generate("<Escape>")
            root.update()
            assert root.state() != "withdrawn"
            app.provider_var.set("EZTrans XP (offline)")
            app.provider_changed()
            assert app.fields["source"].get() == "ja"
            assert app.fields["target"].get() == "ko"
            assert app.key_entry.instate(["disabled"])
            assert app.fields["eztrans_path"].get()
            # Offline mode must start successfully without any Azure key.
            app.key_var.set("")
            app.start()
            assert app.viewer is not None
            deadline = time.monotonic() + 3
            while app.original.get("1.0", "end-1c") != "Original text" and time.monotonic() < deadline:
                root.update()
                time.sleep(0.02)
            assert app.translated.get("1.0", "end-1c") == "번역된 텍스트"
            app.close_viewer()
            while app.viewer is not None and time.monotonic() < deadline:
                root.update()
                time.sleep(0.02)
            assert app.viewer is None
            assert root.state() != "withdrawn"
        finally:
            app.stop.set()
            if app.thread:
                app.thread.join(timeout=2)
            root.destroy()
    print("GUI startup, area selection cancellation, viewer updates and return to settings: passed")


if __name__ == "__main__":
    worker_check()
    eztrans_check()
    gui_check()
