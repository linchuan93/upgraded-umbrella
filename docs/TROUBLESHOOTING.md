# 故障排查

本文档列出了 OpenClaw 一键安装程序使用过程中可能遇到的常见问题及解决方案。

---

## 常见问题

### 1. Windows: "需要管理员权限"

**症状**: 程序启动后提示需要管理员权限

**解决方案**:
1. 右键点击 `OpenClaw_Installer.exe`
2. 选择"以管理员身份运行"
3. 如果仍然失败，请联系系统管理员

---

### 2. Windows: SmartScreen 拦截

**症状**: Windows 显示"Windows 已保护你的电脑"提示

**解决方案**:
1. 点击"更多信息"
2. 点击"仍要运行"

> 💡 这是因为安装程序未经过代码签名。建议开发者申请代码签名证书（参见 README 中的代码签名章节）。

---

### 3. macOS: "无法打开，因为无法验证开发者"

**症状**: macOS Gatekeeper 阻止运行

**解决方案**:

方法一：右键打开
1. 右键（或 Control+点击）应用
2. 选择"打开"
3. 在弹出的对话框中再次点击"打开"

方法二：使用终端
```bash
xattr -cr OpenClaw_Installer.app
open OpenClaw_Installer.app
```

方法三：在系统设置中允许
1. 前往"系统设置 → 隐私与安全性"
2. 在"安全性"部分找到被阻止的应用
3. 点击"仍然允许"

---

### 4. macOS: 辅助功能权限

**症状**: 自动应答功能无法正常工作

**解决方案**:
1. 前往"系统设置 → 隐私与安全性 → 辅助功能"
2. 点击 + 号，添加 OpenClaw_Installer.app
3. 确保开关已打开
4. 重新运行安装程序

---

### 5. 国内网络下载慢

**症状**: 下载 Node.js 或 Python 安装包速度很慢

**解决方案**:

安装程序会自动检测国内网络环境并切换镜像源。如果自动切换失败：

手动配置 npm 镜像：
```bash
npm config set registry https://registry.npmmirror.com
```

手动配置 pip 镜像：
```bash
pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

---

### 6. 端口被占用

**症状**: OpenClaw 默认端口 3000 被其他程序占用

**解决方案**:

方法一：安装程序会自动检测并分配可用端口

方法二：手动修改配置文件
- 配置文件位置：`~/.openclaw/config.json`
- 修改 `"port"` 字段为其他可用端口

方法三：释放占用端口的进程
```bash
# 查找占用端口的进程
# Windows
netstat -ano | findstr :3000

# macOS/Linux
lsof -i :3000
```

---

### 7. Node.js 安装失败

**症状**: Node.js 安装过程中报错

**可能原因及解决方案**:

| 原因 | 解决方案 |
|------|---------|
| 网络超时 | 切换国内镜像后重试 |
| 权限不足 | 以管理员/root 身份运行 |
| 磁盘空间不足 | 清理磁盘空间（需至少 2GB） |
| 防火墙拦截 | 临时关闭防火墙或添加白名单 |
| 杀毒软件拦截 | 临时关闭杀毒软件 |

手动安装 Node.js：
```bash
# macOS
brew install node@22

# Linux (Ubuntu/Debian)
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt-get install -y nodejs

# Windows
winget install OpenJS.NodeJS.LTS
```

---

### 8. openclaw onboard 自动应答失败

**症状**: 自动初始化失败，提示需要手动操作

**解决方案**:

手动运行初始化向导：
```bash
openclaw onboard
```

如果支持非交互模式：
```bash
openclaw onboard --non-interactive --mode local --install-daemon --accept-risk
```

设置 API Key 环境变量后重试：
```bash
export CUSTOM_API_KEY=sk-ant-xxx
# 重新运行安装程序
```

---

### 9. 守护进程安装失败

**症状**: 开机自启服务未成功安装

**解决方案**:

手动安装守护进程：

**Windows**:
```bash
schtasks /create /tn "OpenClawDaemon" /tr "openclaw daemon start" /sc onlogon /rl highest /f
```

**macOS**:
```bash
sudo launchctl load -w /Library/LaunchDaemons/com.openclaw.daemon.plist
```

**Linux**:
```bash
sudo systemctl enable openclaw
sudo systemctl start openclaw
```

---

### 10. 安装完成后无法使用 openclaw 命令

**症状**: 终端提示 "openclaw: command not found"

**解决方案**:

1. 重新打开终端（PATH 环境变量可能需要刷新）
2. 检查 openclaw 安装路径：
   ```bash
   # 查找 openclaw
   where openclaw     # Windows
   which openclaw     # macOS/Linux
   ```
3. 如果找到但无法使用，手动添加到 PATH：
   ```bash
   # macOS/Linux (添加到 ~/.zshrc 或 ~/.bashrc)
   export PATH="/usr/local/bin:$PATH"
   ```

---

### 11. 运行 openclaw doctor 诊断

如果安装后遇到问题，建议先运行诊断：

```bash
openclaw doctor
```

如果诊断发现问题，尝试自动修复：

```bash
openclaw doctor --repair
```

---

### 12. 查看安装日志

安装日志保存在 `~/OpenClaw_Installer_Logs/` 目录：

```bash
# 查看完整日志
cat ~/OpenClaw_Installer_Logs/install.log

# 查看错误日志
cat ~/OpenClaw_Installer_Logs/error.log

# 搜索特定错误
grep -i "error" ~/OpenClaw_Installer_Logs/install.log
```

---

## 仍然无法解决？

1. 查看 [GitHub Issues](https://github.com/your-org/openclaw-installer/issues)
2. 提交新的 Issue，附上：
   - 操作系统和版本
   - 安装日志（`~/OpenClaw_Installer_Logs/install.log`）
   - 错误截图或文本
3. 尝试手动安装：
   ```bash
   # macOS/Linux
   curl -fsSL https://openclaw.ai/install.sh | bash
   
   # Windows PowerShell
   iwr -useb https://openclaw.ai/install.ps1 | iex
   ```
