# 构建指南

本文档说明如何从源代码构建 OpenClaw 一键安装程序。

---

## 前置条件

### 通用要求

- Python 3.10 或更高版本
- pip 包管理器

### 平台特定要求

| 平台 | 要求 |
|------|------|
| Windows | Visual C++ Build Tools |
| macOS | Xcode Command Line Tools (`xcode-select --install`) |
| Linux | build-essential, python3-tk, zlib1g-dev |

---

## 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/your-org/openclaw-installer.git
cd openclaw-installer
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 构建安装程序

#### Windows

```bash
build\build_windows.bat
```

或手动执行：

```bash
pyinstaller openclaw_installer.spec --clean --noconfirm
```

产物：`dist/OpenClaw_Installer.exe`

#### macOS

```bash
chmod +x build/build_macos.sh
./build/build_macos.sh
```

或手动执行：

```bash
pyinstaller openclaw_installer.spec --clean --noconfirm
```

产物：`dist/OpenClaw_Installer.app`

#### Linux

```bash
chmod +x build/build_linux.sh
./build/build_linux.sh
```

或手动执行：

```bash
pyinstaller openclaw_installer.spec --clean --noconfirm
chmod +x dist/OpenClaw_Installer
```

产物：`dist/OpenClaw_Installer`

---

## 项目结构

```
.
├── src/
│   ├── main.py                    # 主入口（GUI + CLI 降级）
│   ├── gui/
│   │   ├── __init__.py
│   │   └── installer_app.py       # tkinter GUI 应用（集成在 main.py 中）
│   ├── core/
│   │   ├── __init__.py
│   │   ├── platform_detector.py   # 平台检测
│   │   ├── dependency_manager.py  # 依赖管理（Node.js/Python/Git）
│   │   ├── network_manager.py     # 网络检测与镜像配置
│   │   ├── openclaw_installer.py  # OpenClaw 安装
│   │   ├── onboard_handler.py     # 智能应答引擎
│   │   ├── daemon_manager.py      # 守护进程管理
│   │   ├── doctor_runner.py       # 诊断修复
│   │   ├── error_handler.py       # 错误处理与重试
│   │   └── config_manager.py      # 配置管理
│   └── utils/
│       ├── __init__.py
│       ├── logger.py              # 日志系统
│       ├── privilege.py           # 权限管理
│       └── security.py            # 安全检查
├── build/
│   ├── build_windows.bat          # Windows 构建脚本
│   ├── build_macos.sh             # macOS 构建脚本
│   └── build_linux.sh             # Linux 构建脚本
├── assets/
│   ├── icon.ico                   # Windows 图标
│   ├── icon.icns                  # macOS 图标
│   └── icon.png                   # Linux 图标
├── docs/
│   ├── README.md                  # 使用说明
│   ├── BUILD.md                   # 本文件
│   ├── TROUBLESHOOTING.md         # 故障排查
│   └── CHANGELOG.md               # 更新日志
├── openclaw_installer.spec        # PyInstaller 配置
├── requirements.txt               # Python 依赖
└── .coze                          # 运行环境配置
```

---

## PyInstaller 打包参数说明

### 关键参数

| 参数 | 说明 |
|------|------|
| `--clean` | 清理临时文件后重新构建 |
| `--noconfirm` | 不询问直接覆盖输出目录 |
| `--onefile` | 打包为单个可执行文件（Windows/Linux） |
| `--windowed` | 不显示控制台窗口（GUI 模式） |
| `--uac-admin` | Windows 请求管理员权限 |
| `--icon` | 设置应用图标 |

### 自定义打包

如果需要修改打包配置，编辑 `openclaw_installer.spec` 文件：

```python
# 添加数据文件
datas=[('assets', 'assets')],

# 添加隐式导入
hiddenimports=['your_module'],

# 排除不需要的模块（减小体积）
excludes=['matplotlib', 'numpy'],
```

---

## 图标准备

### Windows (.ico)

需要一个多尺寸的 ICO 文件（包含 16x16, 32x32, 48x48, 256x256）：

```bash
# 使用 ImageMagick 转换
convert icon.png -define icon:auto-resize=256,128,64,48,32,16 icon.ico
```

### macOS (.icns)

需要使用 `iconutil` 工具：

```bash
mkdir icon.iconset
sips -z 16 16     icon.png --out icon.iconset/icon_16x16.png
sips -z 32 32     icon.png --out icon.iconset/icon_16x16@2x.png
sips -z 32 32     icon.png --out icon.iconset/icon_32x32.png
sips -z 64 64     icon.png --out icon.iconset/icon_32x32@2x.png
sips -z 128 128   icon.png --out icon.iconset/icon_128x128.png
sips -z 256 256   icon.png --out icon.iconset/icon_128x128@2x.png
sips -z 256 256   icon.png --out icon.iconset/icon_256x256.png
sips -z 512 512   icon.png --out icon.iconset/icon_256x256@2x.png
sips -z 512 512   icon.png --out icon.iconset/icon_512x512.png
sips -z 1024 1024 icon.png --out icon.iconset/icon_512x512@2x.png
iconutil -c icns icon.iconset -o assets/icon.icns
```

---

## 生成 AppImage（Linux）

```bash
# 安装 appimagetool
wget https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage
chmod +x appimagetool-x86_64.AppImage

# 使用构建脚本自动生成
./build/build_linux.sh
```

---

## 测试

### 本地运行（不打包）

```bash
# GUI 模式
python src/main.py

# 命令行模式（自动降级）
python src/main.py --no-gui
```

### 设置 API Key 环境变量

```bash
# Windows
set CUSTOM_API_KEY=sk-ant-xxx

# macOS/Linux
export CUSTOM_API_KEY=sk-ant-xxx
```

---

## 持续集成

可在 CI/CD 中自动构建各平台产物。示例 GitHub Actions 配置：

```yaml
name: Build
on: [push, pull_request]

jobs:
  build-windows:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install -r requirements.txt
      - run: pyinstaller openclaw_installer.spec --clean --noconfirm
      - uses: actions/upload-artifact@v4
        with:
          name: OpenClaw_Installer_Windows
          path: dist/OpenClaw_Installer.exe

  build-macos:
    runs-on: macos-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install -r requirements.txt
      - run: pyinstaller openclaw_installer.spec --clean --noconfirm
      - uses: actions/upload-artifact@v4
        with:
          name: OpenClaw_Installer_macOS
          path: dist/OpenClaw_Installer.app

  build-linux:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: sudo apt-get install -y python3-tk
      - run: pip install -r requirements.txt
      - run: pyinstaller openclaw_installer.spec --clean --noconfirm
      - uses: actions/upload-artifact@v4
        with:
          name: OpenClaw_Installer_Linux
          path: dist/OpenClaw_Installer
```
