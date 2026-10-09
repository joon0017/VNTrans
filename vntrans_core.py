"""Configuration, local Windows OCR, Azure and offline EZTrans translation."""
from __future__ import annotations
import asyncio
from contextlib import ExitStack
import ctypes
from ctypes import wintypes
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import re
import threading
import urllib.error
import urllib.parse
import urllib.request


@dataclass
class Preset:
    name: str = "Default"
    source: str = "ja"
    target: str = "ko"
    region: str = ""
    x: int = 0
    y: int = 0
    w: int = 800
    h: int = 200
    interval: int = 2000
    provider: str = "azure"
    eztrans_path: str = ""

    def validate(self, desktop: dict | None = None) -> None:
        if self.provider not in ("azure", "eztrans"):
            raise ValueError("Select Azure Translator or EZTrans XP.")
        if not isinstance(self.eztrans_path, str):
            raise ValueError("Invalid EZTrans installation folder.")
        if not isinstance(self.name, str) or not self.name.strip() or len(self.name) > 120:
            raise ValueError("Enter a preset name (1–120 characters).")
        for label, code in (("OCR language", self.source), ("Target language", self.target)):
            if not isinstance(code, str) or not re.fullmatch(r"[a-zA-Z0-9-]{1,31}", code):
                raise ValueError(f"{label}: use a language code such as ja, ko, en or zh-Hans.")
        if self.provider == "eztrans" and (self.source.lower().split("-")[0] != "ja" or self.target.lower().split("-")[0] != "ko"):
            raise ValueError("EZTrans XP supports Japanese to Korean. Use source ja and target ko.")
        if not isinstance(self.region, str) or (self.provider == "azure" and self.region and not re.fullmatch(r"[a-zA-Z0-9-]{1,64}", self.region)):
            raise ValueError("Enter a valid Azure region, for example eastasia.")
        if any(type(v) is not int for v in (self.x, self.y, self.w, self.h, self.interval)):
            raise ValueError("Coordinates, dimensions and interval must be whole numbers.")
        if not 10 <= self.w <= 4096 or not 10 <= self.h <= 4096:
            raise ValueError("Capture width and height must be 10–4096 pixels.")
        if not 500 <= self.interval <= 60000:
            raise ValueError("Capture interval must be 500–60000 milliseconds.")
        if desktop and (self.x < desktop["left"] or self.y < desktop["top"]
                        or self.x + self.w > desktop["left"] + desktop["width"]
                        or self.y + self.h > desktop["top"] + desktop["height"]):
            raise ValueError("The capture rectangle must fit within the desktop.")

    def rectangle(self) -> dict:
        return dict(left=self.x, top=self.y, width=self.w, height=self.h)


def protect_key(data: bytes, decrypt: bool = False) -> bytes:
    """Current-account DPAPI encryption, compatible with the previous C++ key.dat."""
    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]
    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    result = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p if decrypt else wintypes.LPCWSTR,
                         ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                         wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    if not function(ctypes.byref(source), None if decrypt else "VNTrans Translator key",
                    None, None, None, 1, ctypes.byref(result)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(result.data, result.size)
    finally:
        kernel.LocalFree(ctypes.cast(result.data, ctypes.c_void_p))


class Store:
    def __init__(self, directory: Path | None = None):
        self.directory = directory or Path(os.environ["LOCALAPPDATA"]) / "VNTrans"
        self.directory.mkdir(parents=True, exist_ok=True)

    def load_presets(self) -> list[Preset]:
        path = self.directory / "presets.json"
        if not path.exists():
            return [Preset()]
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError("The presets file must contain a list.")
        presets = [Preset(**entry) for entry in data]
        for preset in presets:
            preset.validate()
        return presets or [Preset()]

    def load_key(self) -> str:
        path = self.directory / "key.dat"
        return protect_key(path.read_bytes(), decrypt=True).decode("utf-8") if path.exists() else ""

    def save(self, presets: list[Preset], key: str) -> None:
        encrypted = protect_key(key.encode("utf-8"))
        self._write("key.dat", encrypted)
        self._write("presets.json", json.dumps([asdict(p) for p in presets],
                    ensure_ascii=False, indent=2).encode("utf-8"))

    def _write(self, name: str, data: bytes) -> None:
        temporary = self.directory / (name + ".tmp")
        temporary.write_bytes(data)
        temporary.replace(self.directory / name)


def translate(text: str, preset: Preset, key: str) -> str:
    query = urllib.parse.urlencode({"api-version": "3.0", "from": preset.source, "to": preset.target})
    headers = {"Content-Type": "application/json; charset=UTF-8", "Ocp-Apim-Subscription-Key": key}
    if preset.region:
        headers["Ocp-Apim-Subscription-Region"] = preset.region
    request = urllib.request.Request("https://api.cognitive.microsofttranslator.com/translate?" + query,
        json.dumps([{"Text": text}], ensure_ascii=False).encode("utf-8"), headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            body = response.read(1024 * 1024 + 1)
            if len(body) > 1024 * 1024:
                raise RuntimeError("Translation response is too large.")
        return json.loads(body)[0]["translations"][0]["text"]
    except urllib.error.HTTPError as exc:
        advice = {401: "Check your Azure key and region.", 403: "Check access and subscription quota.",
                  429: "Quota or rate limit reached. Increase the interval."}.get(exc.code, "Check language codes and Azure settings.")
        raise RuntimeError(f"Translator HTTP {exc.code}. {advice}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError("Translation connection failed or timed out. Check internet access.") from exc


def capture_worker(preset: Preset, key: str, stop: threading.Event, publish) -> None:
    """All screen capture, OCR and HTTP work happens off the Tk thread."""
    initialized = False
    try:
        from winrt.runtime import ApartmentType, init_apartment, uninit_apartment
        init_apartment(ApartmentType.MULTI_THREADED)
        initialized = True
        asyncio.run(_capture_loop(preset, key, stop, publish))
    except Exception as exc:
        publish("", "", f"Cannot start translation: {exc}")
    finally:
        if initialized:
            uninit_apartment()


async def _capture_loop(preset: Preset, key: str, stop: threading.Event, publish) -> None:
    import mss
    from winrt.windows.globalization import Language
    from winrt.windows.graphics.imaging import BitmapAlphaMode, BitmapPixelFormat, SoftwareBitmap
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.storage.streams import DataWriter
    engine = OcrEngine.try_create_from_language(Language(preset.source))
    if engine is None:
        raise RuntimeError("Source language OCR is not installed. Install its Windows OCR language feature.")
    if max(preset.w, preset.h) > OcrEngine.max_image_dimension:
        raise ValueError(f"Windows OCR allows at most {OcrEngine.max_image_dimension} pixels per side.")
    last_text = last_translation = ""
    failures = 0
    with ExitStack() as resources, mss.MSS() as screen:
        local = None
        if preset.provider == "eztrans":
            from eztrans_bridge import EzTransClient
            local = resources.enter_context(EzTransClient(preset.eztrans_path))
        while not stop.is_set():
            text = ""
            try:
                shot = screen.grab(preset.rectangle())
                writer = DataWriter()
                writer.write_bytes(shot.bgra)
                bitmap = SoftwareBitmap(BitmapPixelFormat.BGRA8, preset.w, preset.h, BitmapAlphaMode.IGNORE)
                try:
                    bitmap.copy_from_buffer(writer.detach_buffer())
                    result = await engine.recognize_async(bitmap)
                    text = "\n".join(line.text for line in result.lines).strip()
                    if preset.source.lower().split("-")[0] == "ja":
                        # Windows OCR separates Japanese character tokens with spaces.
                        # Rejoin adjacent Japanese characters before translation.
                        japanese = r"\u3000-\u30ff\u3400-\u9fff\uff00-\uffef"
                        text = re.sub(fr"(?<=[{japanese}])[ \t]+(?=[{japanese}])", "", text)
                finally:
                    bitmap.close()
                    writer.close()
                    del shot
                if stop.is_set():
                    return
                if not text:
                    last_text = last_translation = ""
                    publish("", "", "No text detected. Waiting for dialogue…")
                elif text != last_text:
                    publish(text, "", "Translating…")
                    last_translation = local.translate(text) if local is not None else translate(text, preset, key)
                    last_text = text
                    if not stop.is_set():
                        publish(text, last_translation, "Running — waiting for new dialogue.")
                else:
                    publish(text, last_translation, "Running — unchanged text skips translation.")
                failures = 0
            except Exception as exc:
                failures += 1
                publish(text, "", f"{exc} Retrying…")
            delay = min(60, preset.interval / 1000 * 2 ** min(failures, 5))
            if stop.wait(delay):
                return
