# -*- mode: python ; coding: utf-8 -*-
import os
from version import __version__

icon_file = 'app_icon.ico' if os.path.exists('app_icon.ico') else 'NONE'
datas_list = [
    ('README.md', '.'),
    ('LICENSE', '.'),
    ('RELEASE_NOTES.md', '.'),
    ('profiles', 'profiles'),
    ('data', 'data'),
    ('create_desktop_shortcut.ps1', '.'),
    ('se_render/shaders', 'se_render/shaders'),
]
if os.path.exists('app_icon.ico'):
    datas_list.append(('app_icon.ico', '.'))
if os.path.exists('logo.png'):
    datas_list.append(('logo.png', '.'))

a = Analysis(
    ['gui_standalone.py'],
    pathex=[],
    binaries=[],
    datas=datas_list,
    hiddenimports=[
        'resource_paths',
        'se_assets',
        'se_assets.install_locator',
        'se_assets.cube_catalog',
        'se_assets.mesh_cache',
        'se_assets.mwm_loader',
        'se_assets.dds_loader',
        'se_render',
        'se_render.hsv',
        'se_render.orientation',
        'se_render.scene_graph',
        'se_render.topology',
        'se_render.viewport',
        'se_render.gl_backend',
        'se_render.camera',
        'se_render.shaders',
        'moderngl',
        'numpy',
        'PIL.ImageTk',
    ],
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
