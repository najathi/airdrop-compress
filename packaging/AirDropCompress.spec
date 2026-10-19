# PyInstaller spec for the macOS app bundle. Build with: packaging/build.sh
import re
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).parent
VERSION = re.search(r'__version__ = "([^"]+)"', (ROOT / "airdrop_compress" / "__init__.py").read_text()).group(1)
BUNDLE_ID = "com.najathi.airdropcompress"

datas = [(str(ROOT / "airdrop_compress" / "ui" / "web"), "airdrop_compress/ui/web")]
for pkg in ("magika", "pdfminer", "markitdown", "certifi"):
    datas += collect_data_files(pkg)

hiddenimports = (
    collect_submodules("airdrop_compress")
    + collect_submodules("markitdown.converters")
    + ["pillow_heif", "webview.platforms.cocoa", "PyObjCTools.AppHelper"]
)

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT)],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "pytest", "IPython", "matplotlib", "PyQt5", "PyQt6", "PySide6", "gi",
              "azure", "youtube_transcript_api", "speech_recognition", "pydub"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="AirDrop Compress",
          console=False, argv_emulation=False, upx=False, codesign_identity=None)
coll = COLLECT(exe, a.binaries, a.datas, name="AirDrop Compress", upx=False)
app = BUNDLE(
    coll,
    name="AirDrop Compress.app",
    icon=str(ROOT / "build" / "AppIcon.icns"),
    bundle_identifier=BUNDLE_ID,
    version=VERSION,
    info_plist={
        "CFBundleName": "AirDrop Compress",
        "CFBundleDisplayName": "AirDrop Compress",
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        "LSUIElement": True,                    # menu bar app: no Dock icon
        "LSMinimumSystemVersion": "12.0",
        "LSApplicationCategoryType": "public.app-category.productivity",
        "NSHumanReadableCopyright": "MIT licence",
        "NSHighResolutionCapable": True,
        "NSDesktopFolderUsageDescription": "AirDrop Compress watches the AirDrop folder on your Desktop for new files to convert.",
        "NSDownloadsFolderUsageDescription": "AirDrop Compress watches your Downloads folder, where AirDrop saves received files.",
        "NSDocumentsFolderUsageDescription": "AirDrop Compress converts files you choose from your Documents folder.",
        "NSAppleEventsUsageDescription": "AirDrop Compress uses Finder to move itself to the Trash when you uninstall it.",
    },
)
