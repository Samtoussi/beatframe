# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[('/opt/homebrew/bin/ffmpeg', 'bin'), ('/opt/homebrew/bin/ffprobe', 'bin')],
    datas=[
    ('assets', 'assets'),
    ('LICENSE', '.'),
    ('THIRD_PARTY_NOTICES.txt', '.'),
    ('GPL-3.0.txt', '.'),
],
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
    [],
    exclude_binaries=True,
    name='BeatFrame',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets/beatframe-macos.icns'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='BeatFrame',
)

app = BUNDLE(
    coll,
    name='BeatFrame.app',
    icon='assets/beatframe-macos.icns',
    bundle_identifier='com.beatframe.app',
)
