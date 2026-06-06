"""
OpenClaw 一键安装程序 - 平台检测模块

功能：
1. 检测当前操作系统类型（Windows/macOS/Linux）及版本
2. 检测 CPU 架构（x64/ARM64）
3. 提供平台相关的路径和命令适配
4. 检测磁盘空间是否充足
5. 检测杀毒软件/防火墙状态

设计原则：
- 所有平台信息在程序启动时一次性收集，后续通过 PlatformInfo 对象访问
- 提供统一的平台抽象层，上层代码无需关心平台差异
"""

import os
import sys
import platform
import shutil
import subprocess
import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, List
from enum import Enum


logger = logging.getLogger("OpenClawInstaller")


class OSType(Enum):
    """操作系统类型枚举"""
    WINDOWS = "windows"
    MACOS = "macos"
    LINUX = "linux"
    UNKNOWN = "unknown"


class ArchType(Enum):
    """CPU 架构枚举"""
    X64 = "x64"
    ARM64 = "arm64"
    X86 = "x86"
    UNKNOWN = "unknown"


@dataclass
class PlatformInfo:
    """
    平台信息数据类
    
    包含当前系统的完整信息，供其他模块使用。
    在程序启动时由 detect_platform() 一次性填充。
    """
    os_type: OSType = OSType.UNKNOWN
    arch: ArchType = ArchType.UNKNOWN
    os_version: str = ""
    os_name: str = ""
    is_admin: bool = False
    disk_space_gb: float = 0.0
    has_firewall: bool = False
    firewall_name: str = ""
    antivirus_detected: List[str] = field(default_factory=list)
    home_dir: str = ""
    temp_dir: str = ""
    shell: str = ""
    python_path: str = ""
    node_path: str = ""
    git_path: str = ""


def detect_platform() -> PlatformInfo:
    """
    检测当前平台信息
    
    返回一个包含完整平台信息的 PlatformInfo 对象。
    此函数应在程序启动时调用一次，结果可缓存复用。
    
    Returns:
        PlatformInfo: 包含当前系统完整信息的数据对象
    """
    info = PlatformInfo()
    
    # ── 1. 检测操作系统类型 ──
    system = platform.system().lower()
    if system == "windows":
        info.os_type = OSType.WINDOWS
    elif system == "darwin":
        info.os_type = OSType.MACOS
    elif system == "linux":
        info.os_type = OSType.LINUX
    else:
        info.os_type = OSType.UNKNOWN
        logger.warning(f"未知操作系统: {system}")
    
    # ── 2. 检测操作系统版本 ──
    info.os_version = platform.version()
    info.os_name = platform.platform()
    
    # ── 3. 检测 CPU 架构 ──
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64", "x64"):
        info.arch = ArchType.X64
    elif machine in ("arm64", "aarch64"):
        info.arch = ArchType.ARM64
    elif machine in ("i386", "i686", "x86"):
        info.arch = ArchType.X86
    else:
        info.arch = ArchType.UNKNOWN
        logger.warning(f"未知 CPU 架构: {machine}")
    
    # ── 4. 检测管理员权限 ──
    info.is_admin = _check_admin_privilege(info.os_type)
    
    # ── 5. 检测磁盘空间 ──
    info.disk_space_gb = _check_disk_space(info.os_type)
    
    # ── 6. 检测防火墙和杀毒软件 ──
    _detect_security_software(info)
    
    # ── 7. 设置通用路径 ──
    info.home_dir = os.path.expanduser("~")
    info.temp_dir = _get_temp_dir(info.os_type)
    info.shell = _detect_shell(info.os_type)
    
    # ── 8. 检测已安装的工具路径 ──
    info.python_path = shutil.which("python3") or shutil.which("python") or ""
    info.node_path = shutil.which("node") or ""
    info.git_path = shutil.which("git") or ""
    
    logger.info(f"平台检测完成: {info.os_type.value}/{info.arch.value}, "
                f"版本: {info.os_version}, 管理员: {info.is_admin}, "
                f"磁盘: {info.disk_space_gb:.1f}GB")
    
    return info


def _check_admin_privilege(os_type: OSType) -> bool:
    """
    检测当前是否拥有管理员/超级用户权限
    
    Args:
        os_type: 操作系统类型
        
    Returns:
        bool: 是否拥有管理员权限
    """
    try:
        if os_type == OSType.WINDOWS:
            # Windows: 尝试访问需要管理员权限的路径
            import ctypes
            return ctypes.windll.shell32.IsUserAnAdmin() != 0  # type: ignore
        elif os_type in (OSType.MACOS, OSType.LINUX):
            # macOS/Linux: 检查 UID
            return os.geteuid() == 0
    except Exception as e:
        logger.debug(f"管理员权限检测异常: {e}")
    return False


def _check_disk_space(os_type: OSType) -> float:
    """
    检测安装目标路径的可用磁盘空间
    
    需要至少 2GB 可用空间才能继续安装。
    
    Args:
        os_type: 操作系统类型
        
    Returns:
        float: 可用磁盘空间（GB）
    """
    try:
        if os_type == OSType.WINDOWS:
            # Windows: 使用 ctypes 获取磁盘信息
            import ctypes
            free_bytes = ctypes.c_ulonglong(0)
            ctypes.windll.kernel32.GetDiskFreeSpaceExW(  # type: ignore
                ctypes.c_wchar_p("C:\\"), None, None, ctypes.pointer(free_bytes)
            )
            return free_bytes.value / (1024 ** 3)
        else:
            # macOS/Linux: 使用 os.statvfs
            target = "/usr/local" if os.path.exists("/usr/local") else "/"
            stat = os.statvfs(target)
            return (stat.f_bavail * stat.f_frsize) / (1024 ** 3)
    except Exception as e:
        logger.warning(f"磁盘空间检测失败: {e}")
        return -1.0


def _detect_security_software(info: PlatformInfo) -> None:
    """
    检测系统上运行的防火墙和杀毒软件
    
    在 Windows 上通过 WMI 查询；在 macOS/Linux 上通过进程列表检测。
    检测结果会写入 PlatformInfo 对象。
    
    Args:
        info: PlatformInfo 对象（会被就地修改）
    """
    info.antivirus_detected = []
    
    if info.os_type == OSType.WINDOWS:
        _detect_windows_security(info)
    elif info.os_type == OSType.MACOS:
        _detect_macos_security(info)
    elif info.os_type == OSType.LINUX:
        _detect_linux_security(info)


def _detect_windows_security(info: PlatformInfo) -> None:
    """检测 Windows 防火墙和杀毒软件"""
    info.has_firewall = True  # Windows 默认开启防火墙
    info.firewall_name = "Windows Defender Firewall"
    
    # 常见杀毒软件进程名
    av_processes = {
        "MsMpEng": "Windows Defender",
        "avp": "Kaspersky",
        "bdagent": "Bitdefender",
        "McAfee": "McAfee",
        "avast": "Avast",
        "Avg": "AVG",
        "norton": "Norton",
        "360sd": "360安全卫士",
        " ZhuDongFangYu": "360主动防御",
        "HipsDaemon": "火绒",
        "wsctrl": "火绒",
    }
    
    try:
        result = subprocess.run(
            ["tasklist", "/FO", "CSV"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                for proc_name, av_name in av_processes.items():
                    if proc_name.lower() in line.lower():
                        if av_name not in info.antivirus_detected:
                            info.antivirus_detected.append(av_name)
    except Exception as e:
        logger.debug(f"Windows 杀毒软件检测异常: {e}")


def _detect_macos_security(info: PlatformInfo) -> None:
    """检测 macOS 防火墙和杀毒软件"""
    try:
        result = subprocess.run(
            ["defaults", "read", "/Library/Preferences/com.apple.alf", "globalstate"],
            capture_output=True, text=True, timeout=5
        )
        info.has_firewall = result.stdout.strip() == "1"
        info.firewall_name = "macOS Application Firewall"
    except Exception:
        info.has_firewall = False
    
    # 检测常见 macOS 杀毒软件
    av_apps = ["Norton", "Kaspersky", "Bitdefender", "Sophos", "Malwarebytes", "ESET"]
    try:
        result = subprocess.run(
            ["ls", "/Applications"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            for app in av_apps:
                if app.lower() in result.stdout.lower():
                    info.antivirus_detected.append(app)
    except Exception:
        pass


def _detect_linux_security(info: PlatformInfo) -> None:
    """检测 Linux 防火墙和杀毒软件"""
    # 检测 iptables / ufw / firewalld
    for cmd in ["ufw", "firewalld", "iptables"]:
        if shutil.which(cmd):
            info.has_firewall = True
            info.firewall_name = cmd
            break
    
    # 检测 ClamAV
    if shutil.which("clamd") or shutil.which("clamav"):
        info.antivirus_detected.append("ClamAV")


def _get_temp_dir(os_type: OSType) -> str:
    """
    获取临时文件目录
    
    Args:
        os_type: 操作系统类型
        
    Returns:
        str: 临时目录的绝对路径
    """
    if os_type == OSType.WINDOWS:
        temp = os.environ.get("TEMP", os.environ.get("TMP", ""))
        if temp:
            return temp
    return "/tmp" if os_type != OSType.WINDOWS else os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "Temp")


def _detect_shell(os_type: OSType) -> str:
    """
    检测当前可用的 Shell
    
    Args:
        os_type: 操作系统类型
        
    Returns:
        str: Shell 可执行文件路径
    """
    if os_type == OSType.WINDOWS:
        # Windows 优先使用 PowerShell
        pwsh = shutil.which("pwsh") or shutil.which("powershell")
        return pwsh or "cmd.exe"
    else:
        # macOS/Linux 优先使用 bash
        for shell in ["bash", "zsh", "sh"]:
            path = shutil.which(shell)
            if path:
                return path
        return "/bin/sh"


def get_node_download_url(version: str, arch: ArchType, os_type: OSType) -> str:
    """
    根据平台信息构建 Node.js 下载 URL
    
    Args:
        version: Node.js 版本号（如 "v22.14.0"）
        arch: CPU 架构
        os_type: 操作系统类型
        
    Returns:
        str: Node.js 安装包下载 URL
    """
    # 官方源
    base_url = f"https://nodejs.org/dist/{version}"
    
    # 文件名映射
    if os_type == OSType.WINDOWS:
        arch_str = "x64" if arch == ArchType.X64 else "x86"
        filename = f"node-{version}-{arch_str}.msi"
    elif os_type == OSType.MACOS:
        if arch == ArchType.ARM64:
            filename = f"node-{version}-darwin-arm64.pkg"
        else:
            filename = f"node-{version}-darwin-x64.pkg"
    elif os_type == OSType.LINUX:
        arch_str = "x64" if arch == ArchType.X64 else "arm64"
        filename = f"node-{version}-linux-{arch_str}.tar.xz"
    else:
        raise ValueError(f"不支持的平台: {os_type}")
    
    return f"{base_url}/{filename}"


def get_python_download_url(version: str, arch: ArchType, os_type: OSType) -> str:
    """
    根据平台信息构建 Python 下载 URL
    
    Args:
        version: Python 版本号（如 "3.12.0"）
        arch: CPU 架构
        os_type: 操作系统类型
        
    Returns:
        str: Python 安装包下载 URL
    """
    base_url = f"https://www.python.org/ftp/python/{version}"
    
    if os_type == OSType.WINDOWS:
        arch_str = "amd64" if arch == ArchType.X64 else ""
        filename = f"python-{version}{('-' + arch_str) if arch_str else ''}.exe"
    elif os_type == OSType.MACOS:
        if arch == ArchType.ARM64:
            filename = f"python-{version}-macos11.pkg"
        else:
            filename = f"python-{version}-macos11.pkg"
    elif os_type == OSType.LINUX:
        # Linux 通常通过包管理器安装，这里提供源码链接作为后备
        filename = f"Python-{version}.tgz"
    else:
        raise ValueError(f"不支持的平台: {os_type}")
    
    return f"{base_url}/{filename}"


def get_min_disk_space_required() -> float:
    """
    获取安装所需的最小磁盘空间（GB）
    
    包括 Node.js (~200MB)、Python (~150MB)、Git (~50MB)、
    OpenClaw (~100MB) 及临时文件 (~500MB) 的估算总和。
    
    Returns:
        float: 最小所需磁盘空间（GB）
    """
    return 2.0  # 2 GB


def is_version_sufficient(current: str, required: str) -> bool:
    """
    比较版本号，判断当前版本是否满足要求
    
    使用简单的分段比较法（如 "22.14.0" vs "22.0.0"）。
    
    Args:
        current: 当前版本号（如 "22.14.0"）
        required: 要求的最低版本号（如 "22.0.0"）
        
    Returns:
        bool: 当前版本是否 >= 要求版本
    """
    def normalize(v: str) -> List[int]:
        # 移除前缀 'v' 并转为整数列表
        v = v.lstrip("vV")
        return [int(x) for x in v.split(".")]
    
    try:
        c = normalize(current)
        r = normalize(required)
        return c >= r
    except (ValueError, TypeError) as e:
        logger.warning(f"版本比较异常: current={current}, required={required}, error={e}")
        return False
