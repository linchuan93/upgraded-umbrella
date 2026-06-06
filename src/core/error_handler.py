"""
OpenClaw 一键安装程序 - 错误处理与重试模块

功能：
1. 统一错误捕获与分类
2. 自动重试机制（最多 3 次）
3. 结构化错误日志记录
4. 错误报告生成

设计原则：
- 所有安装步骤的错误都通过此模块统一处理
- 重试采用指数退避策略
- 错误日志保存到本地文件供后续分析
"""

import os
import time
import logging
import traceback
import json
from typing import Optional, Callable, TypeVar, Any, Dict, List
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from functools import wraps

logger = logging.getLogger("OpenClawInstaller")

T = TypeVar("T")

# ── 日志目录 ──
LOG_DIR = os.path.join(os.path.expanduser("~"), "OpenClaw_Installer_Logs")


class ErrorCategory(Enum):
    """错误分类枚举"""
    NETWORK = "network"          # 网络错误
    PERMISSION = "permission"    # 权限错误
    DEPENDENCY = "dependency"    # 依赖缺失
    INSTALL = "install"          # 安装失败
    CONFIG = "config"            # 配置错误
    DAEMON = "daemon"            # 守护进程错误
    PORT = "port"                # 端口冲突
    DISK = "disk"                # 磁盘空间
    TIMEOUT = "timeout"          # 超时
    UNKNOWN = "unknown"          # 未知错误


@dataclass
class ErrorRecord:
    """错误记录数据类"""
    timestamp: str = ""
    category: str = ""
    step: str = ""
    message: str = ""
    traceback: str = ""
    retry_count: int = 0
    max_retries: int = 3
    resolved: bool = False
    resolution: str = ""


class ErrorHandler:
    """
    错误处理器
    
    负责：
    1. 统一捕获和分类错误
    2. 实现自动重试机制
    3. 记录结构化错误日志
    4. 生成错误报告
    
    用法:
        handler = ErrorHandler()
        result = handler.with_retry(step_name, func, max_retries=3)
    """
    
    def __init__(self):
        """初始化错误处理器"""
        self.error_records: List[ErrorRecord] = []
        self._ensure_log_dir()
    
    def _ensure_log_dir(self) -> None:
        """确保日志目录存在"""
        os.makedirs(LOG_DIR, exist_ok=True)
    
    def with_retry(self, step_name: str, func: Callable[..., T],
                   max_retries: int = 3, delay_base: float = 2.0,
                   progress_callback: Optional[Callable[[str, int], None]] = None,
                   **kwargs) -> Optional[T]:
        """
        带自动重试的函数执行器
        
        采用指数退避策略：delay = delay_base * (2 ^ retry_count)
        即第 1 次重试等待 2 秒，第 2 次等待 4 秒，第 3 次等待 8 秒。
        
        Args:
            step_name: 步骤名称（用于日志）
            func: 要执行的函数
            max_retries: 最大重试次数
            delay_base: 退避基础延迟（秒）
            progress_callback: 进度回调
            **kwargs: 传递给 func 的参数
            
        Returns:
            Optional[T]: 函数返回值，全部重试失败返回 None
        """
        last_error = None
        
        for attempt in range(max_retries + 1):
            try:
                if attempt > 0:
                    delay = delay_base * (2 ** (attempt - 1))
                    logger.info(f"重试 {step_name} (第 {attempt}/{max_retries} 次)，等待 {delay:.0f} 秒...")
                    if progress_callback:
                        progress_callback(f"重试 {step_name} ({attempt}/{max_retries})...", attempt * 20)
                    time.sleep(delay)
                
                result = func(**kwargs)
                
                if attempt > 0:
                    logger.info(f"{step_name} 重试成功 (第 {attempt} 次)")
                
                # 记录成功
                if last_error:
                    self._record_resolution(step_name, "retry_success")
                
                return result
                
            except Exception as e:
                last_error = e
                category = self._classify_error(e)
                
                # 记录错误
                self._record_error(
                    step=step_name,
                    category=category,
                    message=str(e),
                    traceback_str=traceback.format_exc(),
                    retry_count=attempt,
                    max_retries=max_retries
                )
                
                logger.warning(
                    f"{step_name} 失败 (尝试 {attempt + 1}/{max_retries + 1}): "
                    f"[{category.value}] {e}"
                )
                
                # 如果是不应重试的错误类型，立即放弃
                if category in (ErrorCategory.PERMISSION, ErrorCategory.DISK):
                    logger.error(f"{step_name} 遇到不可重试的错误: {category.value}")
                    break
        
        # 所有重试失败
        logger.error(f"{step_name} 全部重试失败 ({max_retries + 1} 次)")
        self._save_error_report()
        return None
    
    def _classify_error(self, error: Exception) -> ErrorCategory:
        """
        根据异常信息分类错误
        
        Args:
            error: 异常对象
            
        Returns:
            ErrorCategory: 错误分类
        """
        error_str = str(error).lower()
        error_type = type(error).__name__.lower()
        
        # 网络错误
        if any(kw in error_str for kw in ["timeout", "timed out", "connection", "network", "dns"]):
            return ErrorCategory.NETWORK
        
        # 权限错误
        if any(kw in error_str for kw in ["permission", "denied", "eacces", "eperm", "access"]):
            return ErrorCategory.PERMISSION
        
        # 依赖缺失
        if any(kw in error_str for kw in ["not found", "missing", "module", "no such file"]):
            return ErrorCategory.DEPENDENCY
        
        # 端口冲突
        if any(kw in error_str for kw in ["port", "eaddrinuse", "in use"]):
            return ErrorCategory.PORT
        
        # 磁盘空间
        if any(kw in error_str for kw in ["space", "enospc", "disk"]):
            return ErrorCategory.DISK
        
        # 超时
        if "timeout" in error_type or "timeout" in error_str:
            return ErrorCategory.TIMEOUT
        
        # 安装失败
        if any(kw in error_str for kw in ["install", "setup", "build"]):
            return ErrorCategory.INSTALL
        
        # 配置错误
        if any(kw in error_str for kw in ["config", "setting", "invalid"]):
            return ErrorCategory.CONFIG
        
        return ErrorCategory.UNKNOWN
    
    def _record_error(self, step: str, category: ErrorCategory, message: str,
                      traceback_str: str, retry_count: int, max_retries: int) -> None:
        """
        记录错误信息
        
        Args:
            step: 步骤名称
            category: 错误分类
            message: 错误消息
            traceback_str: 异常堆栈
            retry_count: 当前重试次数
            max_retries: 最大重试次数
        """
        record = ErrorRecord(
            timestamp=datetime.now().isoformat(),
            category=category.value,
            step=step,
            message=message[:500],
            traceback=traceback_str[:2000],
            retry_count=retry_count,
            max_retries=max_retries
        )
        self.error_records.append(record)
    
    def _record_resolution(self, step: str, resolution: str) -> None:
        """
        记录错误解决信息
        
        Args:
            step: 步骤名称
            resolution: 解决方案描述
        """
        for record in reversed(self.error_records):
            if record.step == step and not record.resolved:
                record.resolved = True
                record.resolution = resolution
                break
    
    def _save_error_report(self) -> str:
        """
        保存结构化错误报告到本地文件
        
        Returns:
            str: 报告文件路径
        """
        report_path = os.path.join(LOG_DIR, "error.log")
        
        try:
            os.makedirs(LOG_DIR, exist_ok=True)
            
            with open(report_path, "a", encoding="utf-8") as f:
                f.write(f"\n{'='*60}\n")
                f.write(f"OpenClaw 安装程序错误报告\n")
                f.write(f"生成时间: {datetime.now().isoformat()}\n")
                f.write(f"{'='*60}\n\n")
                
                for i, record in enumerate(self.error_records, 1):
                    f.write(f"错误 #{i}\n")
                    f.write(f"  时间: {record.timestamp}\n")
                    f.write(f"  分类: {record.category}\n")
                    f.write(f"  步骤: {record.step}\n")
                    f.write(f"  消息: {record.message}\n")
                    f.write(f"  重试: {record.retry_count}/{record.max_retries}\n")
                    f.write(f"  已解决: {'是' if record.resolved else '否'}\n")
                    if record.resolved:
                        f.write(f"  解决方案: {record.resolution}\n")
                    f.write(f"\n")
                
                # 未解决的错误摘要
                unresolved = [r for r in self.error_records if not r.resolved]
                if unresolved:
                    f.write(f"\n未解决的错误 ({len(unresolved)} 个):\n")
                    for r in unresolved:
                        f.write(f"  - [{r.category}] {r.step}: {r.message[:100]}\n")
            
            logger.info(f"错误报告已保存到: {report_path}")
            return report_path
            
        except Exception as e:
            logger.error(f"保存错误报告失败: {e}")
            return ""
    
    def get_error_report_path(self) -> str:
        """
        获取错误报告文件路径
        
        Returns:
            str: 报告文件路径
        """
        return os.path.join(LOG_DIR, "error.log")
    
    def has_unresolved_errors(self) -> bool:
        """
        检查是否有未解决的错误
        
        Returns:
            bool: 是否存在未解决错误
        """
        return any(not r.resolved for r in self.error_records)
    
    def get_unresolved_errors(self) -> List[ErrorRecord]:
        """
        获取所有未解决的错误
        
        Returns:
            List[ErrorRecord]: 未解决的错误列表
        """
        return [r for r in self.error_records if not r.resolved]
    
    def get_summary(self) -> Dict[str, Any]:
        """
        获取错误摘要
        
        Returns:
            Dict: 包含错误统计的字典
        """
        total = len(self.error_records)
        resolved = sum(1 for r in self.error_records if r.resolved)
        
        by_category: Dict[str, int] = {}
        for r in self.error_records:
            by_category[r.category] = by_category.get(r.category, 0) + 1
        
        return {
            "total_errors": total,
            "resolved": resolved,
            "unresolved": total - resolved,
            "by_category": by_category,
            "log_path": self.get_error_report_path()
        }
