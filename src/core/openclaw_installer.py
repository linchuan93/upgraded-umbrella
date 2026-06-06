"""
OpenClaw 一键安装程序 - OpenClaw 安装模块

功能：
1. 使用官方一键脚本安装 OpenClaw
2. 降级为 npm 全局安装
3. 安装后验证
4. 版本检查与升级

设计原则：
- 优先使用官方推荐的一键安装脚本
- 安装失败时自动降级到 npm 安装
- 所有安装操作支持重试
"""

import subprocess
import shutil
import logging
import os
from typing import Optional, Callable
from dataclasses import dataclass

from .platform_detector import PlatformInfo, OSType
from .network_manager import NetworkManager

logger = logging.getLogger("OpenClawInstaller")

# ── OpenClaw 官方安装脚本 URL ──
OFFICIAL_INSTALL_SCRIPTS = {
    OSType.WINDOWS: "https://openclaw.ai/install.ps1",
    OSType.MACOS: "https://openclaw.ai/install.sh",
    OSType.LINUX: "https://openclaw.ai/install.sh",
}

# ── npm 包名 ──
NPM_PACKAGE_NAME = "@anthropic-ai/openclaw"  # 实际包名可能不同，这里作为示例


@dataclass
class InstallResult:
    """安装结果数据类"""
    success: bool = False
    method: str = ""  # "official_script" / "npm" / "brew"
    version: str = ""
    install_path: str = ""
    error_message: str = ""


class OpenClawInstaller:
    """
    OpenClaw 安装器
    
    负责：
    1. 尝试使用官方一键脚本安装
    2. 失败时降级为 npm 全局安装
    3. 安装后验证
    4. 版本检查
    
    用法:
        installer = OpenClawInstaller(platform_info, network_manager)
        result = installer.install(progress_callback)
    """
    
    def __init__(self, platform_info: PlatformInfo, network_manager: NetworkManager):
        """
        初始化 OpenClaw 安装器
        
        Args:
            platform_info: 平台信息对象
            network_manager: 网络管理器（用于获取镜像配置）
        """
        self.platform = platform_info
        self.network = network_manager
    
    def install(self, progress_callback: Optional[Callable[[str, int], None]] = None) -> InstallResult:
        """
        安装 OpenClaw
        
        安装策略（按优先级）：
        1. 官方一键脚本安装（最可靠，包含所有依赖处理）
        2. npm 全局安装（降级方案）
        3. brew 安装（仅 macOS，最终降级）
        
        Args:
            progress_callback: 进度回调函数
            
        Returns:
            InstallResult: 安装结果
        """
        logger.info("开始安装 OpenClaw...")
        
        # ── 策略 1: 官方一键脚本 ──
        if progress_callback:
            progress_callback("正在使用官方脚本安装 OpenClaw...", 30)
        
        result = self._install_via_official_script(progress_callback)
        if result.success:
            return result
        
        logger.warning(f"官方脚本安装失败: {result.error_message}，降级为 npm 安装...")
        
        # ── 策略 2: npm 全局安装 ──
        if progress_callback:
            progress_callback("正在通过 npm 安装 OpenClaw...", 50)
        
        result = self._install_via_npm(progress_callback)
        if result.success:
            return result
        
        logger.warning(f"npm 安装失败: {result.error_message}")
        
        # ── 策略 3: brew 安装（仅 macOS） ──
        if self.platform.os_type == OSType.MACOS:
            if progress_callback:
                progress_callback("正在通过 Homebrew 安装 OpenClaw...", 70)
            result = self._install_via_brew(progress_callback)
            if result.success:
                return result
        
        # 所有策略都失败
        return InstallResult(
            success=False,
            error_message="所有安装方式均失败。请检查网络连接后手动运行: "
                         f"curl -fsSL https://openclaw.ai/install.sh | bash"
        )
    
    def verify(self) -> InstallResult:
        """
        验证 OpenClaw 安装状态
        
        检查 openclaw 命令是否可用，并获取版本信息。
        
        Returns:
            InstallResult: 验证结果
        """
        openclaw_path = shutil.which("openclaw")
        if not openclaw_path:
            return InstallResult(
                success=False,
                error_message="openclaw 命令未找到"
            )
        
        try:
            result = subprocess.run(
                ["openclaw", "--version"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                version = result.stdout.strip()
                return InstallResult(
                    success=True,
                    version=version,
                    install_path=openclaw_path
                )
            else:
                return InstallResult(
                    success=False,
                    error_message=f"openclaw --version 返回错误: {result.stderr[:200]}"
                )
        except Exception as e:
            return InstallResult(
                success=False,
                error_message=f"验证异常: {e}"
            )
    
    def _install_via_official_script(self, progress_callback: Optional[Callable] = None) -> InstallResult:
        """
        使用官方一键安装脚本安装 OpenClaw
        
        Windows: iwr -useb https://openclaw.ai/install.ps1 | iex
        macOS/Linux: curl -fsSL https://openclaw.ai/install.sh | bash
        
        Args:
            progress_callback: 进度回调
            
        Returns:
            InstallResult: 安装结果
        """
        try:
            if self.platform.os_type == OSType.WINDOWS:
                # Windows: 使用 PowerShell 执行安装脚本
                script_url = OFFICIAL_INSTALL_SCRIPTS[OSType.WINDOWS]
                ps_script = f"iwr -useb {script_url} | iex"
                
                # 查找 PowerShell
                pwsh = shutil.which("pwsh") or shutil.which("powershell")
                if not pwsh:
                    return InstallResult(
                        success=False,
                        error_message="PowerShell 未找到",
                        method="official_script"
                    )
                
                cmd = [pwsh, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script]
            else:
                # macOS/Linux: 使用 curl + bash
                script_url = OFFICIAL_INSTALL_SCRIPTS[self.platform.os_type]
                cmd = ["bash", "-c", f"curl -fsSL {script_url} | bash"]
            
            logger.info(f"执行官方安装脚本: {' '.join(cmd[:3])}...")
            
            result = subprocess.run(
                cmd,
                capture_output=True, text=True, timeout=600  # 10 分钟超时
            )
            
            if result.returncode == 0:
                # 验证安装
                verify = self.verify()
                if verify.success:
                    return InstallResult(
                        success=True,
                        method="official_script",
                        version=verify.version,
                        install_path=verify.install_path
                    )
                else:
                    return InstallResult(
                        success=False,
                        method="official_script",
                        error_message=f"脚本执行成功但验证失败: {verify.error_message}"
                    )
            else:
                error_output = (result.stderr or result.stdout or "")[:500]
                return InstallResult(
                    success=False,
                    method="official_script",
                    error_message=f"脚本执行失败 (code={result.returncode}): {error_output}"
                )
                
        except subprocess.TimeoutExpired:
            return InstallResult(
                success=False,
                method="official_script",
                error_message="安装脚本执行超时（10分钟）"
            )
        except Exception as e:
            return InstallResult(
                success=False,
                method="official_script",
                error_message=f"执行异常: {e}"
            )
    
    def _install_via_npm(self, progress_callback: Optional[Callable] = None) -> InstallResult:
        """
        使用 npm 全局安装 OpenClaw
        
        降级方案：当官方脚本不可用时使用。
        
        Args:
            progress_callback: 进度回调
            
        Returns:
            InstallResult: 安装结果
        """
        npm_path = shutil.which("npm")
        if not npm_path:
            return InstallResult(
                success=False,
                method="npm",
                error_message="npm 未安装，无法使用 npm 安装"
            )
        
        try:
            # 确保 npm registry 已配置（可能需要使用国内镜像）
            registry = self.network.status.recommended_mirror
            if registry == "china":
                subprocess.run(
                    ["npm", "config", "set", "registry", "https://registry.npmmirror.com"],
                    capture_output=True, timeout=10
                )
            
            # 全局安装
            cmd = ["npm", "install", "-g", "openclaw"]
            logger.info(f"执行 npm 安装: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                capture_output=True, text=True, timeout=600
            )
            
            if result.returncode == 0:
                verify = self.verify()
                if verify.success:
                    return InstallResult(
                        success=True,
                        method="npm",
                        version=verify.version,
                        install_path=verify.install_path
                    )
                else:
                    return InstallResult(
                        success=False,
                        method="npm",
                        error_message=f"npm 安装成功但验证失败: {verify.error_message}"
                    )
            else:
                return InstallResult(
                    success=False,
                    method="npm",
                    error_message=f"npm 安装失败: {(result.stderr or '')[:500]}"
                )
                
        except subprocess.TimeoutExpired:
            return InstallResult(
                success=False,
                method="npm",
                error_message="npm 安装超时"
            )
        except Exception as e:
            return InstallResult(
                success=False,
                method="npm",
                error_message=f"npm 安装异常: {e}"
            )
    
    def _install_via_brew(self, progress_callback: Optional[Callable] = None) -> InstallResult:
        """
        使用 Homebrew 安装 OpenClaw（仅 macOS）
        
        最终降级方案。
        
        Args:
            progress_callback: 进度回调
            
        Returns:
            InstallResult: 安装结果
        """
        brew = shutil.which("brew")
        if not brew:
            return InstallResult(
                success=False,
                method="brew",
                error_message="Homebrew 未安装"
            )
        
        try:
            cmd = [brew, "install", "openclaw"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            
            if result.returncode == 0:
                verify = self.verify()
                if verify.success:
                    return InstallResult(
                        success=True,
                        method="brew",
                        version=verify.version,
                        install_path=verify.install_path
                    )
            
            return InstallResult(
                success=False,
                method="brew",
                error_message=f"brew 安装失败: {(result.stderr or '')[:500]}"
            )
        except Exception as e:
            return InstallResult(
                success=False,
                method="brew",
                error_message=f"brew 安装异常: {e}"
            )
