# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules
from PyInstaller.utils.win32.versioninfo import VSVersionInfo, FixedFileInfo, StringFileInfo, StringTable, StringStruct, VarFileInfo, VarStruct
from version import __version__

version_parts = tuple(int(p) for p in __version__.split('.')) + (0,)
version_info = VSVersionInfo(ffi=FixedFileInfo(filevers=version_parts, prodvers=version_parts,
    mask=0x3f, flags=0, OS=0x40004, fileType=1, subtype=0, date=(0, 0)), kids=[
    StringFileInfo([StringTable('040904B0', [StringStruct('FileDescription', 'SE Tactical Command'),
        StringStruct('FileVersion', __version__), StringStruct('ProductName', 'SE Tactical Command'),
        StringStruct('ProductVersion', __version__)])]), VarFileInfo([VarStruct('Translation', [1033, 1200])])])

icon_file = 'app_icon.ico' if os.path.exists('app_icon.ico') else 'NONE'
datas_list = [
    ('README.md', '.'),
    ('INSTALL.md', '.'),
    ('COMPATIBILITY.md', '.'),
    ('release_acceptance.json', '.'),
    ('LICENSE', '.'),
    ('RELEASE_NOTES.md', '.'),
    ('profiles', 'profiles'),
    ('data', 'data'),
    ('create_desktop_shortcut.ps1', '.'),
    ('se_render/shaders', 'se_render/shaders'),
]
datas_list += collect_data_files('customtkinter')
if os.path.exists('app_icon.ico'):
    datas_list.append(('app_icon.ico', '.'))
if os.path.exists('logo.png'):
    datas_list.append(('logo.png', '.'))

a = Analysis(
    ['gui_standalone.py'],
    pathex=[],
    binaries=[],
    datas=datas_list,
    hiddenimports=collect_submodules('se_assets') + collect_submodules('se_render') + collect_submodules('glcontext') + [
        'resource_paths',
        'runtime_selftest',
        'blueprint_document',
        'blueprint_edit',
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
    version=version_info,
)
