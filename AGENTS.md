# AGENTS.md

## 项目概览

OpenClaw 一键安装程序 — 跨平台桌面安装程序，支持 Windows/macOS/Linux，零交互、零环境依赖、全自动安装。

## 技术栈

- **语言**: Python 3.10+
- **GUI**: tkinter（内置，零额外依赖）
- **打包**: PyInstaller 6.0+
- **包管理**: pip + requirements.txt

## 项目结构

```
src/
├── main.py                    # 主入口（GUI + CLI 降级）
├── core/
│   ├── platform_detector.py   # 平台检测
│   ├── dependency_manager.py  # 依赖管理
│   ├── network_manager.py     # 网络检测与镜像配置
│   ├── openclaw_installer.py  # OpenClaw 安装
│   ├── onboard_handler.py     # 智能应答引擎
│   ├── daemon_manager.py      # 守护进程管理
│   ├── doctor_runner.py       # 诊断修复
│   ├── error_handler.py       # 错误处理与重试
│   └── config_manager.py      # 配置管理
├── gui/
│   └── installer_app.py       # GUI（集成在 main.py 中）
└── utils/
    ├── logger.py              # 日志系统
    ├── privilege.py           # 权限管理
    └── security.py            # 安全检查
```

## 构建命令

```bash
pip install -r requirements.txt
pyinstaller openclaw_installer.spec --clean --noconfirm
```

## 代码风格

- Python PEP 8 规范
- 每个模块包含完整的 docstring
- 类型注解（Type Hints）
- 数据类使用 @dataclass
- 日志使用 logging 模块

## 关键设计决策

1. 使用 tkinter 而非 Electron：零额外依赖，打包体积更小
2. 三级降级策略：non-interactive → PTY → 手动提示
3. 错误处理采用指数退避重试（2^n 秒）
4. 配置文件使用 JSON 格式，修改前自动备份
5. 安全优先：默认 127.0.0.1 监听，不暴露公网
