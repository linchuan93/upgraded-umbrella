"""
OpenClaw 一键安装程序 - 依赖管理模块

功能：
1. 检测并安装 Node.js >= v22.14+
2. 检测并安装 Python 3.10+
3. 检测并安装 Git
4. 静默安装（不弹出安装向导窗口）
5. 支持断点续装和版本升级
6. 自动选择国内镜像源加速下载

设计原则：
- 每个依赖的安装是幂等的（重复运行不会出错）
- 安装过程全程静默，通过回调函数报告进度
- 网络下载失败时自动切换镜像源重试
"""

import os
import sys
import subprocess
import shutil
import logging
import tempfile
import time
from typing import Optional, Callable, Dict, Tuple
from dataclasses import dataclass

from .platform_detector import (
    PlatformInfo, OSType, ArchType,
    get_node_download_url, get_python_download_url,
    is_version_sufficient, get_min_disk_space_required
)

logger = logging.getLogger("OpenClawInstaller")

# ── 依赖版本要求 ──
REQUIRED_NODE_VERSION = "22.14.0"
REQUIRED_PYTHON_VERSION = "3.10.0"
REQUIRED_GIT_VERSION = "2.30.0"

# ── 国内镜像 URL ──
NODE_MIRRORS = {
    "npmmirror": "https://npmmirror.com/mirrors/node",
    "huawei": "https://repo.huaweicloud.com/nodejs",
}

PYTHON_MIRRORS = {
    "huawei": "https://repo.huaweicloud.com/python",
    "tsinghua": "https://mirrors.tuna.tsinghua.edu.cn/python",
}


@dataclass
class DependencyStatus:
    """依赖项状态数据类"""
    name: str
    installed: bool = False
    current_version: str = ""
    required_version: str = ""
    needs_install: bool = False
    needs_update: bool = False
    install_path: str = ""


class DependencyManager:
    """
    依赖管理器
    
    负责：
    1. 检测所有必需依赖的安装状态
    2. 自动下载并静默安装缺失或版本不足的依赖
    3. 通过回调函数向 GUI 报告安装进度
    
    用法:
        dm = DependencyManager(platform_info)
        dm.check_all()
        dm.install_missing(progress_callback)
    """
    
    def __init__(self, platform_info: PlatformInfo):
        """
        初始化依赖管理器
        
        Args:
            platform_info: 平台信息对象
        """
        self.platform = platform_info
        self.statuses: Dict[str, DependencyStatus] = {}
        self._use_china_mirror = False  # 是否使用国内镜像
        
    def check_all(self) -> Dict[str, DependencyStatus]:
        """
        检测所有必需依赖的状态
        
        Returns:
            Dict[str, DependencyStatus]: 依赖名称到状态的映射
        """
        logger.info("开始检测所有依赖...")
        
        self.statuses["nodejs"] = self._check_nodejs()
        self.statuses["python"] = self._check_python()
        self.statuses["git"] = self._check_git()
        
        # 检测磁盘空间
        min_space = get_min_disk_space_required()
        if self.platform.disk_space_gb >= 0 and self.platform.disk_space_gb < min_space:
            logger.warning(
                f"磁盘空间不足: 当前 {self.platform.disk_space_gb:.1f}GB, "
                f"需要至少 {min_space:.1f}GB"
            )
        
        for name, status in self.statuses.items():
            state = "已安装" if status.installed else "未安装"
            version_info = f" (v{status.current_version})" if status.current_version else ""
            need = ""
            if status.needs_install:
                need = " [需要安装]"
            elif status.needs_update:
                need = f" [需要升级到 v{status.required_version}]"
            logger.info(f"  {name}: {state}{version_info}{need}")
        
        return self.statuses
    
    def install_missing(self, progress_callback: Optional[Callable[[str, int], None]] = None) -> bool:
        """
        安装所有缺失或需要更新的依赖
        
        Args:
            progress_callback: 进度回调函数，参数为 (步骤描述, 百分比)
            
        Returns:
            bool: 所有依赖是否安装成功
        """
        all_success = True
        
        for name, status in self.statuses.items():
            if not status.needs_install and not status.needs_update:
                continue
            
            logger.info(f"开始安装/更新 {name}...")
            
            if progress_callback:
                progress_callback(f"安装 {name} 中...", 0)
            
            try:
                if name == "nodejs":
                    success = self._install_nodejs(progress_callback)
                elif name == "python":
                    success = self._install_python(progress_callback)
                elif name == "git":
                    success = self._install_git(progress_callback)
                else:
                    logger.warning(f"未知依赖: {name}")
                    continue
                
                if success:
                    logger.info(f"{name} 安装成功")
                    if progress_callback:
                        progress_callback(f"{name} 安装完成", 100)
                else:
                    logger.error(f"{name} 安装失败")
                    all_success = False
                    
            except Exception as e:
                logger.error(f"{name} 安装异常: {e}")
                all_success = False
        
        return all_success
    
    # ── Node.js 相关 ──
    
    def _check_nodejs(self) -> DependencyStatus:
        """
        检测 Node.js 安装状态和版本
        
        Returns:
            DependencyStatus: Node.js 的状态信息
        """
        status = DependencyStatus(
            name="nodejs",
            required_version=REQUIRED_NODE_VERSION
        )
        
        node_path = shutil.which("node") or self.platform.node_path
        if not node_path:
            status.needs_install = True
            return status
        
        try:
            result = subprocess.run(
                [node_path, "--version"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                version = result.stdout.strip().lstrip("v")
                status.installed = True
                status.current_version = version
                status.install_path = node_path
                status.needs_update = not is_version_sufficient(version, REQUIRED_NODE_VERSION)
                status.needs_install = False
        except Exception as e:
            logger.debug(f"Node.js 检测异常: {e}")
            status.needs_install = True
        
        return status
    
    def _install_nodejs(self, progress_callback: Optional[Callable] = None) -> bool:
        """
        下载并静默安装 Node.js
        
        安装策略：
        - Windows: 下载 .msi 安装包，使用 msiexec /quiet 静默安装
        - macOS: 下载 .pkg 安装包，使用 installer -pkg 静默安装
        - Linux: 下载 .tar.xz 压缩包，手动解压到 /usr/local
        
        Args:
            progress_callback: 进度回调
            
        Returns:
            bool: 是否安装成功
        """
        version = f"v{REQUIRED_NODE_VERSION}"
        
        if progress_callback:
            progress_callback("正在下载 Node.js...", 20)
        
        # 选择下载 URL（优先国内镜像）
        try:
            url = get_node_download_url(version, self.platform.arch, self.platform.os_type)
            if self._use_china_mirror:
                # 替换为国内镜像 URL
                mirror_base = NODE_MIRRORS["npmmirror"]
                url = url.replace("https://nodejs.org/dist", mirror_base)
        except ValueError as e:
            logger.error(f"无法构建 Node.js 下载 URL: {e}")
            return False
        
        # 下载到临时目录
        download_dir = tempfile.mkdtemp(prefix="openclaw_nodejs_")
        filename = url.split("/")[-1]
        download_path = os.path.join(download_dir, filename)
        
        try:
            if not self._download_file(url, download_path, progress_callback):
                return False
            
            if progress_callback:
                progress_callback("正在安装 Node.js...", 60)
            
            # 根据平台执行安装
            if self.platform.os_type == OSType.WINDOWS:
                return self._install_nodejs_windows(download_path)
            elif self.platform.os_type == OSType.MACOS:
                return self._install_nodejs_macos(download_path)
            elif self.platform.os_type == OSType.LINUX:
                return self._install_nodejs_linux(download_path)
            else:
                logger.error(f"不支持的平台: {self.platform.os_type}")
                return False
                
        except Exception as e:
            logger.error(f"Node.js 安装异常: {e}")
            return False
        finally:
            # 清理临时文件
            try:
                shutil.rmtree(download_dir, ignore_errors=True)
            except Exception:
                pass
    
    def _install_nodejs_windows(self, msi_path: str) -> bool:
        """Windows: 使用 msiexec 静默安装 .msi 包"""
        try:
            cmd = [
                "msiexec", "/i", msi_path,
                "/quiet", "/norestart",
                "ADDLOCAL=ALL"
            ]
            result = subprocess.run(cmd, capture_output=True, timeout=600)
            if result.returncode == 0:
                # 刷新 PATH 环境变量
                self._refresh_path()
                return True
            else:
                logger.error(f"msiexec 安装失败，返回码: {result.returncode}")
                return False
        except subprocess.TimeoutExpired:
            logger.error("Node.js 安装超时")
            return False
    
    def _install_nodejs_macos(self, pkg_path: str) -> bool:
        """macOS: 使用 installer 命令静默安装 .pkg 包"""
        try:
            cmd = ["sudo", "installer", "-pkg", pkg_path, "-target", "/"]
            result = subprocess.run(cmd, capture_output=True, timeout=600)
            if result.returncode == 0:
                return True
            else:
                logger.error(f"installer 安装失败，返回码: {result.returncode}")
                # 降级：尝试使用 brew
                return self._install_via_brew("node@22")
        except subprocess.TimeoutExpired:
            logger.error("Node.js 安装超时")
            return False
    
    def _install_nodejs_linux(self, tar_path: str) -> bool:
        """Linux: 解压 .tar.xz 到 /usr/local"""
        try:
            cmd = [
                "tar", "-xJf", tar_path,
                "-C", "/usr/local", "--strip-components=1"
            ]
            result = subprocess.run(cmd, capture_output=True, timeout=300)
            if result.returncode == 0:
                # 创建符号链接
                self._create_symlinks("/usr/local/bin")
                return True
            else:
                logger.error(f"解压 Node.js 失败，返回码: {result.returncode}")
                # 降级：尝试使用包管理器
                return self._install_via_package_manager("nodejs")
        except subprocess.TimeoutExpired:
            logger.error("Node.js 解压超时")
            return False
    
    # ── Python 相关 ──
    
    def _check_python(self) -> DependencyStatus:
        """
        检测 Python 安装状态和版本
        
        Returns:
            DependencyStatus: Python 的状态信息
        """
        status = DependencyStatus(
            name="python",
            required_version=REQUIRED_PYTHON_VERSION
        )
        
        python_path = shutil.which("python3") or shutil.which("python") or self.platform.python_path
        if not python_path:
            status.needs_install = True
            return status
        
        try:
            result = subprocess.run(
                [python_path, "--version"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                # 输出格式: "Python 3.12.0"
                version_str = result.stdout.strip().split()[-1]
                status.installed = True
                status.current_version = version_str
                status.install_path = python_path
                status.needs_update = not is_version_sufficient(version_str, REQUIRED_PYTHON_VERSION)
                status.needs_install = False
        except Exception as e:
            logger.debug(f"Python 检测异常: {e}")
            status.needs_install = True
        
        return status
    
    def _install_python(self, progress_callback: Optional[Callable] = None) -> bool:
        """
        下载并静默安装 Python
        
        安装策略：
        - Windows: 下载 .exe 安装包，使用 /quiet InstallAllUsers=1 静默安装
        - macOS: 下载 .pkg 安装包或使用 brew install python3
        - Linux: 优先使用包管理器安装（apt/yum/dnf）
        
        Args:
            progress_callback: 进度回调
            
        Returns:
            bool: 是否安装成功
        """
        if progress_callback:
            progress_callback("正在下载 Python...", 20)
        
        # Linux 优先使用包管理器
        if self.platform.os_type == OSType.LINUX:
            return self._install_python_linux(progress_callback)
        
        version = REQUIRED_PYTHON_VERSION
        
        try:
            url = get_python_download_url(version, self.platform.arch, self.platform.os_type)
            if self._use_china_mirror:
                mirror_base = PYTHON_MIRRORS["huawei"]
                url = url.replace("https://www.python.org/ftp/python", mirror_base)
        except ValueError as e:
            logger.error(f"无法构建 Python 下载 URL: {e}")
            return False
        
        download_dir = tempfile.mkdtemp(prefix="openclaw_python_")
        filename = url.split("/")[-1]
        download_path = os.path.join(download_dir, filename)
        
        try:
            if not self._download_file(url, download_path, progress_callback):
                return False
            
            if progress_callback:
                progress_callback("正在安装 Python...", 60)
            
            if self.platform.os_type == OSType.WINDOWS:
                return self._install_python_windows(download_path)
            elif self.platform.os_type == OSType.MACOS:
                return self._install_python_macos(download_path)
            else:
                return False
                
        except Exception as e:
            logger.error(f"Python 安装异常: {e}")
            return False
        finally:
            try:
                shutil.rmtree(download_dir, ignore_errors=True)
            except Exception:
                pass
    
    def _install_python_windows(self, exe_path: str) -> bool:
        """Windows: 使用 /quiet 静默安装 Python"""
        try:
            cmd = [
                exe_path,
                "/quiet", "InstallAllUsers=1",
                "PrependPath=1", "Include_pip=1",
                "Include_launcher=0"
            ]
            result = subprocess.run(cmd, capture_output=True, timeout=600)
            if result.returncode == 0:
                self._refresh_path()
                return True
            else:
                logger.error(f"Python 安装失败，返回码: {result.returncode}")
                return False
        except subprocess.TimeoutExpired:
            logger.error("Python 安装超时")
            return False
    
    def _install_python_macos(self, pkg_path: str) -> bool:
        """macOS: 使用 installer 或 brew 安装 Python"""
        try:
            cmd = ["sudo", "installer", "-pkg", pkg_path, "-target", "/"]
            result = subprocess.run(cmd, capture_output=True, timeout=600)
            if result.returncode == 0:
                return True
            else:
                return self._install_via_brew("python@3.12")
        except subprocess.TimeoutExpired:
            return self._install_via_brew("python@3.12")
    
    def _install_python_linux(self, progress_callback: Optional[Callable] = None) -> bool:
        """Linux: 使用包管理器安装 Python"""
        if progress_callback:
            progress_callback("正在通过包管理器安装 Python...", 50)
        return self._install_via_package_manager("python3")
    
    # ── Git 相关 ──
    
    def _check_git(self) -> DependencyStatus:
        """
        检测 Git 安装状态和版本
        
        Returns:
            DependencyStatus: Git 的状态信息
        """
        status = DependencyStatus(
            name="git",
            required_version=REQUIRED_GIT_VERSION
        )
        
        git_path = shutil.which("git") or self.platform.git_path
        if not git_path:
            status.needs_install = True
            return status
        
        try:
            result = subprocess.run(
                [git_path, "--version"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                # 输出格式: "git version 2.40.0"
                version_str = result.stdout.strip().split()[-1]
                status.installed = True
                status.current_version = version_str
                status.install_path = git_path
                status.needs_update = not is_version_sufficient(version_str, REQUIRED_GIT_VERSION)
                status.needs_install = False
        except Exception as e:
            logger.debug(f"Git 检测异常: {e}")
            status.needs_install = True
        
        return status
    
    def _install_git(self, progress_callback: Optional[Callable] = None) -> bool:
        """
        安装 Git
        
        安装策略：
        - Windows: 使用 winget 或下载 Git for Windows 安装包
        - macOS: 使用 xcode-select --install 或 brew install git
        - Linux: 使用包管理器安装
        
        Args:
            progress_callback: 进度回调
            
        Returns:
            bool: 是否安装成功
        """
        if progress_callback:
            progress_callback("正在安装 Git...", 30)
        
        if self.platform.os_type == OSType.WINDOWS:
            return self._install_git_windows(progress_callback)
        elif self.platform.os_type == OSType.MACOS:
            return self._install_git_macos(progress_callback)
        elif self.platform.os_type == OSType.LINUX:
            return self._install_git_linux(progress_callback)
        return False
    
    def _install_git_windows(self, progress_callback: Optional[Callable] = None) -> bool:
        """Windows: 使用 winget 安装 Git"""
        # 优先尝试 winget
        winget = shutil.which("winget")
        if winget:
            try:
                result = subprocess.run(
                    ["winget", "install", "--id", "Git.Git", "--accept-package-agreements",
                     "--accept-source-agreements", "--silent"],
                    capture_output=True, timeout=300
                )
                if result.returncode == 0:
                    self._refresh_path()
                    return True
            except Exception:
                pass
        
        # 降级：下载安装包
        url = "https://github.com/git-for-windows/git/releases/latest/download/Git-2.47.1-64-bit.exe"
        if self._use_china_mirror:
            url = "https://mirrors.huaweicloud.com/git-for-windows/2.47.1.windows.1/Git-2.47.1-64-bit.exe"
        
        download_dir = tempfile.mkdtemp(prefix="openclaw_git_")
        download_path = os.path.join(download_dir, "git_installer.exe")
        
        try:
            if not self._download_file(url, download_path, progress_callback):
                return False
            cmd = [download_path, "/VERYSILENT", "/NORESTART", "/NOCANCEL", "/SP-"]
            result = subprocess.run(cmd, capture_output=True, timeout=600)
            if result.returncode == 0:
                self._refresh_path()
                return True
        except Exception as e:
            logger.error(f"Git 安装异常: {e}")
        finally:
            shutil.rmtree(download_dir, ignore_errors=True)
        return False
    
    def _install_git_macos(self, progress_callback: Optional[Callable] = None) -> bool:
        """macOS: 使用 xcode-select 或 brew 安装 Git"""
        # 优先尝试 xcode-select
        try:
            result = subprocess.run(
                ["xcode-select", "--install"],
                capture_output=True, timeout=60
            )
            # 返回码 1 通常表示已安装
            if result.returncode in (0, 1):
                if shutil.which("git"):
                    return True
        except Exception:
            pass
        
        # 降级：使用 brew
        return self._install_via_brew("git")
    
    def _install_git_linux(self, progress_callback: Optional[Callable] = None) -> bool:
        """Linux: 使用包管理器安装 Git"""
        return self._install_via_package_manager("git")
    
    # ── 通用辅助方法 ──
    
    def set_china_mirror(self, enabled: bool) -> None:
        """
        设置是否使用国内镜像源
        
        Args:
            enabled: 是否启用国内镜像
        """
        self._use_china_mirror = enabled
        logger.info(f"国内镜像源: {'已启用' if enabled else '已禁用'}")
    
    def _download_file(self, url: str, dest_path: str,
                       progress_callback: Optional[Callable] = None) -> bool:
        """
        下载文件（支持国内镜像切换和重试）
        
        下载策略：
        1. 先尝试官方源
        2. 若失败，自动切换到国内镜像源
        3. 最多重试 3 次
        
        Args:
            url: 下载 URL
            dest_path: 目标文件路径
            progress_callback: 进度回调
            
        Returns:
            bool: 是否下载成功
        """
        # 使用 urllib（Python 内置，不需要额外依赖）
        import urllib.request
        import urllib.error
        
        max_retries = 3
        urls_to_try = [url]
        
        # 如果 URL 是官方源，添加国内镜像备选
        if "nodejs.org" in url and self._use_china_mirror:
            mirror_url = url.replace("https://nodejs.org/dist", NODE_MIRRORS["npmmirror"])
            urls_to_try.append(mirror_url)
        elif "python.org" in url and self._use_china_mirror:
            mirror_url = url.replace("https://www.python.org/ftp/python", PYTHON_MIRRORS["huawei"])
            urls_to_try.append(mirror_url)
        
        for attempt_url in urls_to_try:
            for attempt in range(max_retries):
                try:
                    if progress_callback:
                        progress_callback(f"正在下载 ({attempt + 1}/{max_retries})...", 30)
                    
                    logger.info(f"下载: {attempt_url} (尝试 {attempt + 1}/{max_retries})")
                    
                    # 使用 urllib 下载（内置模块，无额外依赖）
                    urllib.request.urlretrieve(attempt_url, dest_path)
                    
                    # 验证文件大小
                    if os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
                        logger.info(f"下载完成: {dest_path}")
                        return True
                    else:
                        logger.warning("下载文件为空，重试中...")
                        
                except urllib.error.URLError as e:
                    logger.warning(f"下载失败 (URL: {attempt_url}): {e}")
                except Exception as e:
                    logger.warning(f"下载异常: {e}")
                
                # 等待后重试
                time.sleep(2 ** attempt)
        
        logger.error(f"所有下载尝试均失败: {url}")
        return False
    
    def _install_via_brew(self, package: str) -> bool:
        """
        使用 Homebrew 安装包（macOS）
        
        Args:
            package: Homebrew 包名
            
        Returns:
            bool: 是否安装成功
        """
        brew = shutil.which("brew")
        if not brew:
            logger.warning("Homebrew 未安装，尝试安装 Homebrew...")
            try:
                # 安装 Homebrew
                result = subprocess.run(
                    ['/bin/bash', '-c',
                     '$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)'],
                    capture_output=True, timeout=600
                )
                brew = shutil.which("brew")
                if not brew:
                    logger.error("Homebrew 安装失败")
                    return False
            except Exception as e:
                logger.error(f"Homebrew 安装异常: {e}")
                return False
        
        try:
            cmd = [brew, "install", package]
            result = subprocess.run(cmd, capture_output=True, timeout=600)
            return result.returncode == 0
        except Exception as e:
            logger.error(f"brew install {package} 异常: {e}")
            return False
    
    def _install_via_package_manager(self, package: str) -> bool:
        """
        使用系统包管理器安装包（Linux）
        
        自动检测可用的包管理器（apt/yum/dnf/pacman）。
        
        Args:
            package: 包名
            
        Returns:
            bool: 是否安装成功
        """
        package_managers = {
            "apt": ["sudo", "apt-get", "install", "-y"],
            "yum": ["sudo", "yum", "install", "-y"],
            "dnf": ["sudo", "dnf", "install", "-y"],
            "pacman": ["sudo", "pacman", "-S", "--noconfirm"],
        }
        
        # 包名映射（不同包管理器的包名可能不同）
        package_name_map = {
            "nodejs": {"apt": "nodejs", "yum": "nodejs", "dnf": "nodejs", "pacman": "nodejs"},
            "python3": {"apt": "python3", "yum": "python3", "dnf": "python3", "pacman": "python"},
            "git": {"apt": "git", "yum": "git", "dnf": "git", "pacman": "git"},
        }
        
        for pm_name, pm_cmd in package_managers.items():
            if shutil.which(pm_cmd[1]):  # 检查包管理器是否存在
                try:
                    # 获取适配的包名
                    actual_package = package_name_map.get(package, {}).get(pm_name, package)
                    cmd = pm_cmd + [actual_package]
                    
                    logger.info(f"使用 {pm_name} 安装 {actual_package}...")
                    result = subprocess.run(cmd, capture_output=True, timeout=600)
                    
                    if result.returncode == 0:
                        logger.info(f"{package} 通过 {pm_name} 安装成功")
                        return True
                    else:
                        logger.warning(f"{pm_name} 安装 {package} 失败: {result.stderr.decode()[:200]}")
                except Exception as e:
                    logger.warning(f"{pm_name} 安装异常: {e}")
        
        logger.error(f"无可用的包管理器来安装 {package}")
        return False
    
    def _refresh_path(self) -> None:
        """
        刷新 PATH 环境变量
        
        安装新软件后，当前进程的 PATH 可能未更新。
        此方法从系统重新读取 PATH 配置。
        """
        if self.platform.os_type == OSType.WINDOWS:
            try:
                import winreg  # type: ignore
                key = winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"
                )
                path_value, _ = winreg.QueryValueEx(key, "Path")
                os.environ["Path"] = path_value
                winreg.CloseKey(key)
            except Exception:
                pass
        else:
            # macOS/Linux: 重新加载 shell 配置
            for rc_file in [".zshrc", ".bashrc", ".bash_profile", ".profile"]:
                rc_path = os.path.expanduser(f"~/{rc_file}")
                if os.path.exists(rc_path):
                    try:
                        result = subprocess.run(
                            [self.platform.shell, "-c", f"source {rc_path} && echo $PATH"],
                            capture_output=True, text=True, timeout=5
                        )
                        if result.returncode == 0 and result.stdout.strip():
                            os.environ["PATH"] = result.stdout.strip()
                            break
                    except Exception:
                        continue
    
    def _create_symlinks(self, bin_dir: str) -> None:
        """
        在指定目录创建符号链接
        
        Args:
            bin_dir: 目标 bin 目录
        """
        # 此方法主要用于 Linux 下手动解压 Node.js 后创建链接
        pass
