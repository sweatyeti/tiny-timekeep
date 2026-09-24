# PyInstaller spec - one-file Windows build.
#   python -m PyInstaller packaging/keeper-of-time.spec --noconfirm
# Run from the project root so the paths below resolve.

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).resolve().parent  # project root (SPECPATH is packaging/)

# pywebview ships JS/CSS assets and resolves its platform backend at runtime. Its own PyInstaller
# hook normally covers this, but collecting explicitly is what makes the Windows backend
# (pythonnet/clr -> WebView2) survive --onefile without a hidden-import guessing game.
datas = [
    (str(ROOT / "ui"), "ui"),           # the frontend, loaded from a path relative to the exe
] + collect_data_files("webview")

hiddenimports = ["clr", "clr_loader"] + collect_submodules("webview")

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT), str(ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "unittest"],   # unittest is test-only; tkinter is pywebview's fallback
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="KeeperOfTime",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,              # windowed: no console box. Use --debug flag of main.py for devtools.
)
