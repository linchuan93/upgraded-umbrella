"""
OpenClaw 一键安装程序 - 诊断修复模块

功能：
1. 运行 openclaw doctor 诊断命令
2. 自动执行 openclaw doctor --repair 修复
3. 解析诊断输出并提供修复建议
4. 根据常见错误码匹配预设修复脚本

设计原则：
- 优先使用 openclaw 自带的 doctor 功能
- doctor 无法修复时，根据错误码匹配预设修复方案
- 所有修复操作记录到日志
- 修复失败时不阻塞，提供手动修复指引
"""

import subprocess
import shutil
import re
import logging
from typing import Optional, Callable, List, Dict, Tuple
from dataclasses import dataclass, field

from .platform_detector import PlatformInfo, OSType

logger = logging.getLogger("OpenClawInstaller")


@dataclass
class DiagnosisResult:
    """诊断结果数据类"""
    healthy: bool = False
    issues: List[str] = field(default_factory=list)
    fixable: bool = False
    repair_attempted: bool = False
    repair_success: bool = False
    details: str = ""


# ── 常见错误码与修复方案映射 ──
ERROR_FIX_MAP: Dict[str, Dict] = {
    # 权限相关
    "permission denied": {
        "fix": "escalate_privilege",
        "description": "权限不足，需要提权",
        "action": "自动请求管理员权限"
    },
    "EACCES": {
        "fix": "escalate_privilege",
        "description": "文件访问权限被拒绝",
        "action": "自动请求管理员权限并重试"
    },
    "EPERM": {
        "fix": "escalate_privilege",
        "description": "操作不被允许",
        "action": "自动请求管理员权限"
    },
    
    # 网络相关
    "ETIMEDOUT": {
        "fix": "switch_mirror",
        "description": "网络连接超时",
        "action": "切换到国内镜像源"
    },
    "ENOTFOUND": {
        "fix": "check_dns",
        "description": "DNS 解析失败",
        "action": "检查 DNS 配置或切换镜像源"
    },
    "ECONNREFUSED": {
        "fix": "check_service",
        "description": "连接被拒绝",
        "action": "检查目标服务是否可用"
    },
    "ECONNRESET": {
        "fix": "retry",
        "description": "连接被重置",
        "action": "重试操作"
    },
    
    # 磁盘相关
    "ENOSPC": {
        "fix": "clean_disk",
        "description": "磁盘空间不足",
        "action": "清理临时文件释放空间"
    },
    
    # 端口相关
    "EADDRINUSE": {
        "fix": "change_port",
        "description": "端口被占用",
        "action": "更换为可用端口"
    },
    
    # Node.js 相关
    "MODULE_NOT_FOUND": {
        "fix": "reinstall_deps",
        "description": "Node.js 模块缺失",
        "action": "重新安装依赖"
    },
    "npm ERR!": {
        "fix": "npm_cache_clean",
        "description": "npm 安装错误",
        "action": "清理 npm 缓存并重试"
    },
}


class DoctorRunner:
    """
    诊断修复运行器
    
    负责：
    1. 运行 openclaw doctor 诊断
    2. 尝试 openclaw doctor --repair 自动修复
    3. 根据错误码匹配修复方案
    4. 执行预设修复脚本
    
    用法:
        doctor = DoctorRunner(platform_info)
        result = doctor.run_diagnosis()
        if not result.healthy:
            doctor.attempt_repair(result)
    """
    
    def __init__(self, platform_info: PlatformInfo):
        """
        初始化诊断修复运行器
        
        Args:
            platform_info: 平台信息对象
        """
        self.platform = platform_info
    
    def run_diagnosis(self, progress_callback: Optional[Callable[[str, int], None]] = None) -> DiagnosisResult:
        """
        运行 openclaw doctor 诊断
        
        Args:
            progress_callback: 进度回调
            
        Returns:
            DiagnosisResult: 诊断结果
        """
        logger.info("运行 openclaw doctor 诊断...")
        
        if progress_callback:
            progress_callback("正在运行诊断...", 20)
        
        openclaw = shutil.which("openclaw")
        if not openclaw:
            return DiagnosisResult(
                healthy=False,
                issues=["openclaw 命令未找到"],
                details="OpenClaw 尚未安装，无法运行诊断"
            )
        
        try:
            result = subprocess.run(
                ["openclaw", "doctor"],
                capture_output=True, text=True, timeout=120
            )
            
            output = result.stdout + result.stderr
            issues = self._parse_issues(output)
            
            diag = DiagnosisResult(
                healthy=len(issues) == 0 and result.returncode == 0,
                issues=issues,
                fixable=self._check_fixable(issues),
                details=output[:2000]
            )
            
            logger.info(f"诊断完成: {'健康' if diag.healthy else f'发现 {len(issues)} 个问题'}")
            for issue in issues:
                logger.info(f"  问题: {issue}")
            
            return diag
            
        except subprocess.TimeoutExpired:
            logger.error("openclaw doctor 超时")
            return DiagnosisResult(
                healthy=False,
                issues=["诊断命令超时"],
                details="openclaw doctor 执行超过 2 分钟"
            )
        except Exception as e:
            logger.error(f"诊断异常: {e}")
            return DiagnosisResult(
                healthy=False,
                issues=[f"诊断异常: {e}"],
                details=str(e)
            )
    
    def attempt_repair(self, diagnosis: DiagnosisResult,
                       progress_callback: Optional[Callable[[str, int], None]] = None) -> DiagnosisResult:
        """
        尝试自动修复诊断出的问题
        
        修复策略：
        1. 优先运行 openclaw doctor --repair
        2. 根据 ERROR_FIX_MAP 匹配修复方案
        3. 执行预设修复脚本
        
        Args:
            diagnosis: 诊断结果
            progress_callback: 进度回调
            
        Returns:
            DiagnosisResult: 修复后的诊断结果
        """
        logger.info("尝试自动修复...")
        
        if progress_callback:
            progress_callback("正在尝试自动修复...", 50)
        
        # ── 策略 1: openclaw doctor --repair ──
        repair_result = self._run_doctor_repair()
        if repair_result:
            logger.info("openclaw doctor --repair 修复成功")
            # 重新诊断确认
            return self.run_diagnosis(progress_callback)
        
        logger.warning("doctor --repair 未能修复，尝试预设修复方案...")
        
        # ── 策略 2: 根据错误码匹配修复 ──
        for issue in diagnosis.issues:
            fix_applied = self._apply_fix_for_error(issue, progress_callback)
            if fix_applied:
                logger.info(f"已应用修复方案: {issue[:50]}")
        
        # 重新诊断
        if progress_callback:
            progress_callback("重新诊断中...", 90)
        
        return self.run_diagnosis(progress_callback)
    
    def _run_doctor_repair(self) -> bool:
        """
        运行 openclaw doctor --repair
        
        Returns:
            bool: 修复是否成功
        """
        openclaw = shutil.which("openclaw")
        if not openclaw:
            return False
        
        try:
            result = subprocess.run(
                ["openclaw", "doctor", "--repair"],
                capture_output=True, text=True, timeout=180
            )
            
            if result.returncode == 0:
                logger.info("doctor --repair 执行成功")
                return True
            else:
                logger.warning(f"doctor --repair 返回非零: {result.stderr[:200]}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error("doctor --repair 超时")
            return False
        except Exception as e:
            logger.error(f"doctor --repair 异常: {e}")
            return False
    
    def _parse_issues(self, output: str) -> List[str]:
        """
        解析诊断输出，提取问题列表
        
        Args:
            output: 诊断命令的输出文本
            
        Returns:
            List[str]: 问题列表
        """
        issues = []
        
        # 常见问题标记
        problem_markers = [
            r"(?i)error[:：]",
            r"(?i)warning[:：]",
            r"(?i)fail(?:ed|ure)[:：]",
            r"(?i)not found",
            r"(?i)missing",
            r"(?i)unavailable",
            r"✗",
            r"❌",
            r"\[FAIL\]",
            r"\[ERROR\]",
        ]
        
        for line in output.splitlines():
            for marker in problem_markers:
                if re.search(marker, line):
                    # 清理并添加到问题列表
                    clean_line = line.strip()
                    if clean_line and clean_line not in issues:
                        issues.append(clean_line)
                    break
        
        return issues
    
    def _check_fixable(self, issues: List[str]) -> bool:
        """
        检查问题是否可自动修复
        
        Args:
            issues: 问题列表
            
        Returns:
            bool: 是否有可自动修复的问题
        """
        for issue in issues:
            issue_lower = issue.lower()
            for error_key in ERROR_FIX_MAP:
                if error_key.lower() in issue_lower:
                    return True
        return False
    
    def _apply_fix_for_error(self, error: str,
                              progress_callback: Optional[Callable] = None) -> bool:
        """
        根据错误信息匹配并应用修复方案
        
        Args:
            error: 错误信息
            progress_callback: 进度回调
            
        Returns:
            bool: 是否成功应用了修复方案
        """
        error_lower = error.lower()
        
        for error_key, fix_info in ERROR_FIX_MAP.items():
            if error_key.lower() in error_lower:
                logger.info(f"匹配到修复方案: {fix_info['description']} → {fix_info['action']}")
                
                fix_method = fix_info["fix"]
                
                try:
                    if fix_method == "escalate_privilege":
                        return self._fix_escalate_privilege()
                    elif fix_method == "switch_mirror":
                        return self._fix_switch_mirror()
                    elif fix_method == "retry":
                        return True  # 由上层重试逻辑处理
                    elif fix_method == "clean_disk":
                        return self._fix_clean_disk()
                    elif fix_method == "change_port":
                        return self._fix_change_port()
                    elif fix_method == "reinstall_deps":
                        return self._fix_reinstall_deps()
                    elif fix_method == "npm_cache_clean":
                        return self._fix_npm_cache_clean()
                    elif fix_method == "check_dns":
                        return self._fix_switch_mirror()  # DNS 问题也切换镜像
                    elif fix_method == "check_service":
                        return False  # 服务不可用需要用户手动处理
                    else:
                        return False
                        
                except Exception as e:
                    logger.error(f"修复方案执行异常: {e}")
                    return False
        
        # 未知错误，记录但不修复
        logger.warning(f"未匹配到修复方案: {error[:100]}")
        return False
    
    # ── 修复方案实现 ──
    
    def _fix_escalate_privilege(self) -> bool:
        """修复权限问题：请求提权"""
        if self.platform.os_type == OSType.WINDOWS:
            # Windows: 提示用户以管理员身份运行
            logger.warning("请右键安装程序，选择'以管理员身份运行'")
            return False
        elif self.platform.os_type in (OSType.MACOS, OSType.LINUX):
            # Unix: 检查 sudo 权限
            try:
                result = subprocess.run(
                    ["sudo", "-n", "true"],
                    capture_output=True, timeout=5
                )
                if result.returncode == 0:
                    logger.info("sudo 权限可用")
                    return True
                else:
                    logger.warning("需要 sudo 密码，请在弹出提示时输入")
                    return False
            except Exception:
                return False
        return False
    
    def _fix_switch_mirror(self) -> bool:
        """修复网络问题：切换到国内镜像"""
        try:
            npm = shutil.which("npm")
            if npm:
                subprocess.run(
                    ["npm", "config", "set", "registry", "https://registry.npmmirror.com"],
                    capture_output=True, timeout=10
                )
                logger.info("已切换 npm 为国内镜像源")
            return True
        except Exception:
            return False
    
    def _fix_clean_disk(self) -> bool:
        """修复磁盘空间不足：清理临时文件"""
        try:
            import tempfile
            temp_dir = tempfile.gettempdir()
            
            # 清理常见的临时文件
            clean_targets = []
            if self.platform.os_type == OSType.WINDOWS:
                clean_targets = [
                    os.path.join(os.environ.get("TEMP", ""), "openclaw_*"),
                    os.path.join(os.environ.get("TEMP", ""), "node_*"),
                ]
            else:
                clean_targets = [
                    "/tmp/openclaw_*",
                    "/tmp/npm-*",
                ]
            
            import glob
            for pattern in clean_targets:
                for f in glob.glob(pattern):
                    try:
                        os.unlink(f)
                    except Exception:
                        pass
            
            # 清理 npm 缓存
            npm = shutil.which("npm")
            if npm:
                subprocess.run(
                    ["npm", "cache", "clean", "--force"],
                    capture_output=True, timeout=60
                )
            
            logger.info("临时文件已清理")
            return True
        except Exception as e:
            logger.error(f"磁盘清理异常: {e}")
            return False
    
    def _fix_change_port(self) -> bool:
        """修复端口冲突：更换端口"""
        from .network_manager import NetworkManager
        nm = NetworkManager(self.platform)
        new_port = nm.find_available_port(3000)
        
        if new_port > 0:
            logger.info(f"可用端口: {new_port}")
            # TODO: 更新 OpenClaw 配置文件中的端口号
            return True
        return False
    
    def _fix_reinstall_deps(self) -> bool:
        """修复模块缺失：重新安装依赖"""
        try:
            npm = shutil.which("npm")
            if not npm:
                return False
            
            result = subprocess.run(
                ["npm", "install", "-g", "openclaw", "--force"],
                capture_output=True, timeout=300
            )
            return result.returncode == 0
        except Exception:
            return False
    
    def _fix_npm_cache_clean(self) -> bool:
        """修复 npm 错误：清理缓存并重试"""
        try:
            npm = shutil.which("npm")
            if npm:
                subprocess.run(
                    ["npm", "cache", "clean", "--force"],
                    capture_output=True, timeout=60
                )
            return True
        except Exception:
            return False


# 需要在模块顶部导入 os
import os
