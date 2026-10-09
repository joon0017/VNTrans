# VNTrans — Python

A Windows visual novel translator written in Python with a Tkinter interface. It captures a selected desktop rectangle, recognizes text locally with Windows OCR, and displays the original text and a translation from Azure or the installed EZTrans XP engine. Screenshots stay in memory and are never saved.

## Offline usage with EZTrans XP
EZTrans XP is a proprietary Japanese-to-Korean translation engine. VNTrans does not include or install it, and does not modify its installation. It must be installed and working on the destination PC for offline translation. 
To use EZTrans XP, select **EZTrans XP (offline)** in the settings, and configure the capture area. The app automatically detects the installation folder; use **Browse…** if it was installed elsewhere. No Azure key or internet connection is required for local translation.


## Run the ready-made application

Double-click **`dist\VNTrans.exe`**. This standalone x64 build includes Python and its dependencies. You do not need to install Python, Visual Studio, or a compiler to run it. It targets Windows 10/11 on x64 computers; other architectures require a separate build on that architecture.

Windows OCR still needs the source language's OCR feature. Azure translation needs a key and internet access; EZTrans XP uses your installed engine offline. The first launch may take a few seconds while the bundled runtime is extracted.

## Run from Python source

1. Install **CPython 3.10–3.14** from [python.org](https://www.python.org/downloads/windows/), including **Tcl/Tk and IDLE** and the **Python launcher**. Python 3.10.6 was used for the verified build.
2. Double-click **`setup.bat`** once. It creates a project-local `.venv`, installs prebuilt packages, and downloads a portable 32-bit Python helper into `runtime32`. No Visual Studio is needed; installation explicitly prohibits compiling dependencies from source. The helper is not installed globally.
3. Double-click **`run.bat`** to open the app.

If you have multiple Python versions and the default is outside the supported range, create the environment with your preferred supported version first, for example:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --only-binary=:all: -r requirements.txt
.\.venv\Scripts\python.exe prepare_eztrans.py
.\.venv\Scripts\python.exe vntrans.py
```

## Configure a game

1. Install the source language's Windows OCR feature in Windows Settings → Time & language → Language & region → language options. Installing a display language alone may not include OCR. An administrator PowerShell can list available capabilities with `Get-WindowsCapability -Online | Where-Object Name -Like 'Language.OCR*'`.
2. Select the **Translation engine**: **Azure Translator (online)** or **EZTrans XP (offline)**.
3. Enter a preset name. For Azure, enter the source language (`ja`, `en`, `ko`, etc.), target language (`ko`, `en`, `zh-Hans`, etc.), Azure key and region. Azure usage follows the resource's pricing and quota. For EZTrans, the app sets Japanese (`ja`) → Korean (`ko`), disables Azure fields, and automatically detects the installation folder. Use **Browse…** if it was installed elsewhere.
4. Open the game in windowed or borderless mode. Click **Select screen area** and drag over the dialogue box. Escape cancels. The coordinates use physical screen pixels; monitors with negative coordinates are supported. You can also enter the rectangle manually.
5. Choose the capture interval in milliseconds: **500–60000**, with **2000** as the default.
6. Click **Save preset**. An existing name is replaced; a new name creates another preset. The dropdown restores settings for each game.
7. Click **시작**. A new window displays the original and translated text. Keep it outside the capture rectangle so the OCR does not read the app's own output. **Always on top** is available for borderless games.
8. Close the translation window to stop capture and return to settings. The interface stays responsive while an active OCR/network request finishes.

Start uses the current settings without requiring a save. The capture interval is a delay after each cycle, so processing time also contributes to the actual interval. Unchanged text skips another translation request. Failed requests are retried with a delay that grows to at most 60 seconds. Windows OCR's spaces between adjacent Japanese characters are removed before translation.

## EZTrans XP setup

On this PC, the app detected **`C:\Program Files (x86)\ChangShinSoft\ezTrans XP`** and successfully called its engine. Select **EZTrans XP (offline)**, configure your capture area, save the preset, and click **시작**. No Azure key or internet connection is required for local translation.

The chosen folder must contain `J2KEngine.dll` and the `Dat` dictionary folder. You need a working installed/activated EZTrans XP. VNTrans does not include or install the proprietary engine or its dictionaries, and does not modify its installation.

EZTrans XP's Japanese-to-Korean engine is 32-bit. A private helper process runs it using the bundled portable Python runtime, allowing the main app to stay 64-bit. Communication uses local pipes; no HTTP server or listening port is opened. The helper is kept alive while the viewer runs, and closed when you stop translation. A stuck translation times out and stops the helper; close the viewer and start again to reload the engine.

For a command-line installation check, run `.\.venv\Scripts\python.exe vntrans.py --check-eztrans`. The packaged executable also accepts `--check-eztrans` and returns exit code 0 on success, or 1 on failure.

## Saved settings and privacy

Presets are stored in `%LOCALAPPDATA%\VNTrans\presets.json`. The API key is saved separately in `key.dat`, encrypted using Windows DPAPI for the current Windows account. The key is shared across presets; each preset has its own translation engine, EZTrans folder, region, languages, area and interval. Click **Save preset** after editing the key to persist it. Old presets default to Azure.

The Python version reads the previous C++ version's preset and key formats. Copying an encrypted key to a different Windows account will not make it readable.

In Azure mode, only recognized text is sent to Azure over HTTPS. In EZTrans mode, recognized text is processed locally. OCR runs locally in both modes. Screenshots and text history are not written to disk. A packaged executable extracts program libraries to a temporary folder when launched; these are application files, not screenshots.

## Build another executable

After running setup, double-click **`build_exe.bat`**. It uses PyInstaller to produce **`dist\VNTrans.exe`**, without Visual Studio. Distribute that executable. Rebuild after changing Python source. Build on the intended Windows architecture with a Python interpreter of that architecture.

Equivalent commands:

```powershell
.\.venv\Scripts\python.exe -m pip install --only-binary=:all: "pyinstaller>=6,<7"
.\.venv\Scripts\python.exe prepare_eztrans.py
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --windowed --name VNTrans --collect-submodules winrt --add-data "runtime32;runtime32" --add-data "eztrans_helper.py;." vntrans.py
```

## Limitations

- OCR accuracy depends on font, contrast, size and layout. Stylized or vertical Japanese text can be read poorly. Text that appears character by character can trigger partial translations.
- Capture reads visible desktop pixels. Covered, minimized, protected or exclusive fullscreen games can produce wrong or black images. Use windowed/borderless mode and keep the dialogue visible.
- Reselect the area after moving the game or changing monitor layout or scaling. Width and height must be 10–4096 pixels and fit the desktop and OCR engine limit.
- EZTrans XP supports Japanese → Korean with the original CP932/CP949 encodings. Symbols its engine cannot represent are replaced. Choose Azure for other language pairs.
- The proprietary EZTrans engine is not bundled; it must be installed and working on the destination PC.

## Verification

Verified on this Windows computer with Python 3.10.6:

- Nine automated tests covering invalid settings and monitor bounds, Unicode and empty-key DPAPI encryption, preset persistence, corrupted settings, Azure UTF-8 requests/responses, rate-limit errors, provider validation and old-preset compatibility.
- Actual desktop capture and actual Windows OCR of an in-memory rendered text image, with a simulated translation response. Verified repeated text triggers one translation request and the worker stops cleanly.
- GUI startup, area-selector cancellation, original/translation pane updates, and return to settings when capture stops.
- Actual installed EZTrans translations, multiline text, repeated calls, helper cleanup, and Japanese OCR → Korean translation without calling Azure.
- EZTrans settings behavior and viewer startup with no Azure key.
- A standalone executable build, followed by launching/closing the packaged settings window and calling the installed EZTrans engine through the packaged helper successfully.

A live Azure translation has not been tested because no Azure key was supplied. Translation response/error handling is tested with simulated responses. Multi-monitor selection at different DPI settings and live game capture still need testing on the intended setup.

Run the tests from the project root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe tests\windows_smoke.py
.\.venv\Scripts\python.exe tests\exe_smoke.py
```

The Windows smoke test briefly opens GUI windows and needs access to an interactive Windows desktop, installed English/Japanese OCR, and EZTrans XP. It makes no translation API calls and saves no screenshots. The executable smoke test requires an existing build and EZTrans installation.

## Files

- `vntrans.py`: Tkinter settings, presets UI, area selection and translation viewer.
- `vntrans_core.py`: configuration, encrypted key storage, OCR worker and translation client.
- `eztrans_bridge.py`, `eztrans_helper.py`: automatic installation detection and the local 32-bit engine bridge.
- `prepare_eztrans.py`: downloads the official portable Python helper runtime.
- `requirements.txt`: prebuilt Python dependencies.
- `setup.bat`, `run.bat`, `build_exe.bat`: install, launch and package scripts.
- `tests/`: automated and Windows integration checks.

## References

- [PyWinRT OCR package and prebuilt wheels](https://pypi.org/project/winrt-Windows.Media.Ocr/)
- [PyWinRT asynchronous API usage](https://pywinrt.readthedocs.io/en/stable/types.html)
- [Azure Translator REST quickstart](https://github.com/MicrosoftDocs/azure-ai-docs/blob/main/articles/ai-services/translator/text-translation/quickstarts/rest-api.md)
- [EZTrans integration API signatures](https://github.com/sokcuri/araltrans02/blob/master/Translator/ezTransXP/ezTransXP.h)
- [Official bundled Python 3.13.16 distribution](https://www.python.org/ftp/python/3.13.16/)
