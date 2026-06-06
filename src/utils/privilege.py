"""
OpenClaw 一键安装程序 - 权限管理模块

功能：
1. 检测当前权限级别
2. 自动申请提权（UAC/sudo/pkexec）
3. macOS 辅助功能权限引导
4. 权限不足时的友好提示

设计原则：
- 每个平台使用原生的提权机制
- 提权请求前向用户说明原因
- macOS 辅助功能权限通过 osascript 引导
- 权限被拒绝时提供明确的操作指引
"""

import os
import sys
import subprocess
import shutil
import logging
from typing import Optional

from .logger import get_logger

logger = get_logger("privilege")

# 检测平台（避免循环导入）
_IS_WINDOWS = sys.platform == "win32"
_IS_MACOS = sys.platform == "darwin"
_IS_LINUX = sys.platform.startswith("linux")


def check_admin() -> bool:
    """
    检测当前是否拥有管理员/root 权限
    
    Returns:
        bool: 是否拥有管理员权限
    """
    try:
        if _IS_WINDOWS:
            import ctypes
            return ctypes.windll.shell32.IsUserAnAdmin() != 0  # type: ignore
        else:
            return os.geteuid() == 0
    except Exception:
        return False


def request_elevation(reason: str = "安装程序需要管理员权限来完成系统级操作") -> bool:
    """
    请求权限提升
    
    根据平台使用不同机制：
    - Windows: 通过 UAC 重新以管理员身份启动
    - macOS: 通过 osascript 弹窗请求 sudo
    - Linux: 通过 pkexec 或 gksu 请求提权
    
    Args:
        reason: 提权原因（显示给用户）
        
    Returns:
        bool: 是否成功提权
    """
    if check_admin():
        return True
    
    logger.info(f"请求权限提升: {reason}")
    
    if _IS_WINDOWS:
        return _elevate_windows(reason)
    elif _IS_MACOS:
        return _elevate_macos(reason)
    elif _IS_LINUX:
        return _elevate_linux(reason)
    
    return False


def _elevate_windows(reason: str) -> bool:
    """
    Windows: 通过 UAC 重新启动当前脚本
    
    使用 ctypes 调用 ShellExecuteW 以管理员身份运行。
    
    Args:
        reason: 提权原因
        
    Returns:
        bool: 是否成功发起提权请求
    """
    try:
        import ctypes
        
        # 弹出提示
        result = ctypes.windll.user32.MessageBoxW(  # type: ignore
            0,
            f"{reason}\n\n点击「确定」将以管理员身份重新启动安装程序。",
            "OpenClaw 安装程序 - 需要管理员权限",
            0x01  # MB_OKCANCEL
        )
        
        if result == 1:  # IDOK
            # 以管理员身份重新启动
            ctypes.windll.shell32.ShellExecuteW(  # type: ignore
                None, "runas", sys.executable,
                " ".join([f'"{arg}"' for arg in sys.argv]),
                None, 1  # SW_SHOWNORMAL
            )
            sys.exit(0)
        
        return False
        
    except Exception as e:
        logger.error(f"Windows 提权失败: {e}")
        return False


def _elevate_macos(reason: str) -> bool:
    """
    macOS: 通过 osascript 弹窗请求 sudo 密码
    
    Args:
        reason: 提权原因
        
    Returns:
        bool: 是否成功提权
    """
    try:
        # 使用 osascript 弹出提示
        script = f'''
        display dialog "{reason}" ¬
            with title "OpenClaw 安装程序 - 需要管理员权限" ¬
            buttons {{"取消", "继续"}} default button "继续" ¬
            with icon caution
        '''
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, timeout=60
        )
        
        if result.returncode != 0:
            logger.info("用户取消了提权请求")
            return False
        
        # 验证 sudo 权限
        result = subprocess.run(
            ["sudo", "-v"],  # 验证 sudo 缓存
            capture_output=True, timeout=60
        )
        return result.returncode == 0
        
    except Exception as e:
        logger.error(f"macOS 提权失败: {e}")
        return False


def _elevate_linux(reason: str) -> bool:
    """
    Linux: 通过 pkexec 或 gksu 请求提权
    
    Args:
        reason: 提权原因
        
    Returns:
        bool: 是否成功提权
    """
    # 尝试 pkexec（现代 Linux 桌面环境的标准方式）
    pkexec = shutil.which("pkexec")
    if pkexec:
        try:
            result = subprocess.run(
                [pkexec, "echo", "权限验证成功"],
                capture_output=True, timeout=60
            )
            if result.returncode == 0:
                return True
        except Exception:
            pass
    
    # 尝试 gksu（旧版 Linux）
    gksu = shutil.which("gksu")
    if gksu:
        try:
            result = subprocess.run(
                [gksu, "echo", "权限验证成功"],
                capture_output=True, timeout=60
            )
            if result.returncode == 0:
                return True
        except Exception:
            pass
    
    # 尝试直接 sudo
    try:
        result = subprocess.run(
            ["sudo", "-v"],
            capture_output=True, timeout=60
        )
        return result.returncode == 0
    except Exception:
        pass
    
    # 所有方式都失败
    logger.error(
        "无法自动获取管理员权限。请使用以下方式之一运行安装程序:\n"
        "  1. sudo python3 openclaw_installer.py\n"
        "  2. pkexec python3 openclaw_installer.py"
    )
    return False


def request_macos_accessibility() -> bool:
    """
    引导用户在 macOS 上授予辅助功能权限
    
    某些操作（如模拟键盘输入）需要辅助功能权限。
    此函数通过 osascript 引导用户到系统设置页面。
    
    Returns:
        bool: 用户是否已授权
    """
    if not _IS_MACOS:
        return True
    
    try:
        script = '''
        display dialog "OpenClaw 安装程序需要"辅助功能"权限来完成自动化配置。\\n\\n"
            & "请按以下步骤操作:\\n"
            & "1. 点击"打开系统设置"\\n"
            & "2. 前往"隐私与安全性" → "辅助功能"\\n"
            & "3. 点击 + 号添加 OpenClaw 安装程序\\n"
            & "4. 确保开关已打开\\n\\n"
            & "完成后请点击"继续"。"
            with title "OpenClaw 安装程序 - 需要辅助功能权限"
            buttons {"退出", "打开系统设置", "继续"} default button "继续"
            with icon caution
        '''
        
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, timeout=120
        )
        
        button_map = {1: "退出", 2: "打开系统设置", 3: "继续"}
        # osascript 返回 button returned:继续
        output = result.stdout.decode().strip()
        
        if "打开系统设置" in output:
            # 打开系统设置
            subprocess.run(
                ["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"],
                capture_output=True
            )
            # 等待用户操作后重新提示
            return request_macos_accessibility()
        elif "退出" in output:
            return False
        else:
            return True
            
    except Exception as e:
        logger.error(f"辅助功能权限请求异常: {e}")
        return False


def get_elevation_instructions() -> str:
    """
    获取当前平台的提权操作指引
    
    Returns:
        str: 操作指引文本
    """
    if _IS_WINDOWS:
        return (
            "请右键点击安装程序，选择「以管理员身份运行」。"
            "\n\n如果无法以管理员身份运行，请联系系统管理员获取权限。"
        )
    elif _IS_MACOS:
        return (
            "请在弹出密码框时输入管理员密码。"
            "\n\n如果需要辅助功能权限，请在「系统设置 -> 隐私与安全性 -> 辅助功能」中"
            "为安装程序授权。"
        )
    elif _IS_LINUX:
        return (
            "请使用以下命令重新运行安装程序："
            "\n  sudo ./OpenClaw_Installer.AppImage"
            "\n\n或联系系统管理员获取 sudo 权限。"
        )
    return "请联系系统管理员获取管理员权限。"
