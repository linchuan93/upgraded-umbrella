"""
OpenClaw 一键安装程序 - 守护进程管理模块

功能：
1. 安装 OpenClaw 后台守护进程
2. 配置开机自启动
3. 启动/停止/重启守护进程
4. 检测守护进程运行状态

平台适配：
- Windows: 使用 Windows Service 或任务计划程序
- macOS: 使用 launchd (plist)
- Linux: 使用 systemd 或 cron @reboot

设计原则：
- 优先使用 openclaw 自带的 --install-daemon 功能
- 降级为手动创建系统服务
- 所有操作需要管理员/root 权限
"""

import os
import subprocess
import shutil
import logging
import time
import tempfile
from typing import Optional, Callable, Dict
from dataclasses import dataclass

from .platform_detector import PlatformInfo, OSType

logger = logging.getLogger("OpenClawInstaller")


@dataclass
class DaemonStatus:
    """守护进程状态"""
    installed: bool = False
    running: bool = False
    enabled: bool = False  # 开机自启
    service_name: str = ""
    pid: int = -1


class DaemonManager:
    """
    守护进程管理器
    
    负责：
    1. 安装 OpenClaw 守护进程
    2. 配置开机自启动
    3. 管理守护进程生命周期
    4. 检测守护进程状态
    
    用法:
        dm = DaemonManager(platform_info)
        dm.install_and_start(progress_callback)
    """
    
    def __init__(self, platform_info: PlatformInfo):
        """
        初始化守护进程管理器
        
        Args:
            platform_info: 平台信息对象
        """
        self.platform = platform_info
    
    def install_and_start(self, progress_callback: Optional[Callable[[str, int], None]] = None) -> bool:
        """
        安装并启动守护进程
        
        安装策略（按优先级）：
        1. 使用 openclaw --install-daemon（如果支持）
        2. 手动创建系统服务
        
        Args:
            progress_callback: 进度回调
            
        Returns:
            bool: 是否成功
        """
        logger.info("开始安装守护进程...")
        
        # ── 策略 1: 使用 openclaw 自带功能 ──
        if progress_callback:
            progress_callback("正在安装守护进程...", 30)
        
        if self._install_via_openclaw():
            logger.info("通过 openclaw --install-daemon 安装成功")
            return True
        
        logger.warning("openclaw --install-daemon 不可用，降级为手动创建服务")
        
        # ── 策略 2: 手动创建系统服务 ──
        if progress_callback:
            progress_callback("正在手动创建系统服务...", 60)
        
        if self.platform.os_type == OSType.WINDOWS:
            return self._install_windows_service()
        elif self.platform.os_type == OSType.MACOS:
            return self._install_macos_launchd()
        elif self.platform.os_type == OSType.LINUX:
            return self._install_linux_systemd()
        
        return False
    
    def check_status(self) -> DaemonStatus:
        """
        检测守护进程状态
        
        Returns:
            DaemonStatus: 守护进程状态信息
        """
        status = DaemonStatus()
        
        if self.platform.os_type == OSType.WINDOWS:
            return self._check_windows_status()
        elif self.platform.os_type == OSType.MACOS:
            return self._check_macos_status()
        elif self.platform.os_type == OSType.LINUX:
            return self._check_linux_status()
        
        return status
    
    def start(self) -> bool:
        """启动守护进程"""
        if self.platform.os_type == OSType.WINDOWS:
            return self._run_command(["net", "start", "OpenClaw"])
        elif self.platform.os_type == OSType.MACOS:
            return self._run_command(["launchctl", "load", "-w",
                                      "/Library/LaunchDaemons/com.openclaw.daemon.plist"])
        elif self.platform.os_type == OSType.LINUX:
            return self._run_command(["sudo", "systemctl", "start", "openclaw"])
        return False
    
    def stop(self) -> bool:
        """停止守护进程"""
        if self.platform.os_type == OSType.WINDOWS:
            return self._run_command(["net", "stop", "OpenClaw"])
        elif self.platform.os_type == OSType.MACOS:
            return self._run_command(["launchctl", "unload",
                                      "/Library/LaunchDaemons/com.openclaw.daemon.plist"])
        elif self.platform.os_type == OSType.LINUX:
            return self._run_command(["sudo", "systemctl", "stop", "openclaw"])
        return False
    
    def restart(self) -> bool:
        """重启守护进程"""
        self.stop()
        time.sleep(2)
        return self.start()
    
    # ── 内部方法 ──
    
    def _install_via_openclaw(self) -> bool:
        """
        使用 openclaw 自带的 --install-daemon 功能
        
        Returns:
            bool: 是否安装成功
        """
        openclaw = shutil.which("openclaw")
        if not openclaw:
            return False
        
        try:
            result = subprocess.run(
                ["openclaw", "daemon", "install"],
                capture_output=True, text=True, timeout=60
            )
            if result.returncode == 0:
                # 启动守护进程
                subprocess.run(
                    ["openclaw", "daemon", "start"],
                    capture_output=True, timeout=30
                )
                return True
            return False
        except Exception as e:
            logger.debug(f"openclaw daemon install 失败: {e}")
            return False
    
    def _install_windows_service(self) -> bool:
        """
        Windows: 使用任务计划程序创建开机自启任务
        
        不使用 Windows Service（需要编译为 .dll），
        而是使用任务计划程序（更简单可靠）。
        """
        openclaw = shutil.which("openclaw")
        if not openclaw:
            return False
        
        try:
            # 创建任务计划（开机自启，以当前用户身份运行）
            task_name = "OpenClawDaemon"
            cmd = [
                "schtasks", "/create",
                "/tn", task_name,
                "/tr", f'"{openclaw}" daemon start',
                "/sc", "onlogon",  # 用户登录时启动
                "/rl", "highest",  # 最高权限运行
                "/f"  # 覆盖已存在的任务
            ]
            
            result = subprocess.run(cmd, capture_output=True, timeout=30)
            if result.returncode == 0:
                logger.info(f"Windows 任务计划 '{task_name}' 创建成功")
                
                # 立即启动一次
                subprocess.run(
                    ["schtasks", "/run", "/tn", task_name],
                    capture_output=True, timeout=30
                )
                return True
            else:
                logger.error(f"任务计划创建失败: {result.stderr.decode()[:200]}")
                return False
                
        except Exception as e:
            logger.error(f"Windows 服务安装异常: {e}")
            return False
    
    def _install_macos_launchd(self) -> bool:
        """
        macOS: 创建 launchd plist 实现开机自启
        
        plist 文件安装到 /Library/LaunchDaemons/ 目录。
        """
        openclaw = shutil.which("openclaw") or "/usr/local/bin/openclaw"
        
        plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.openclaw.daemon</string>
    <key>ProgramArguments</key>
    <array>
        <string>{openclaw}</string>
        <string>daemon</string>
        <string>start</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/openclaw-daemon.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/openclaw-daemon-error.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>"""
        
        plist_path = "/Library/LaunchDaemons/com.openclaw.daemon.plist"
        
        try:
            # 写入 plist 文件
            with tempfile.NamedTemporaryFile(mode='w', suffix='.plist', delete=False) as f:
                f.write(plist_content)
                temp_plist = f.name
            
            # 复制到 LaunchDaemons（需要 sudo）
            subprocess.run(
                ["sudo", "cp", temp_plist, plist_path],
                capture_output=True, timeout=10
            )
            
            # 设置权限
            subprocess.run(
                ["sudo", "chown", "root:wheel", plist_path],
                capture_output=True, timeout=10
            )
            subprocess.run(
                ["sudo", "chmod", "644", plist_path],
                capture_output=True, timeout=10
            )
            
            # 加载 launchd 服务
            result = subprocess.run(
                ["sudo", "launchctl", "load", "-w", plist_path],
                capture_output=True, timeout=30
            )
            
            os.unlink(temp_plist)
            
            if result.returncode == 0:
                logger.info("macOS launchd 服务安装成功")
                return True
            else:
                logger.error(f"launchctl load 失败: {result.stderr.decode()[:200]}")
                return False
                
        except Exception as e:
            logger.error(f"macOS launchd 安装异常: {e}")
            return False
    
    def _install_linux_systemd(self) -> bool:
        """
        Linux: 创建 systemd service 实现开机自启
        
        service 文件安装到 /etc/systemd/system/ 目录。
        """
        openclaw = shutil.which("openclaw") or "/usr/local/bin/openclaw"
        
        service_content = f"""[Unit]
Description=OpenClaw Daemon
After=network.target

[Service]
Type=simple
ExecStart={openclaw} daemon start
Restart=on-failure
RestartSec=5
Environment=PATH=/usr/local/bin:/usr/bin:/bin
WorkingDirectory=/tmp

[Install]
WantedBy=multi-user.target
"""
        
        service_path = "/etc/systemd/system/openclaw.service"
        
        try:
            # 写入 service 文件
            with tempfile.NamedTemporaryFile(mode='w', suffix='.service', delete=False) as f:
                f.write(service_content)
                temp_service = f.name
            
            # 复制到 systemd 目录
            subprocess.run(
                ["sudo", "cp", temp_service, service_path],
                capture_output=True, timeout=10
            )
            subprocess.run(
                ["sudo", "chmod", "644", service_path],
                capture_output=True, timeout=10
            )
            
            # 重新加载 systemd
            subprocess.run(
                ["sudo", "systemctl", "daemon-reload"],
                capture_output=True, timeout=30
            )
            
            # 启用开机自启
            subprocess.run(
                ["sudo", "systemctl", "enable", "openclaw"],
                capture_output=True, timeout=30
            )
            
            # 启动服务
            result = subprocess.run(
                ["sudo", "systemctl", "start", "openclaw"],
                capture_output=True, timeout=30
            )
            
            os.unlink(temp_service)
            
            if result.returncode == 0:
                logger.info("Linux systemd 服务安装成功")
                return True
            else:
                logger.error(f"systemctl start 失败: {result.stderr.decode()[:200]}")
                # 尝试降级为 cron @reboot
                return self._install_linux_cron(openclaw)
                
        except Exception as e:
            logger.error(f"Linux systemd 安装异常: {e}")
            return self._install_linux_cron(openclaw)
    
    def _install_linux_cron(self, openclaw_path: str) -> bool:
        """
        Linux 降级方案: 使用 cron @reboot 实现开机自启
        
        当 systemd 不可用时使用此方案。
        """
        try:
            # 添加 @reboot cron 任务
            cron_line = f"@reboot {openclaw_path} daemon start"
            
            # 获取当前 crontab
            result = subprocess.run(
                ["crontab", "-l"],
                capture_output=True, text=True, timeout=10
            )
            current_cron = result.stdout if result.returncode == 0 else ""
            
            # 检查是否已存在
            if "openclaw" not in current_cron:
                new_cron = current_cron + "\n" + cron_line + "\n"
                process = subprocess.Popen(
                    ["crontab", "-"],
                    stdin=subprocess.PIPE, text=True
                )
                process.communicate(input=new_cron, timeout=10)
                
                if process.returncode == 0:
                    logger.info("Linux cron @reboot 配置成功")
                    return True
            
            return True  # 已存在
            
        except Exception as e:
            logger.error(f"cron 配置异常: {e}")
            return False
    
    def _check_windows_status(self) -> DaemonStatus:
        """检测 Windows 守护进程状态"""
        status = DaemonStatus(service_name="OpenClawDaemon")
        
        try:
            result = subprocess.run(
                ["schtasks", "/query", "/tn", "OpenClawDaemon"],
                capture_output=True, text=True, timeout=10
            )
            status.installed = result.returncode == 0
            status.enabled = "Ready" in result.stdout or "Running" in result.stdout
        except Exception:
            pass
        
        # 检查进程是否在运行
        try:
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq openclaw*"],
                capture_output=True, text=True, timeout=10
            )
            status.running = "openclaw" in result.stdout.lower()
        except Exception:
            pass
        
        return status
    
    def _check_macos_status(self) -> DaemonStatus:
        """检测 macOS 守护进程状态"""
        status = DaemonStatus(service_name="com.openclaw.daemon")
        
        plist_path = "/Library/LaunchDaemons/com.openclaw.daemon.plist"
        status.installed = os.path.exists(plist_path)
        
        try:
            result = subprocess.run(
                ["launchctl", "list", "com.openclaw.daemon"],
                capture_output=True, text=True, timeout=10
            )
            status.running = result.returncode == 0
            status.enabled = status.running
        except Exception:
            pass
        
        return status
    
    def _check_linux_status(self) -> DaemonStatus:
        """检测 Linux 守护进程状态"""
        status = DaemonStatus(service_name="openclaw")
        
        # 检查 systemd
        try:
            result = subprocess.run(
                ["systemctl", "is-enabled", "openclaw"],
                capture_output=True, text=True, timeout=10
            )
            status.installed = result.returncode == 0
            status.enabled = result.stdout.strip() == "enabled"
            
            result = subprocess.run(
                ["systemctl", "is-active", "openclaw"],
                capture_output=True, text=True, timeout=10
            )
            status.running = result.stdout.strip() == "active"
        except Exception:
            # 检查 cron
            try:
                result = subprocess.run(
                    ["crontab", "-l"],
                    capture_output=True, text=True, timeout=10
                )
                status.installed = "openclaw" in result.stdout
            except Exception:
                pass
        
        return status
    
    def _run_command(self, cmd: list) -> bool:
        """执行命令并返回是否成功"""
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=30)
            return result.returncode == 0
        except Exception:
            return False
