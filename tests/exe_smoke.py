"""Start the packaged app hidden, find its settings window, and close cleanly."""
import ctypes
from ctypes import wintypes
from pathlib import Path
import subprocess
import time

user = ctypes.windll.user32
callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
startup = subprocess.STARTUPINFO()
startup.dwFlags = subprocess.STARTF_USESHOWWINDOW
startup.wShowWindow = 0
exe = Path(__file__).resolve().parents[1] / "dist" / "VNTrans.exe"
found = []
existing = set()

@callback_type
def inspect(hwnd, argument):
    text = ctypes.create_unicode_buffer(256)
    user.GetWindowTextW(hwnd, text, len(text))
    if text.value == "VNTrans — Settings" and hwnd not in existing:
        found.append(hwnd)
    return True

user.EnumWindows(inspect, 0)
existing.update(found)
found.clear()
process = subprocess.Popen([str(exe)], startupinfo=startup)

try:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline and not found:
        user.EnumWindows(inspect, 0)
        if process.poll() is not None:
            raise AssertionError(f"Executable exited before startup: {process.returncode}")
        time.sleep(0.1)
    assert found, "Packaged app did not create its settings window"
    user.PostMessageW(found[0], 0x0010, 0, 0)
    assert process.wait(timeout=10) == 0
    print("Packaged executable starts and closes successfully.")
finally:
    if process.poll() is None:
        process.kill()
        process.wait()

checked = subprocess.run([str(exe), "--check-eztrans"], startupinfo=startup, timeout=40)
assert checked.returncode == 0, f"Packaged EZTrans check failed: {checked.returncode}"
print("Packaged executable calls the real installed EZTrans engine successfully.")
