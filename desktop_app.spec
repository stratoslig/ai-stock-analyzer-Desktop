# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files
import os

block_cipher = None

# All the data files we need to collect
datas = []
datas += collect_data_files('customtkinter')
datas += collect_data_files('pandas_ta')
datas += collect_data_files('trafilatura')
datas += collect_data_files('cloudscraper')
datas += collect_data_files('ddgs')
datas += collect_data_files('feedparser')
datas.append(('icon.ico', '.')) # For Windows Taskbar icon

# All the hidden imports PyInstaller might miss
hiddenimports = [
    'yfinance',
    'pandas',
    'PyPDF2',
    'matplotlib.backends.backend_tkagg',
    'matplotlib.widgets',
    'sklearn',
    'sklearn.utils._cython_blas',
    'sklearn.neighbors._typedefs',
    'sklearn.neighbors._quad_tree',
    'openpyxl',
    'dateutil.parser',
    'pkg_resources.py2_warn',
    'lxml',
    'google.generativeai',
    'google.ai.generativelanguage',
    'docx',
]

a = Analysis(
    ['desktop_app.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Configuration for Windows and Linux executables
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AI Stock Analyzer Desktop',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # This is equivalent to --noconsole or --windowed
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico' # Icon for the .exe file
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='AI Stock Analyzer Desktop',
)

# Configuration for the macOS .app bundle
app = BUNDLE(
    coll,
    name='AI Stock Analyzer Desktop.app',
    icon='icon.icns',
    bundle_identifier='pro.aistockanalyzer.desktop',
)