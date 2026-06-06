"""
OpenClaw 一键安装程序 - Onboard 智能应答模块

功能：
1. 检测 openclaw onboard 是否支持 --non-interactive 模式
2. 优先使用非交互模式参数完成全部配置
3. 降级为 PTY 伪终端模式（Expect-like），自动应答交互式提示
4. 未知对话模式时输出结构化警告但不阻塞
5. 支持通过环境变量预设 API Key

设计原则：
- 三级降级策略：non-interactive → PTY → 手动提示
- PTY 模式使用正则模式匹配捕获提示并自动应答
- 所有自动应答操作记录到日志，可追溯
- 遇到未知模式不崩溃，仅警告并继续
"""

import subprocess
import re
import os
import logging
import time
import signal
from typing import Optional, Callable, Dict, List, Tuple, Pattern
from dataclasses import dataclass, field
from enum import Enum

from .platform_detector import PlatformInfo, OSType

logger = logging.getLogger("OpenClawInstaller")


class OnboardMode(Enum):
    """Onboard 执行模式枚举"""
    NON_INTERACTIVE = "non_interactive"   # 非交互模式（最优）
    PTY = "pty"                           # 伪终端模式（降级）
    MANUAL = "manual"                      # 手动模式（最终降级）


@dataclass
class OnboardResult:
    """Onboard 执行结果"""
    success: bool = False
    mode: OnboardMode = OnboardMode.MANUAL
    steps_completed: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    error_message: str = ""


@dataclass
class PromptPattern:
    """
    交互式提示模式定义
    
    用于 PTY 模式下匹配 openclaw onboard 的交互提示并自动应答。
    """
    pattern: Pattern          # 正则匹配模式
    response: str             # 自动应答内容
    description: str          # 描述（用于日志）
    is_confirm: bool = False  # 是否为确认提示（y/N）


class OnboardHandler:
    """
    Onboard 智能应答处理器
    
    负责：
    1. 检测 openclaw onboard 支持的参数
    2. 优先使用 --non-interactive 模式
    3. 降级为 PTY 伪终端交互模式
    4. 自动填充 API Key 等敏感信息
    5. 处理确认提示（y/N）
    
    用法:
        handler = OnboardHandler(platform_info)
        handler.set_api_key(os.environ.get("CUSTOM_API_KEY", ""))
        result = handler.run(progress_callback)
    """
    
    def __init__(self, platform_info: PlatformInfo):
        """
        初始化 Onboard 处理器
        
        Args:
            platform_info: 平台信息对象
        """
        self.platform = platform_info
        self._api_key: str = ""
        self._mode_preference: OnboardMode = OnboardMode.NON_INTERACTIVE
        self._onboard_path: str = ""
        
        # 初始化交互提示模式库
        self._prompt_patterns = self._init_prompt_patterns()
    
    def set_api_key(self, api_key: str) -> None:
        """
        设置 API Key
        
        优先级：环境变量 CUSTOM_API_KEY > 此方法设置的值
        
        Args:
            api_key: API Key 字符串
        """
        env_key = os.environ.get("CUSTOM_API_KEY", "")
        self._api_key = env_key or api_key
        if self._api_key:
            logger.info("API Key 已设置（来源: %s）", "环境变量" if env_key else "参数")
        else:
            logger.warning("未设置 API Key，onboard 过程中可能需要手动输入")
    
    def run(self, progress_callback: Optional[Callable[[str, int], None]] = None) -> OnboardResult:
        """
        执行 openclaw onboard
        
        三级降级策略：
        1. 检测 --non-interactive 支持情况，优先使用参数化模式
        2. 降级为 PTY 伪终端模式，自动应答交互提示
        3. 最终降级为手动提示模式
        
        Args:
            progress_callback: 进度回调
            
        Returns:
            OnboardResult: 执行结果
        """
        logger.info("开始执行 openclaw onboard...")
        
        # 先检查 openclaw 是否已安装
        import shutil
        self._onboard_path = shutil.which("openclaw") or ""
        if not self._onboard_path:
            return OnboardResult(
                success=False,
                error_message="openclaw 命令未找到，请先安装 OpenClaw"
            )
        
        # ── 策略 1: 非交互模式 ──
        if progress_callback:
            progress_callback("检测非交互模式支持...", 10)
        
        non_interactive_supported, supported_params = self._check_non_interactive_support()
        
        if non_interactive_supported:
            logger.info("检测到 --non-interactive 支持，使用参数化模式")
            if progress_callback:
                progress_callback("使用非交互模式配置...", 30)
            
            result = self._run_non_interactive(supported_params, progress_callback)
            if result.success:
                return result
            
            logger.warning(f"非交互模式失败: {result.error_message}，降级为 PTY 模式")
        
        # ── 策略 2: PTY 伪终端模式 ──
        logger.info("降级为 PTY 伪终端模式")
        if progress_callback:
            progress_callback("使用智能应答模式配置...", 50)
        
        result = self._run_pty_mode(progress_callback)
        if result.success:
            return result
        
        logger.warning(f"PTY 模式失败: {result.error_message}，降级为手动提示")
        
        # ── 策略 3: 手动模式 ──
        return OnboardResult(
            success=False,
            mode=OnboardMode.MANUAL,
            error_message=(
                "自动配置失败。请手动执行以下命令完成初始化:\n"
                "  openclaw onboard\n"
                "根据提示完成配置即可。"
            )
        )
    
    def _check_non_interactive_support(self) -> Tuple[bool, List[str]]:
        """
        检测 openclaw onboard --help 中的非交互模式参数
        
        Returns:
            Tuple[bool, List[str]]: (是否支持非交互模式, 支持的参数列表)
        """
        try:
            result = subprocess.run(
                ["openclaw", "onboard", "--help"],
                capture_output=True, text=True, timeout=15
            )
            
            help_text = result.stdout + result.stderr
            supported_params = []
            
            # 检测 --non-interactive 标志
            if "--non-interactive" in help_text:
                supported_params.append("--non-interactive")
            
            # 检测其他关键参数
            key_params = [
                "--mode", "--install-daemon", "--accept-risk",
                "--config-path", "--api-key", "--provider",
                "--no-daemon"
            ]
            
            for param in key_params:
                if param in help_text:
                    supported_params.append(param)
            
            has_non_interactive = "--non-interactive" in supported_params
            logger.info(f"非交互模式支持: {has_non_interactive}, 参数: {supported_params}")
            
            return has_non_interactive, supported_params
            
        except subprocess.TimeoutExpired:
            logger.warning("openclaw onboard --help 超时")
            return False, []
        except Exception as e:
            logger.warning(f"检测非交互模式异常: {e}")
            return False, []
    
    def _run_non_interactive(self, supported_params: List[str],
                              progress_callback: Optional[Callable] = None) -> OnboardResult:
        """
        使用非交互模式执行 onboard
        
        根据检测到的参数构建完整的命令行。
        
        Args:
            supported_params: 支持的参数列表
            progress_callback: 进度回调
            
        Returns:
            OnboardResult: 执行结果
        """
        cmd = ["openclaw", "onboard"]
        
        # ── 构建命令参数 ──
        cmd.append("--non-interactive")
        
        if "--mode" in supported_params:
            cmd.extend(["--mode", "local"])
        
        if "--install-daemon" in supported_params:
            cmd.append("--install-daemon")
        
        if "--accept-risk" in supported_params:
            cmd.append("--accept-risk")
        
        # API Key 通过环境变量传递（避免命令行暴露）
        env = os.environ.copy()
        if self._api_key:
            if "--api-key" in supported_params:
                cmd.extend(["--api-key", self._api_key])
            else:
                # 通过环境变量传递
                env["OPENCLAW_API_KEY"] = self._api_key
                env["ANTHROPIC_API_KEY"] = self._api_key
        
        logger.info(f"执行非交互模式: {' '.join(cmd[:4])}...")
        
        if progress_callback:
            progress_callback("正在执行 onboard 配置...", 60)
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True, text=True, timeout=300,
                env=env
            )
            
            if result.returncode == 0:
                logger.info("非交互模式 onboard 成功")
                return OnboardResult(
                    success=True,
                    mode=OnboardMode.NON_INTERACTIVE,
                    steps_completed=["non_interactive_onboard"]
                )
            else:
                error = (result.stderr or result.stdout or "")[:500]
                logger.error(f"非交互模式失败: {error}")
                return OnboardResult(
                    success=False,
                    mode=OnboardMode.NON_INTERACTIVE,
                    error_message=f"返回码 {result.returncode}: {error}"
                )
                
        except subprocess.TimeoutExpired:
            return OnboardResult(
                success=False,
                mode=OnboardMode.NON_INTERACTIVE,
                error_message="非交互模式超时（5分钟）"
            )
        except Exception as e:
            return OnboardResult(
                success=False,
                mode=OnboardMode.NON_INTERACTIVE,
                error_message=f"执行异常: {e}"
            )
    
    def _run_pty_mode(self, progress_callback: Optional[Callable] = None) -> OnboardResult:
        """
        使用 PTY 伪终端模式执行 onboard
        
        通过伪终端与 openclaw onboard 进程交互，
        实时捕获输出流，检测到等待输入时自动应答。
        
        此模式类似 Linux 的 expect 工具。
        
        Args:
            progress_callback: 进度回调
            
        Returns:
            OnboardResult: 执行结果
        """
        logger.info("启动 PTY 伪终端模式...")
        
        try:
            # 尝试使用 pty 模块（Unix 系统内置）
            if self.platform.os_type != OSType.WINDOWS:
                return self._run_pty_unix(progress_callback)
            else:
                # Windows 不支持 pty 模块，使用管道 + 超时模式
                return self._run_pty_windows(progress_callback)
                
        except Exception as e:
            logger.error(f"PTY 模式异常: {e}")
            return OnboardResult(
                success=False,
                mode=OnboardMode.PTY,
                error_message=f"PTY 异常: {e}"
            )
    
    def _run_pty_unix(self, progress_callback: Optional[Callable] = None) -> OnboardResult:
        """
        Unix (macOS/Linux) PTY 模式实现
        
        使用 Python 内置的 pty 模块创建伪终端，
        与 openclaw onboard 进程进行交互。
        
        Args:
            progress_callback: 进度回调
            
        Returns:
            OnboardResult: 执行结果
        """
        import pty
        import select
        
        warnings = []
        steps_completed = []
        
        cmd = ["openclaw", "onboard"]
        env = os.environ.copy()
        if self._api_key:
            env["OPENCLAW_API_KEY"] = self._api_key
            env["ANTHROPIC_API_KEY"] = self._api_key
        
        try:
            # 创建伪终端
            master_fd, slave_fd = pty.openpty()
            
            proc = subprocess.Popen(
                cmd,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=subprocess.STDOUT,
                env=env,
                close_fds=True
            )
            
            os.close(slave_fd)  # 子进程已获得副本
            
            # 设置 master_fd 为非阻塞
            import fcntl
            flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
            fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
            
            output_buffer = ""
            timeout_seconds = 300  # 总超时 5 分钟
            start_time = time.time()
            last_output_time = start_time
            
            while True:
                elapsed = time.time() - start_time
                if elapsed > timeout_seconds:
                    proc.kill()
                    return OnboardResult(
                        success=False,
                        mode=OnboardMode.PTY,
                        warnings=warnings,
                        error_message="PTY 模式超时（5分钟）"
                    )
                
                # 检查进程是否已结束
                if proc.poll() is not None:
                    # 读取剩余输出
                    try:
                        remaining = os.read(master_fd, 4096).decode("utf-8", errors="replace")
                        output_buffer += remaining
                    except Exception:
                        pass
                    break
                
                # 读取输出（非阻塞）
                try:
                    ready, _, _ = select.select([master_fd], [], [], 0.5)
                    if ready:
                        chunk = os.read(master_fd, 4096).decode("utf-8", errors="replace")
                        output_buffer += chunk
                        last_output_time = time.time()
                        logger.debug(f"PTY 输出: {chunk[:100]}...")
                        
                        # 更新进度
                        if progress_callback:
                            progress_callback("正在配置 OpenClaw...", 70)
                except OSError:
                    break
                except Exception:
                    pass
                
                # 检查是否需要自动应答
                response = self._match_prompt(output_buffer)
                if response is not None:
                    logger.info(f"自动应答: {response[:20]}...")
                    time.sleep(0.5)  # 短暂延迟确保进程已准备好接收输入
                    os.write(master_fd, (response + "\n").encode("utf-8"))
                    output_buffer = ""  # 清空缓冲区，避免重复匹配
                    
                    # 记录步骤
                    steps_completed.append(f"auto_reply: {response[:30]}")
            
            os.close(master_fd)
            proc.wait()
            
            if proc.returncode == 0:
                logger.info("PTY 模式 onboard 成功")
                return OnboardResult(
                    success=True,
                    mode=OnboardMode.PTY,
                    steps_completed=steps_completed,
                    warnings=warnings
                )
            else:
                return OnboardResult(
                    success=False,
                    mode=OnboardMode.PTY,
                    steps_completed=steps_completed,
                    warnings=warnings,
                    error_message=f"返回码 {proc.returncode}: {output_buffer[-300:]}"
                )
                
        except Exception as e:
            return OnboardResult(
                success=False,
                mode=OnboardMode.PTY,
                warnings=warnings,
                error_message=f"PTY Unix 异常: {e}"
            )
    
    def _run_pty_windows(self, progress_callback: Optional[Callable] = None) -> OnboardResult:
        """
        Windows PTY 模式实现
        
        Windows 不支持 Python 的 pty 模块，因此使用管道 + 超时检测模式：
        1. 使用 subprocess.Popen 的 stdin/stdout 管道
        2. 设置短超时读取输出
        3. 检测到提示模式时自动写入应答
        
        Args:
            progress_callback: 进度回调
            
        Returns:
            OnboardResult: 执行结果
        """
        warnings = []
        steps_completed = []
        
        cmd = ["openclaw", "onboard"]
        env = os.environ.copy()
        if self._api_key:
            env["OPENCLAW_API_KEY"] = self._api_key
            env["ANTHROPIC_API_KEY"] = self._api_key
        
        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
                text=True,
                bufsize=1  # 行缓冲
            )
            
            output_buffer = ""
            timeout_seconds = 300
            start_time = time.time()
            
            while True:
                elapsed = time.time() - start_time
                if elapsed > timeout_seconds:
                    proc.kill()
                    return OnboardResult(
                        success=False,
                        mode=OnboardMode.PTY,
                        warnings=warnings,
                        error_message="Windows PTY 模式超时"
                    )
                
                # 检查进程是否已结束
                if proc.poll() is not None:
                    # 读取剩余输出
                    remaining = proc.stdout.read() or ""
                    output_buffer += remaining
                    break
                
                # 非阻塞读取输出
                try:
                    import threading
                    
                    chunk_holder = [None]
                    def read_chunk():
                        try:
                            chunk_holder[0] = proc.stdout.readline()
                        except Exception:
                            pass
                    
                    reader = threading.Thread(target=read_chunk, daemon=True)
                    reader.start()
                    reader.join(timeout=2.0)
                    
                    if chunk_holder[0] is not None:
                        output_buffer += chunk_holder[0]
                        logger.debug(f"Windows PTY 输出: {chunk_holder[0][:100]}")
                        
                        if progress_callback:
                            progress_callback("正在配置 OpenClaw...", 70)
                except Exception:
                    pass
                
                # 检查是否需要自动应答
                response = self._match_prompt(output_buffer)
                if response is not None:
                    logger.info(f"自动应答: {response[:20]}...")
                    try:
                        proc.stdin.write(response + "\n")
                        proc.stdin.flush()
                    except Exception:
                        pass
                    output_buffer = ""
                    steps_completed.append(f"auto_reply: {response[:30]}")
            
            if proc.returncode == 0:
                return OnboardResult(
                    success=True,
                    mode=OnboardMode.PTY,
                    steps_completed=steps_completed,
                    warnings=warnings
                )
            else:
                return OnboardResult(
                    success=False,
                    mode=OnboardMode.PTY,
                    steps_completed=steps_completed,
                    warnings=warnings,
                    error_message=f"返回码 {proc.returncode}"
                )
                
        except Exception as e:
            return OnboardResult(
                success=False,
                mode=OnboardMode.PTY,
                warnings=warnings,
                error_message=f"Windows PTY 异常: {e}"
            )
    
    def _match_prompt(self, output: str) -> Optional[str]:
        """
        匹配输出中的交互提示并返回应答
        
        遍历预定义的提示模式库，当输出匹配到某个模式时返回对应应答。
        如果没有任何模式匹配，返回 None。
        
        Args:
            output: 进程输出文本
            
        Returns:
            Optional[str]: 应答内容，无匹配时返回 None
        """
        # 取输出最后 500 字符进行匹配（避免重复匹配历史输出）
        recent_output = output[-500:] if len(output) > 500 else output
        
        for pattern_def in self._prompt_patterns:
            if pattern_def.pattern.search(recent_output):
                logger.info(f"匹配到提示: {pattern_def.description}")
                
                # 如果是确认提示，自动回答 "y"
                if pattern_def.is_confirm:
                    return "y"
                
                # 检查应答是否需要替换变量
                response = pattern_def.response
                if "{API_KEY}" in response:
                    if self._api_key:
                        response = response.replace("{API_KEY}", self._api_key)
                    else:
                        logger.warning("需要 API Key 但未设置，跳过此项")
                        # 发送空行继续
                        return ""
                
                return response
        
        # 检测未知提示模式（以冒号或问号结尾的行）
        unknown_pattern = re.compile(r".*[?:]\s*$", re.MULTILINE)
        if unknown_pattern.search(recent_output):
            # 检查是否已经处理过（避免无限循环）
            lines = recent_output.strip().splitlines()
            if lines:
                last_line = lines[-1].strip()
                if last_line and not last_line.startswith("$") and len(last_line) > 5:
                    warning_msg = f"检测到未知交互提示: '{last_line[:80]}'"
                    logger.warning(warning_msg)
                    # 不返回应答，让进程继续等待或超时
                    # 这里返回空字符串以跳过当前提示
                    return ""
        
        return None
    
    def _init_prompt_patterns(self) -> List[PromptPattern]:
        """
        初始化交互提示模式库
        
        定义了 openclaw onboard 中可能出现的所有交互提示及其自动应答。
        每个模式包含：正则表达式、应答内容、描述、是否为确认提示。
        
        Returns:
            List[PromptPattern]: 提示模式列表
        """
        patterns = [
            # ── API Key 相关 ──
            PromptPattern(
                pattern=re.compile(r"(?i)enter\s+(your\s+)?api\s+key", re.IGNORECASE),
                response="{API_KEY}",
                description="API Key 输入提示"
            ),
            PromptPattern(
                pattern=re.compile(r"(?i)please\s+enter\s+(your\s+)?(anthropic|openai|api)\s+key", re.IGNORECASE),
                response="{API_KEY}",
                description="API Key 输入提示（详细版）"
            ),
            PromptPattern(
                pattern=re.compile(r"(?i)api\s+key\s*[:：]\s*", re.MULTILINE),
                response="{API_KEY}",
                description="API Key 冒号提示"
            ),
            
            # ── 确认提示 ──
            PromptPattern(
                pattern=re.compile(r"(?i)confirm\s*\[y/N\]", re.IGNORECASE),
                response="y",
                description="确认提示 [y/N]",
                is_confirm=True
            ),
            PromptPattern(
                pattern=re.compile(r"(?i)\[Y/n\]", re.IGNORECASE),
                response="y",
                description="确认提示 [Y/n]",
                is_confirm=True
            ),
            PromptPattern(
                pattern=re.compile(r"(?i)do\s+you\s+want\s+to\s+continue", re.IGNORECASE),
                response="y",
                description="是否继续",
                is_confirm=True
            ),
            PromptPattern(
                pattern=re.compile(r"(?i)accept\s+(the\s+)?(terms|risk|license)", re.IGNORECASE),
                response="y",
                description="接受条款/风险",
                is_confirm=True
            ),
            PromptPattern(
                pattern=re.compile(r"(?i)install\s+(the\s+)?daemon", re.IGNORECASE),
                response="y",
                description="安装守护进程",
                is_confirm=True
            ),
            
            # ── 选择提示 ──
            PromptPattern(
                pattern=re.compile(r"(?i)select\s+(a\s+)?mode.*local", re.IGNORECASE),
                response="local",
                description="选择本地模式"
            ),
            PromptPattern(
                pattern=re.compile(r"(?i)choose\s+(a\s+)?provider", re.IGNORECASE),
                response="1",  # 通常第一个选项是默认
                description="选择提供商"
            ),
            PromptPattern(
                pattern=re.compile(r"(?i)select\s+(a\s+)?model", re.IGNORECASE),
                response="",  # 使用默认
                description="选择模型（使用默认）"
            ),
            
            # ── 路径/配置提示 ──
            PromptPattern(
                pattern=re.compile(r"(?i)config\s+(file\s+)?path", re.IGNORECASE),
                response="",  # 使用默认路径
                description="配置路径（使用默认）"
            ),
            PromptPattern(
                pattern=re.compile(r"(?i)install\s+path|destination", re.IGNORECASE),
                response="",  # 使用默认路径
                description="安装路径（使用默认）"
            ),
            PromptPattern(
                pattern=re.compile(r"(?i)port\s*(number)?\s*[:：]", re.IGNORECASE),
                response="",  # 使用默认端口
                description="端口号（使用默认）"
            ),
            
            # ── 其他 ──
            PromptPattern(
                pattern=re.compile(r"(?i)press\s+enter\s+to\s+continue", re.IGNORECASE),
                response="",
                description="按回车继续"
            ),
            PromptPattern(
                pattern=re.compile(r"(?i)password\s*[:：]", re.IGNORECASE),
                response="",  # 密码不能自动填入
                description="密码提示（跳过）"
            ),
        ]
        
        return patterns
