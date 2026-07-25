# -*- mode: python ; coding: utf-8 -*-
# 安装程序：自带 AnTi.exe 本体，运行后释放到本地并创建快捷方式。
# 构建：pyinstaller setup.spec  （在 agent_app 目录下执行）

a = Analysis(
    ['installer.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets', 'assets'),
        ('AnTi.exe', '.'),
    ],
    hiddenimports=['win32com', 'win32com.client'],
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
    name='AnTi-Setup',
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
    icon=['assets\\anti_icon.ico'],
)
