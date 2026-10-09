"""Fetch an isolated, compiler-free 32-bit Python runtime for the EZTrans helper."""
import io
from pathlib import Path
import urllib.request
import zipfile

VERSION = "3.13.16"
URL = f"https://www.python.org/ftp/python/{VERSION}/python-{VERSION}-embed-win32.zip"


def main():
    directory = Path(__file__).resolve().parent / "runtime32"
    if (directory / "python.exe").exists():
        print("32-bit EZTrans helper runtime is ready.")
        return
    print(f"Downloading the official Python {VERSION} 32-bit embedded runtime...")
    with urllib.request.urlopen(URL, timeout=60) as response:
        content = response.read(30 * 1024 * 1024 + 1)
    if len(content) > 30 * 1024 * 1024:
        raise RuntimeError("Unexpected runtime download size.")
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        # This distribution is flat; reject unexpected paths before extraction.
        if any(Path(name).name != name for name in archive.namelist()):
            raise RuntimeError("Unexpected paths in the Python runtime archive.")
        directory.mkdir(exist_ok=True)
        archive.extractall(directory)
    print("32-bit EZTrans helper runtime is ready.")


if __name__ == "__main__":
    main()
