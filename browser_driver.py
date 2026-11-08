"""Start Chrome with a driver matching the selected browser executable."""
import ctypes
from ctypes import wintypes
import os
import re
import subprocess
import threading
from pathlib import Path

import undetected_chromedriver as uc

_startup_lock = threading.Lock()


class Chrome(uc.Chrome):
    def __del__(self):
        # uc repeats quit() during destruction after the Windows handle is closed.
        try:
            super().__del__()
        except OSError as error:
            if getattr(error, "winerror", None) != 6:
                raise


def chrome_major_version(executable):
    if os.name == "nt":
        version = ctypes.WinDLL("version", use_last_error=True)
        version.GetFileVersionInfoSizeW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
        version.GetFileVersionInfoSizeW.restype = wintypes.DWORD
        version.GetFileVersionInfoW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
        version.GetFileVersionInfoW.restype = wintypes.BOOL
        version.VerQueryValueW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.UINT)]
        version.VerQueryValueW.restype = wintypes.BOOL
        unused = wintypes.DWORD()
        size = version.GetFileVersionInfoSizeW(executable, ctypes.byref(unused))
        if not size:
            raise ctypes.WinError(ctypes.get_last_error())
        buffer = ctypes.create_string_buffer(size)
        if not version.GetFileVersionInfoW(executable, 0, size, buffer):
            raise ctypes.WinError(ctypes.get_last_error())
        pointer = ctypes.c_void_p()
        length = wintypes.UINT()
        if not version.VerQueryValueW(buffer, "\\", ctypes.byref(pointer), ctypes.byref(length)):
            raise ctypes.WinError(ctypes.get_last_error())
        # VS_FIXEDFILEINFO: signature, structure version, file version MS/LS.
        info = ctypes.cast(pointer, ctypes.POINTER(wintypes.DWORD))
        if length.value < 16 or info[0] != 0xFEEF04BD:
            raise RuntimeError("Invalid Chrome version metadata")
        return info[2] >> 16
    output = subprocess.check_output([executable, "--version"], text=True, timeout=10)
    match = re.search(r"(\d+)\.\d+\.\d+", output)
    if not match:
        raise RuntimeError(f"Cannot detect Chrome version: {output.strip()}")
    return int(match.group(1))


def create_driver(*, page_load_strategy="normal"):
    # Patcher downloads/extracts into one shared directory for every brand.
    with _startup_lock:
        return _create_driver(page_load_strategy=page_load_strategy)


def _create_driver(*, page_load_strategy="normal"):
    executable = uc.find_chrome_executable()
    if not executable:
        raise RuntimeError("Chrome is not installed or its executable cannot be found")
    major = chrome_major_version(executable)
    options = uc.ChromeOptions()
    # Several store sessions run concurrently. Keep React rendering active when
    # another browser window is foregrounded.
    options.add_argument('--disable-background-timer-throttling')
    options.add_argument('--disable-renderer-backgrounding')
    options.add_argument('--disable-backgrounding-occluded-windows')
    options.page_load_strategy = page_load_strategy
    print(f"Chrome major version: {major}; selecting matching ChromeDriver")
    cached = Path(uc.Patcher().executable_path)
    if cached.is_file():
        output = subprocess.run(
            [str(cached), "--version"], capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        match = re.search(r"ChromeDriver (\d+)\.", output.stdout)
        if match and int(match.group(1)) == major:
            return Chrome(options=options, browser_executable_path=executable, version_main=major,
                          driver_executable_path=str(cached), headless=False)
    return Chrome(options=options, browser_executable_path=executable, version_main=major, headless=False)
