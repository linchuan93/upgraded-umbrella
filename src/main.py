"""
OpenClaw 一键安装程序 - 主 GUI 应用

功能：
1. 图形化安装界面（基于 tkinter，无需额外依赖）
2. 实时进度条和步骤展示
3. 日志输出窗口
4. 安全提示展示
5. 安装结果展示
6. 权限引导弹窗

设计原则：
- 使用 tkinter（Python 内置，确保零额外依赖）
- 界面简洁专业，进度清晰
- 所有操作在后台线程执行，不阻塞 UI
- 支持深色/浅色系统主题
"""

import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from typing import Optional, Callable

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.platform_detector import detect_platform, PlatformInfo, OSType
from src.core.dependency_manager import DependencyManager
from src.core.network_manager import NetworkManager
from src.core.openclaw_installer import OpenClawInstaller
from src.core.onboard_handler import OnboardHandler
from src.core.daemon_manager import DaemonManager
from src.core.doctor_runner import DoctorRunner
from src.core.error_handler import ErrorHandler
from src.core.config_manager import ConfigManager
from src.utils.logger import setup_logging, LOG_DIR
from src.utils.privilege import check_admin, request_elevation, get_elevation_instructions
from src.utils.security import get_security_notices, validate_security_config

import logging

logger = logging.getLogger("OpenClawInstaller")


class InstallerApp:
    """
    安装程序 GUI 应用
    
    主窗口包含：
    - 顶部标题和描述
    - 中部进度区域（步骤列表 + 进度条）
    - 底部日志输出窗口
    - 安全提示区域
    - 操作按钮
    
    用法:
        app = InstallerApp()
        app.run()
    """
    
    # ── 安装步骤定义 ──
    STEPS = [
        ("检测系统环境", "正在检测操作系统、CPU架构、磁盘空间..."),
        ("检测网络环境", "正在检测网络连通性和镜像源..."),
        ("检查权限", "正在验证管理员权限..."),
        ("安装依赖", "正在安装 Node.js、Python、Git..."),
        ("安装 OpenClaw", "正在下载并安装 OpenClaw..."),
        ("运行初始化向导", "正在运行 openclaw onboard 配置..."),
        ("安装守护进程", "正在配置开机自启动服务..."),
        ("安全配置", "正在应用安全默认配置..."),
        ("运行诊断", "正在验证安装结果..."),
        ("完成", "安装完成！"),
    ]
    
    def __init__(self):
        """初始化 GUI 应用"""
        self.root = tk.Tk()
        self.root.title("OpenClaw 一键安装程序")
        self.root.geometry("700x580")
        self.root.resizable(True, True)
        self.root.minsize(600, 500)
        
        # 居中窗口
        self._center_window()
        
        # 状态变量
        self.platform_info: Optional[PlatformInfo] = None
        self.error_handler = ErrorHandler()
        self.is_installing = False
        self.install_success = False
        
        # 构建 UI
        self._build_ui()
        
        # 显示安全提示
        self._show_security_notices()
    
    def _center_window(self) -> None:
        """将窗口居中显示"""
        self.root.update_idletasks()
        w = 700
        h = 580
        x = (self.root.winfo_screenwidth() - w) // 2
        y = (self.root.winfo_screenheight() - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")
    
    def _build_ui(self) -> None:
        """构建用户界面"""
        # ── 主容器 ──
        main_frame = ttk.Frame(self.root, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # ── 标题区域 ──
        title_frame = ttk.Frame(main_frame)
        title_frame.pack(fill=tk.X, pady=(0, 10))
        
        title_label = ttk.Label(
            title_frame,
            text="OpenClaw 一键安装程序",
            font=("", 18, "bold")
        )
        title_label.pack(side=tk.LEFT)
        
        subtitle_label = ttk.Label(
            title_frame,
            text="零交互 · 零环境依赖 · 全系统兼容",
            font=("", 10),
            foreground="gray"
        )
        subtitle_label.pack(side=tk.LEFT, padx=(15, 0))
        
        # ── 进度区域 ──
        progress_frame = ttk.LabelFrame(main_frame, text="安装进度", padding="10")
        progress_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 当前步骤标签
        self.step_label = ttk.Label(
            progress_frame,
            text="准备就绪，点击「开始安装」",
            font=("", 11)
        )
        self.step_label.pack(fill=tk.X, pady=(0, 5))
        
        # 进度条
        self.progress_bar = ttk.Progressbar(
            progress_frame,
            mode="determinate",
            length=400,
            maximum=100
        )
        self.progress_bar.pack(fill=tk.X, pady=(0, 5))
        
        # 百分比标签
        self.percent_label = ttk.Label(
            progress_frame,
            text="0%",
            font=("", 9),
            foreground="gray"
        )
        self.percent_label.pack(anchor=tk.E)
        
        # ── 步骤列表 ──
        steps_frame = ttk.LabelFrame(main_frame, text="安装步骤", padding="5")
        steps_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.step_indicators: list = []
        for i, (step_name, _) in enumerate(self.STEPS):
            frame = ttk.Frame(steps_frame)
            frame.pack(fill=tk.X, pady=1)
            
            indicator = ttk.Label(frame, text="○", font=("", 10))
            indicator.pack(side=tk.LEFT, padx=(0, 8))
            
            label = ttk.Label(frame, text=step_name, font=("", 9))
            label.pack(side=tk.LEFT)
            
            self.step_indicators.append((indicator, label))
        
        # ── 日志区域 ──
        log_frame = ttk.LabelFrame(main_frame, text="安装日志", padding="5")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            height=8,
            font=("Consolas", 9) if sys.platform == "win32" else ("Menlo", 9),
            state=tk.DISABLED,
            wrap=tk.WORD
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # ── 按钮区域 ──
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X)
        
        self.start_button = ttk.Button(
            button_frame,
            text="开始安装",
            command=self._on_start
        )
        self.start_button.pack(side=tk.LEFT, padx=(0, 10))
        
        self.log_button = ttk.Button(
            button_frame,
            text="打开日志目录",
            command=self._open_log_dir,
            state=tk.DISABLED
        )
        self.log_button.pack(side=tk.LEFT, padx=(0, 10))
        
        self.close_button = ttk.Button(
            button_frame,
            text="关闭",
            command=self.root.quit
        )
        self.close_button.pack(side=tk.RIGHT)
    
    def _show_security_notices(self) -> None:
        """显示安全提示"""
        notices = get_security_notices()
        self._append_log("─" * 50)
        self._append_log("安全提示:")
        for notice in notices:
            self._append_log(f"  • {notice}")
        self._append_log("─" * 50)
    
    def _append_log(self, message: str) -> None:
        """
        向日志窗口追加文本
        
        Args:
            message: 日志消息
        """
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)
    
    def _update_progress(self, step: str, percent: int) -> None:
        """
        更新进度条和步骤标签
        
        Args:
            step: 当前步骤描述
            percent: 进度百分比
        """
        self.step_label.configure(text=step)
        self.progress_bar["value"] = percent
        self.percent_label.configure(text=f"{percent}%")
        self.root.update_idletasks()
    
    def _update_step_indicator(self, step_index: int, status: str = "active") -> None:
        """
        更新步骤指示器
        
        Args:
            step_index: 步骤索引
            status: 状态 ("active" / "done" / "error")
        """
        if step_index >= len(self.step_indicators):
            return
        
        indicator, label = self.step_indicators[step_index]
        
        symbols = {
            "active": ("◉", ""),
            "done": ("✓", ""),
            "error": ("✗", ""),
        }
        
        symbol, _ = symbols.get(status, ("○", ""))
        indicator.configure(text=symbol)
    
    def _on_start(self) -> None:
        """开始安装按钮回调"""
        if self.is_installing:
            return
        
        self.is_installing = True
        self.start_button.configure(state=tk.DISABLED)
        self.log_button.configure(state=tk.NORMAL)
        
        # 在后台线程执行安装
        thread = threading.Thread(target=self._run_installation, daemon=True)
        thread.start()
    
    def _run_installation(self) -> None:
        """
        执行完整安装流程
        
        在后台线程中运行，通过 root.after() 更新 UI。
        安装流程包含 10 个步骤，每步完成后更新 UI。
        """
        try:
            # ── Step 0: 检测系统环境 ──
            self._update_step_ui(0, "检测系统环境中...", 5)
            self._append_log("[1/10] 检测系统环境...")
            
            self.platform_info = detect_platform()
            self._append_log(
                f"  操作系统: {self.platform_info.os_type.value} "
                f"({self.platform_info.os_version[:50]})"
            )
            self._append_log(f"  架构: {self.platform_info.arch.value}")
            self._append_log(f"  管理员权限: {'是' if self.platform_info.is_admin else '否'}")
            self._append_log(f"  磁盘空间: {self.platform_info.disk_space_gb:.1f} GB")
            
            if self.platform_info.disk_space_gb >= 0 and self.platform_info.disk_space_gb < 2.0:
                self._append_log("  ⚠ 磁盘空间不足（需要至少 2GB）")
            
            self._mark_step_done(0)
            
            # ── Step 1: 检测网络环境 ──
            self._update_step_ui(1, "检测网络环境中...", 10)
            self._append_log("[2/10] 检测网络环境...")
            
            network_mgr = NetworkManager(self.platform_info)
            network_status = network_mgr.detect()
            
            self._append_log(
                f"  网络连接: {'可用' if network_status.is_connected else '不可用'}"
            )
            self._append_log(
                f"  国内网络: {'是' if network_status.is_china_network else '否'}"
            )
            self._append_log(f"  推荐镜像: {network_status.recommended_mirror}")
            
            # 配置镜像
            if network_status.recommended_mirror == "china":
                network_mgr.configure_mirrors()
                self._append_log("  已切换为国内镜像源")
            
            self._mark_step_done(1)
            
            # ── Step 2: 检查权限 ──
            self._update_step_ui(2, "检查权限中...", 15)
            self._append_log("[3/10] 检查权限...")
            
            if not self.platform_info.is_admin:
                self._append_log("  当前非管理员权限，尝试请求提权...")
                if request_elevation():
                    self._append_log("  提权成功")
                else:
                    self._append_log("  ⚠ 提权失败，部分操作可能需要手动授权")
            else:
                self._append_log("  已拥有管理员权限")
            
            # macOS 辅助功能权限
            if self.platform_info.os_type == OSType.MACOS:
                from src.utils.privilege import request_macos_accessibility
                request_macos_accessibility()
            
            self._mark_step_done(2)
            
            # ── Step 3: 安装依赖 ──
            self._update_step_ui(3, "安装依赖中...", 20)
            self._append_log("[4/10] 安装依赖...")
            
            dep_mgr = DependencyManager(self.platform_info)
            dep_mgr.set_china_mirror(network_status.is_china_network)
            dep_mgr.check_all()
            
            def dep_progress(step: str, percent: int) -> None:
                overall = 20 + percent * 0.2  # 占总进度的 20%
                self._update_progress(step, int(overall))
            
            dep_success = self.error_handler.with_retry(
                "安装依赖",
                lambda: dep_mgr.install_missing(dep_progress),
                max_retries=2
            )
            
            if dep_success:
                self._append_log("  依赖安装完成")
            else:
                self._append_log("  ⚠ 部分依赖安装失败，将继续尝试安装 OpenClaw")
            
            self._mark_step_done(3)
            
            # ── Step 4: 安装 OpenClaw ──
            self._update_step_ui(4, "安装 OpenClaw 中...", 45)
            self._append_log("[5/10] 安装 OpenClaw...")
            
            installer = OpenClawInstaller(self.platform_info, network_mgr)
            
            def install_progress(step: str, percent: int) -> None:
                overall = 45 + percent * 0.15
                self._update_progress(step, int(overall))
            
            install_result = self.error_handler.with_retry(
                "安装 OpenClaw",
                lambda: installer.install(install_progress),
                max_retries=3
            )
            
            if install_result and install_result.success:
                self._append_log(f"  OpenClaw 安装成功 (方式: {install_result.method})")
                if install_result.version:
                    self._append_log(f"  版本: {install_result.version}")
            else:
                error_msg = install_result.error_message if install_result else "未知错误"
                self._append_log(f"  ✗ OpenClaw 安装失败: {error_msg}")
                self._mark_step_error(4)
                self._show_final_result(False, error_msg)
                return
            
            self._mark_step_done(4)
            
            # ── Step 5: 运行初始化向导 ──
            self._update_step_ui(5, "运行初始化向导中...", 65)
            self._append_log("[6/10] 运行 openclaw onboard...")
            
            onboard = OnboardHandler(self.platform_info)
            api_key = os.environ.get("CUSTOM_API_KEY", "")
            if api_key:
                onboard.set_api_key(api_key)
            
            def onboard_progress(step: str, percent: int) -> None:
                overall = 65 + percent * 0.1
                self._update_progress(step, int(overall))
            
            onboard_result = self.error_handler.with_retry(
                "初始化向导",
                lambda: onboard.run(onboard_progress),
                max_retries=2
            )
            
            if onboard_result and onboard_result.success:
                self._append_log(f"  初始化完成 (模式: {onboard_result.mode.value})")
            else:
                error_msg = onboard_result.error_message if onboard_result else "未知错误"
                self._append_log(f"  ⚠ 自动初始化失败: {error_msg}")
                self._append_log("  您可以稍后手动运行: openclaw onboard")
            
            self._mark_step_done(5)
            
            # ── Step 6: 安装守护进程 ──
            self._update_step_ui(6, "安装守护进程中...", 78)
            self._append_log("[7/10] 安装守护进程...")
            
            daemon_mgr = DaemonManager(self.platform_info)
            
            def daemon_progress(step: str, percent: int) -> None:
                overall = 78 + percent * 0.05
                self._update_progress(step, int(overall))
            
            daemon_success = daemon_mgr.install_and_start(daemon_progress)
            
            if daemon_success:
                self._append_log("  守护进程安装成功，已设置开机自启")
            else:
                self._append_log("  ⚠ 守护进程安装失败，OpenClaw 将不会自动启动")
                self._append_log("  您可以手动运行: openclaw daemon start")
            
            self._mark_step_done(6)
            
            # ── Step 7: 安全配置 ──
            self._update_step_ui(7, "应用安全配置中...", 85)
            self._append_log("[8/10] 应用安全配置...")
            
            config_mgr = ConfigManager(self.platform_info)
            config_mgr.load()
            config_mgr.apply_security_defaults()
            if api_key:
                config_mgr.set_api_key(api_key)
            config_mgr.save()
            
            self._append_log("  安全配置已应用:")
            self._append_log("    • 监听地址: 127.0.0.1（仅本地访问）")
            self._append_log("    • 遥测: 已关闭")
            
            # 安全验证
            config_warnings = validate_security_config(config_mgr.get_config_summary())
            for warning in config_warnings:
                self._append_log(f"    {warning}")
            
            self._mark_step_done(7)
            
            # ── Step 8: 运行诊断 ──
            self._update_step_ui(8, "运行诊断中...", 90)
            self._append_log("[9/10] 运行诊断验证...")
            
            doctor = DoctorRunner(self.platform_info)
            diag = doctor.run_diagnosis()
            
            if diag.healthy:
                self._append_log("  ✓ 诊断通过，安装健康")
            else:
                self._append_log(f"  发现 {len(diag.issues)} 个问题:")
                for issue in diag.issues:
                    self._append_log(f"    - {issue[:80]}")
                
                if diag.fixable:
                    self._append_log("  尝试自动修复...")
                    diag = doctor.attempt_repair(diag)
                    if diag.healthy:
                        self._append_log("  ✓ 修复成功")
                    else:
                        self._append_log("  ⚠ 部分问题无法自动修复")
                        self._append_log("  请运行: openclaw doctor --repair")
            
            self._mark_step_done(8)
            
            # ── Step 9: 完成 ──
            self._update_step_ui(9, "安装完成！", 100)
            self._append_log("[10/10] 安装完成！")
            self._append_log("")
            self._append_log("OpenClaw 已成功安装并配置完成。")
            self._append_log("您可以通过以下命令使用:")
            self._append_log("  openclaw --version    # 查看版本")
            self._append_log("  openclaw doctor       # 运行诊断")
            self._append_log("  openclaw daemon start # 启动服务")
            self._append_log("")
            self._append_log(f"安装日志保存在: {LOG_DIR}")
            
            self._mark_step_done(9)
            self.install_success = True
            self._show_final_result(True)
            
        except Exception as e:
            logger.error(f"安装过程异常: {e}", exc_info=True)
            self._append_log(f"\n✗ 安装过程发生异常: {e}")
            self._append_log(f"错误日志: {self.error_handler.get_error_report_path()}")
            self._show_final_result(False, str(e))
        
        finally:
            self.is_installing = False
            self.start_button.configure(state=tk.NORMAL, text="重新安装")
    
    def _update_step_ui(self, step_index: int, message: str, percent: int) -> None:
        """
        在主线程中更新步骤 UI
        
        Args:
            step_index: 步骤索引
            message: 进度消息
            percent: 进度百分比
        """
        self.root.after(0, lambda: self._update_progress(message, percent))
        self.root.after(0, lambda: self._update_step_indicator(step_index, "active"))
    
    def _mark_step_done(self, step_index: int) -> None:
        """标记步骤完成"""
        self.root.after(0, lambda: self._update_step_indicator(step_index, "done"))
    
    def _mark_step_error(self, step_index: int) -> None:
        """标记步骤失败"""
        self.root.after(0, lambda: self._update_step_indicator(step_index, "error"))
    
    def _show_final_result(self, success: bool, error_message: str = "") -> None:
        """
        显示最终安装结果
        
        Args:
            success: 是否安装成功
            error_message: 错误消息（如有）
        """
        if success:
            self.root.after(0, lambda: messagebox.showinfo(
                "安装完成",
                "OpenClaw 已成功安装！\n\n"
                "使用方法:\n"
                "  openclaw --version    查看版本\n"
                "  openclaw doctor       运行诊断\n"
                "  openclaw daemon start 启动服务\n\n"
                f"日志目录: {LOG_DIR}"
            ))
        else:
            self.root.after(0, lambda: messagebox.showerror(
                "安装失败",
                f"OpenClaw 安装过程中出现错误。\n\n"
                f"错误信息: {error_message[:200]}\n\n"
                f"请查看日志获取详细信息:\n"
                f"  {self.error_handler.get_error_report_path()}\n\n"
                f"您也可以尝试手动安装:\n"
                f"  curl -fsSL https://openclaw.ai/install.sh | bash"
            ))
    
    def _open_log_dir(self) -> None:
        """打开日志目录"""
        import subprocess
        try:
            if sys.platform == "win32":
                os.startfile(LOG_DIR)  # type: ignore
            elif sys.platform == "darwin":
                subprocess.run(["open", LOG_DIR])
            else:
                subprocess.run(["xdg-open", LOG_DIR])
        except Exception:
            messagebox.showinfo("日志目录", f"日志保存在: {LOG_DIR}")
    
    def run(self) -> None:
        """启动 GUI 主循环"""
        # 初始化日志系统
        setup_logging()
        
        logger.info("OpenClaw 安装程序启动")
        
        # 检查权限（非阻塞提示）
        if not check_admin():
            self._append_log("⚠ 当前非管理员权限，建议以管理员身份运行")
            self._append_log(f"  {get_elevation_instructions()}")
        
        self.root.mainloop()


# ── 命令行模式（无 GUI 时自动降级） ──

def run_cli() -> None:
    """
    命令行模式运行安装程序
    
    当 tkinter 不可用（如无显示器的服务器环境）时自动降级为此模式。
    """
    setup_logging()
    
    print("=" * 50)
    print("  OpenClaw 一键安装程序 (命令行模式)")
    print("=" * 50)
    print()
    
    # 显示安全提示
    for notice in get_security_notices():
        print(f"  • {notice}")
    print()
    
    # 检查权限
    if not check_admin():
        print("⚠ 非管理员权限运行，部分操作可能失败")
        print(f"  {get_elevation_instructions()}")
        print()
    
    # 执行安装流程（与 GUI 相同的逻辑，但不更新 UI）
    print("[1/10] 检测系统环境...")
    platform_info = detect_platform()
    print(f"  系统: {platform_info.os_type.value}/{platform_info.arch.value}")
    
    print("[2/10] 检测网络环境...")
    network_mgr = NetworkManager(platform_info)
    network_status = network_mgr.detect()
    if network_status.is_china_network:
        network_mgr.configure_mirrors()
    
    print("[3/10] 安装依赖...")
    dep_mgr = DependencyManager(platform_info)
    dep_mgr.set_china_mirror(network_status.is_china_network)
    dep_mgr.check_all()
    dep_mgr.install_missing()
    
    print("[4/10] 安装 OpenClaw...")
    installer = OpenClawInstaller(platform_info, network_mgr)
    result = installer.install()
    
    if result.success:
        print(f"  ✓ 安装成功 (v{result.version})")
    else:
        print(f"  ✗ 安装失败: {result.error_message}")
        return
    
    print("[5/10] 运行初始化向导...")
    onboard = OnboardHandler(platform_info)
    api_key = os.environ.get("CUSTOM_API_KEY", "")
    if api_key:
        onboard.set_api_key(api_key)
    onboard.run()
    
    print("[6/10] 安装守护进程...")
    daemon_mgr = DaemonManager(platform_info)
    daemon_mgr.install_and_start()
    
    print("[7/10] 安全配置...")
    config_mgr = ConfigManager(platform_info)
    config_mgr.load()
    config_mgr.apply_security_defaults()
    if api_key:
        config_mgr.set_api_key(api_key)
    config_mgr.save()
    
    print("[8/10] 运行诊断...")
    doctor = DoctorRunner(platform_info)
    diag = doctor.run_diagnosis()
    if not diag.healthy and diag.fixable:
        doctor.attempt_repair(diag)
    
    print()
    print("=" * 50)
    print("  安装完成！")
    print("=" * 50)
    print()
    print("使用命令:")
    print("  openclaw --version    # 查看版本")
    print("  openclaw doctor       # 运行诊断")
    print("  openclaw daemon start # 启动服务")
    print()
    print(f"日志目录: {LOG_DIR}")


if __name__ == "__main__":
    # 尝试使用 GUI 模式，失败则降级为命令行模式
    try:
        app = InstallerApp()
        app.run()
    except (tk.TclError, ImportError):
        print("GUI 不可用，切换到命令行模式...")
        run_cli()
