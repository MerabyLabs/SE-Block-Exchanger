# -*- mode: python ; coding: utf-8 -*-
import os
from version import __version__

icon_file = 'app_icon.ico' if os.path.exists('app_icon.ico') else 'NONE'
datas_list = [
    ('README.md', '.'),
    ('INSTALL.md', '.'),
    ('LICENSE', '.'),
    ('RELEASE_NOTES.md', '.'),
    ('profiles', 'profiles'),
    ('data', 'data'),
]
if os.path.exists('app_icon.ico'):
    datas_list.append(('app_icon.ico', '.'))

a = Analysis(
    ['gui_standalone.py'],
    pathex=[],
    binaries=[],
    datas=datas_list,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=f'SE_Tactical_Command_v{__version__}',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_file,
)
