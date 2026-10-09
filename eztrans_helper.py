"""Private 32-bit stdlib-only process hosting the installed EZTrans XP DLL.

One JSON request/response per UTF-8 line over anonymous pipes. No network or
on-disk text. The DLL, dictionaries and licensing remain in their installation.
API signatures: https://github.com/sokcuri/araltrans02/blob/master/Translator/ezTransXP/ezTransXP.h
"""
import ctypes
import json
import os
from pathlib import Path
import sys


class Engine:
    def __init__(self, directory):
        if ctypes.sizeof(ctypes.c_void_p) != 4:
            raise RuntimeError("EZTrans XP needs the bundled 32-bit helper runtime.")
        self.directory = Path(directory).resolve()
        if not (self.directory / "J2KEngine.dll").is_file() or not (self.directory / "Dat").is_dir():
            raise RuntimeError("Select the EZTrans XP installation folder containing J2KEngine.dll and Dat.")
        self.dll_directory = os.add_dll_directory(str(self.directory))
        self.library = ctypes.WinDLL(str(self.directory / "J2KEngine.dll"))
        self.library.J2K_InitializeEx.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
        self.library.J2K_InitializeEx.restype = ctypes.c_int
        self.library.J2K_TranslateMMNT.argtypes = [ctypes.c_int, ctypes.c_char_p]
        self.library.J2K_TranslateMMNT.restype = ctypes.c_void_p
        self.library.J2K_FreeMem.argtypes = [ctypes.c_void_p]
        self.library.J2K_FreeMem.restype = ctypes.c_int
        self.library.J2K_Terminate.argtypes = []
        self.library.J2K_Terminate.restype = ctypes.c_int
        # This is the engine's initialization identifier, not a license key.
        if not self.library.J2K_InitializeEx(b"CSUSER123455", str(self.directory / "Dat").encode("mbcs")):
            raise RuntimeError("EZTrans initialization failed. Check the installation and activation in EZTrans XP.")

    def translate(self, text):
        if not isinstance(text, str) or len(text) > 50000:
            raise ValueError("Invalid or excessively long translation text.")
        output = []
        for line in text.replace("\r\n", "\n").split("\n"):
            if not line.strip():
                output.append("")
                continue
            # The original engine takes CP932 Japanese and returns CP949 Korean.
            # Replace unrepresentable symbols rather than failing on an OCR emoji.
            data = line.replace("\x00", "").encode("cp932", errors="replace")
            pointer = self.library.J2K_TranslateMMNT(0, data)
            if not pointer:
                raise RuntimeError("EZTrans returned no translation.")
            try:
                output.append(ctypes.string_at(pointer).decode("cp949", errors="replace"))
            finally:
                self.library.J2K_FreeMem(pointer)
        return "\n".join(output)

    def close(self):
        self.library.J2K_Terminate()
        self.dll_directory.close()


def send(response):
    sys.stdout.write(json.dumps(response, ensure_ascii=True) + "\n")
    sys.stdout.flush()


def main():
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    # A DLL error must not display a modal Windows crash dialog behind the app.
    ctypes.windll.kernel32.SetErrorMode(0x0001 | 0x0002 | 0x8000)
    engine = None
    try:
        engine = Engine(sys.argv[1])
        send({"ready": True})
        for line in sys.stdin:
            try:
                request = json.loads(line)
                if request.get("close"):
                    break
                send({"translation": engine.translate(request["text"])})
            except Exception as exc:
                send({"error": str(exc)})
    except Exception as exc:
        send({"error": str(exc)})
    finally:
        if engine is not None:
            engine.close()


if __name__ == "__main__":
    main()
