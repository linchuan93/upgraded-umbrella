# OpenClaw 一键安装程序

> 零交互 · 零环境依赖 · 全系统兼容

一个跨平台（Windows / macOS / Linux）的 OpenClaw 一键安装程序，用户下载后双击打开，无需敲任何命令、无需提前安装任何运行环境，即可全自动完成 OpenClaw 从环境检测到最终配置的全部安装流程。

---

## 特性

- **零环境依赖**：无需预装 Python、Node.js 等任何运行环境
- **全自动安装**：双击启动后，自动完成所有安装步骤
- **跨平台支持**：Windows 10/11、macOS 12+、Ubuntu 20.04+ / Debian 11+
- **智能应答**：自动处理 openclaw onboard 向导中的所有交互式提示
- **国内镜像加速**：自动检测网络环境，国内用户自动切换镜像源
- **智能修复**：安装失败时自动运行诊断和修复
- **图形化界面**：提供直观的进度展示和日志输出
- **安全优先**：默认监听 127.0.0.1，不暴露公网

---

## 下载与安装

### Windows

1. 下载 `OpenClaw_Installer.exe`
2. **右键** → **以管理员身份运行**
3. 等待安装完成

> ⚠️ Windows 必须以管理员身份运行，否则无法安装系统服务。

### macOS

1. 下载 `OpenClaw_Installer.app`
2. 首次运行需绕过 Gatekeeper：
   - 右键点击 → 选择"打开"
   - 或在"系统设置 → 隐私与安全性"中允许运行
3. 按提示授予辅助功能权限（用于自动应答）
4. 输入管理员密码以安装系统服务

> 💡 如果使用未签名的应用，需要运行：
> ```bash
> xattr -cr OpenClaw_Installer.app
> ```

### Linux

1. 下载 `OpenClaw_Installer.AppImage`（或 `OpenClaw_Installer` 可执行文件）
2. 添加执行权限：
   ```bash
   chmod +x OpenClaw_Installer.AppImage
   ```
3. 运行（建议使用 sudo）：
   ```bash
   sudo ./OpenClaw_Installer.AppImage
   ```

---

## 安装流程

安装程序会自动执行以下步骤：

| 步骤 | 描述 |
|------|------|
| 1. 检测系统环境 | 识别操作系统、CPU架构、磁盘空间 |
| 2. 检测网络环境 | 测试网络连通性，自动切换国内镜像 |
| 3. 检查权限 | 验证管理员权限，自动请求提权 |
| 4. 安装依赖 | 静默安装 Node.js ≥ 22.14、Python 3.10+、Git |
| 5. 安装 OpenClaw | 使用官方脚本或 npm 安装 |
| 6. 运行初始化向导 | 智能应答 openclaw onboard 所有交互 |
| 7. 安装守护进程 | 配置开机自启动服务 |
| 8. 安全配置 | 应用安全默认值（127.0.0.1 监听） |
| 9. 运行诊断 | 验证安装结果，自动修复问题 |
| 10. 完成 | 显示安装结果 |

---

## 环境变量

| 变量名 | 说明 | 示例 |
|--------|------|------|
| `CUSTOM_API_KEY` | 预设 API Key，避免手动输入 | `sk-ant-xxx` |
| `OPENCLAW_API_KEY` | OpenClaw 使用的 API Key | `sk-ant-xxx` |

---

## 文件校验

下载后建议校验文件完整性：

```bash
# Windows
certutil -hashfile OpenClaw_Installer.exe SHA256

# macOS
shasum -a 256 OpenClaw_Installer.app

# Linux
sha256sum OpenClaw_Installer.AppImage
```

---

## 安全声明

- 本程序**不会收集任何个人信息**，所有安装过程均在本地执行
- 默认将服务监听在 `127.0.0.1`，不自动暴露到公网
- 建议设置强密码，不要将服务端口暴露在公网
- 警惕提示词注入攻击

---

## 日志位置

安装日志保存在 `~/OpenClaw_Installer_Logs/` 目录：

| 文件 | 说明 |
|------|------|
| `install.log` | 完整安装日志 |
| `error.log` | 错误报告（如有） |

---

## 代码签名

### Windows

建议申请 OV 或 EV 代码签名证书对 .exe 进行签名，可避免 SmartScreen 的"未知发布者"警告：

| 证书类型 | 提供商 | 参考价格 |
|---------|--------|---------|
| OV 证书 | Certum / DigiCert / GlobalSign | ~1200 元/年 |
| EV 证书 | DigiCert / GlobalSign | ~4000 元/年 |

签名命令：
```bash
signtool sign /tr http://timestamp.digicert.com /td sha256 /fd sha256 /a OpenClaw_Installer.exe
```

### macOS

需要 Apple Developer Program 会员（年费 $99）：

```bash
codesign --deep --force --verify --verbose \
  --sign "Developer ID Application: YOUR_NAME (TEAM_ID)" \
  OpenClaw_Installer.app
```

---

## 技术栈

- **语言**: Python 3.10+
- **GUI**: tkinter（Python 内置，零额外依赖）
- **打包**: PyInstaller 6.0+
- **架构**: 模块化设计，核心逻辑与 GUI 分离

---

## 许可证

MIT License
