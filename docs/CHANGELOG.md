# 更新日志

本文档记录 OpenClaw 一键安装程序的每次版本更新内容。

---

## [1.0.0] - 2025-06-06

### 新增

- 跨平台安装支持（Windows 10/11、macOS 12+、Linux Ubuntu 20.04+/Debian 11+）
- 全自动安装流程，无需用户手动操作
- 智能平台检测（操作系统、CPU 架构、磁盘空间、杀毒软件）
- 智能网络检测与国内镜像自动切换
- 自动安装依赖（Node.js ≥ 22.14、Python 3.10+、Git）
- OpenClaw 自动安装（官方脚本 + npm 降级）
- 智能应答引擎（三级降级：non-interactive → PTY → 手动提示）
- 守护进程自动安装与开机自启配置
- 安全默认配置（127.0.0.1 监听、关闭遥测）
- openclaw doctor 诊断与自动修复
- 智能错误处理与重试（最多 3 次指数退避）
- tkinter 图形化界面（进度条、步骤展示、日志窗口）
- 命令行模式降级（无 GUI 环境自动切换）
- 权限自动申请与提权引导
- SHA-256 文件校验支持
- 结构化错误日志与报告
- 配置文件备份与回滚
- 完整构建脚本（Windows/macOS/Linux）
- PyInstaller 打包配置（含 UAC 管理员权限请求）
- AppImage 生成支持（Linux）
- 代码签名指引（Windows/macOS）
- 完整文档（README、BUILD、TROUBLESHOOTING、CHANGELOG）
