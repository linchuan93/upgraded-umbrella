# -*- mode: python ; coding: utf-8 -*-
"""
OpenClaw 一键安装程序 - PyInstaller 打包配置

此文件定义了如何将 Python 项目打包为独立可执行文件。
使用命令: pyinstaller openclaw_installer.spec

各平台打包产物:
- Windows: dist/OpenClaw_Installer.exe
- macOS: dist/OpenClaw_Installer.app
- Linux: dist/OpenClaw_Installer (可转为 AppImage)
"""

import sys
import os

block_cipher = None

# ── 分析入口 ──
a = Analysis(
    ['src/main.py'],                  # 主入口文件
    pathex=[],                         # 额外搜索路径
    binaries=[],                       # 额外二进制文件
    datas=[],                          # 额外数据文件
    hiddenimports=[
        # 确保这些模块被正确打包
        'tkinter',
        'tkinter.ttk',
        'tkinter.scrolledtext',
        'tkinter.messagebox',
        'pty',
        'fcntl',
        'winreg',
        'ctypes',
        'urllib.request',
        'hashlib',
        'json',
        'subprocess',
        'platform',
        'shutil',
        'tempfile',
        'threading',
        'socket',
        'select',
        'signal',
        'glob',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 排除不需要的模块以减小体积
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'PIL',
        'cv2',
        'torch',
        'tensorflow',
        'IPython',
        'jupyter',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ── 根据平台生成不同的产物 ──
if sys.platform == 'win32':
    # Windows: 生成单个 .exe 文件
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        name='OpenClaw_Installer',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,          # 不显示控制台窗口
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon='assets/icon.ico',  # Windows 图标
        # UAC 管理员权限请求
        uac_admin=True,          # 自动请求管理员权限
    )

elif sys.platform == 'darwin':
    # macOS: 生成 .app 包
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name='OpenClaw_Installer',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch='universal2',  # 支持 Intel + Apple Silicon
        icon='assets/icon.icns',   # macOS 图标
    )
    
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name='OpenClaw_Installer',
    )
    
    app = BUNDLE(
        coll,
        name='OpenClaw_Installer.app',
        icon='assets/icon.icns',
        bundle_identifier='com.openclaw.installer',
        info_plist={
            'CFBundleName': 'OpenClaw Installer',
            'CFBundleDisplayName': 'OpenClaw Installer',
            'CFBundleVersion': '1.0.0',
            'CFBundleShortVersionString': '1.0.0',
            'NSHighResolutionCapable': True,
            'LSMinimumSystemVersion': '12.0',
            'NSRequiresAquaSystemAppearance': False,
        },
    )

else:
    # Linux: 生成单个可执行文件
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        name='OpenClaw_Installer',
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
    )
