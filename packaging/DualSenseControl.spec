# -*- mode: python ; coding: utf-8 -*-
# PyInstaller: un solo DualSenseControl.exe con el panel, dshaptics, los scripts y vDS ya compilado.
# Antes de correrlo, la CI (o packaging/build.ps1) deja:
#   vds-bin/        vdsd.exe, vdsctl.exe, opus.dll  (vDS compilado con vds-mods/*.patch)
#   vds-packaging/  install_dependencies.ps1, install_service.ps1, stop_service.ps1, uninstall_service.ps1
import os
from PyInstaller.utils.hooks import collect_data_files

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))


def src(*p):
    return os.path.join(ROOT, *p)


datas = [
    (src("scripts", "*.ps1"), "scripts"),
    (src("vds-bin", "*"), "vds-bin"),
    (src("vds-packaging", "*"), "vds-packaging"),
    (src("herramientas", "diag-windows.ps1"), "herramientas"),
    (src("LICENSE"), "."),
    (src("THIRD_PARTY.md"), "."),
]
datas += collect_data_files("sv_ttk")

a = Analysis(
    [src("app", "dsgui.py")],
    pathex=[src("app")],
    datas=datas,
    hiddenimports=["dshaptics", "sv_ttk", "pyaudiowpatch", "hid", "soundfile",
                   "scipy.signal", "scipy.fft"],
    excludes=["matplotlib", "pandas", "IPython", "pytest", "PyQt5", "PySide6"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="DualSenseControl",
    console=False,          # ventana sin consola; --cli y --self-test se enganchan a la consola de quien los llama
    upx=False,
    disable_windowed_traceback=False,
    version=os.path.join(SPECPATH, "version_info.txt") if os.path.exists(os.path.join(SPECPATH, "version_info.txt")) else None,
)
