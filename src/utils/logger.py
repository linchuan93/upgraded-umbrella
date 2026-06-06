"""
OpenClaw 一键安装程序 - 日志记录模块

功能：
1. 配置统一的日志格式
2. 同时输出到控制台和文件
3. 支持不同日志级别
4. 日志文件自动轮转

设计原则：
- 日志格式统一：时间 | 级别 | 模块 | 消息
- 文件日志保存到 ~/OpenClaw_Installer_Logs/ 目录
- 控制台日志使用彩色输出（如支持）
"""

import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from typing import Optional

# ── 日志目录 ──
LOG_DIR = os.path.join(os.path.expanduser("~"), "OpenClaw_Installer_Logs")
LOG_FILE = os.path.join(LOG_DIR, "install.log")


def setup_logging(level: int = logging.INFO, log_to_file: bool = True) -> logging.Logger:
    """
    配置日志系统
    
    创建统一的日志格式，同时输出到控制台和文件。
    文件日志使用 RotatingFileHandler，自动轮转（最大 5MB，保留 3 个备份）。
    
    Args:
        level: 日志级别（默认 INFO）
        log_to_file: 是否同时写入文件（默认 True）
        
    Returns:
        logging.Logger: 配置好的根日志器
    """
    # 确保日志目录存在
    os.makedirs(LOG_DIR, exist_ok=True)
    
    # 获取根日志器
    root_logger = logging.getLogger("OpenClawInstaller")
    root_logger.setLevel(level)
    
    # 防止重复添加 handler
    if root_logger.handlers:
        return root_logger
    
    # ── 日志格式 ──
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # ── 控制台 handler ──
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # ── 文件 handler ──
    if log_to_file:
        try:
            file_handler = RotatingFileHandler(
                LOG_FILE,
                maxBytes=5 * 1024 * 1024,  # 5MB
                backupCount=3,
                encoding="utf-8"
            )
            file_handler.setLevel(logging.DEBUG)  # 文件记录所有级别
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
        except Exception as e:
            root_logger.warning(f"文件日志初始化失败: {e}")
    
    return root_logger


def get_logger(name: str) -> logging.Logger:
    """
    获取子日志器
    
    Args:
        name: 子模块名称
        
    Returns:
        logging.Logger: 子日志器
    """
    return logging.getLogger(f"OpenClawInstaller.{name}")
