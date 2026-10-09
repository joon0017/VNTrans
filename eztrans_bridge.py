"""EZTrans discovery and a private persistent 32-bit helper process."""
from __future__ import annotations
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading


def detect_eztrans() -> str:
    candidates = []
    try:
        import winreg
        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for view in (winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY):
                for subkey in (r"SOFTWARE\ChangShin\ezTrans", r"SOFTWARE\ChangShinSoft\ezTrans"):
                    try:
                        with winreg.OpenKey(root, subkey, 0, winreg.KEY_READ | view) as key:
                            for name in ("FileName", "InstallPath", "InstallLocation"):
                                try:
                                    value, _ = winreg.QueryValueEx(key, name)
                                    path = Path(value)
                                    candidates.append(path.parent if path.suffix.lower() == ".exe" else path)
                                except OSError:
                                    pass
                    except OSError:
                        pass
    except ImportError:
        pass
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"), "C:/Program Files (x86)", "C:/Program Files"):
        if base:
            candidates.extend((Path(base) / "ChangShinSoft" / "ezTrans XP", Path(base) / "ezTrans XP"))
    for path in candidates:
        if (path / "J2KEngine.dll").is_file() and (path / "Dat").is_dir():
            return str(path)
    return ""


class EzTransClient:
    def __init__(self, directory: str):
        directory = directory or detect_eztrans()
        if not directory or not (Path(directory) / "J2KEngine.dll").is_file():
            raise ValueError("EZTrans XP was not found. Browse to its installation folder in settings.")
        base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
        runtime, script = base / "runtime32" / "python.exe", base / "eztrans_helper.py"
        if not runtime.is_file() or not script.is_file():
            raise RuntimeError("EZTrans helper is missing. Run setup.bat, or use the latest VNTrans.exe.")
        environment = os.environ.copy()
        # The helper is a different program, not a child copy of the PyInstaller app.
        for name in tuple(environment):
            if name.startswith("_PYI") or name in ("_MEIPASS2", "PYTHONHOME", "PYTHONPATH"):
                environment.pop(name, None)
        self.process = subprocess.Popen([str(runtime), "-I", str(script), str(Path(directory).resolve())],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            encoding="utf-8", bufsize=1, creationflags=subprocess.CREATE_NO_WINDOW,
            cwd=str(runtime.parent), env=environment)
        self.responses = queue.Queue()
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()
        try:
            if not self._response(20).get("ready"):
                raise RuntimeError("EZTrans did not initialize.")
        except Exception:
            self.close()
            raise

    def _read(self):
        try:
            for line in self.process.stdout:
                try:
                    self.responses.put(json.loads(line))
                except ValueError:
                    self.responses.put({"error": "Unexpected response from EZTrans helper."})
        finally:
            self.responses.put({"error": "EZTrans helper exited. Check the installation and activation."})

    def _response(self, timeout):
        try:
            result = self.responses.get(timeout=timeout)
        except queue.Empty:
            self.close()
            raise RuntimeError("EZTrans timed out. Restart translation to reload its engine.") from None
        if "error" in result:
            raise RuntimeError(result["error"])
        return result

    def translate(self, text: str) -> str:
        if self.process.poll() is not None:
            raise RuntimeError("EZTrans helper stopped. Close the viewer and start again.")
        try:
            self.process.stdin.write(json.dumps({"text": text}, ensure_ascii=True) + "\n")
            self.process.stdin.flush()
        except (BrokenPipeError, OSError, ValueError):
            raise RuntimeError("EZTrans helper stopped. Close the viewer and start again.") from None
        return self._response(15)["translation"]

    def close(self):
        if self.process.poll() is None:
            try:
                self.process.stdin.write('{"close": true}\n')
                self.process.stdin.flush()
                self.process.stdin.close()
                self.process.wait(timeout=2)
            except (OSError, ValueError, subprocess.TimeoutExpired):
                self.process.kill()
                self.process.wait(timeout=2)
        self.reader.join(timeout=2)
        self.process.stdout.close()
        if not self.process.stdin.closed:
            self.process.stdin.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
