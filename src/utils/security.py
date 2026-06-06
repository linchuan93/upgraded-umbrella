"""
OpenClaw 一键安装程序 - 安全检查模块

功能：
1. 安全配置验证（监听地址、端口等）
2. 安全风险提示
3. SHA-256 哈希值计算与校验
4. 隐私声明

设计原则：
- 默认安全配置（127.0.0.1 监听）
- 所有安全提示对用户可见
- 不收集任何用户隐私信息
"""

import os
import hashlib
import logging
from typing import Optional

from .logger import get_logger

logger = get_logger("security")


# ── 安全提示内容 ──
SECURITY_NOTICES = [
    "本程序不会收集任何个人信息，所有安装过程均在本地执行。",
    "请设置强密码保护您的 OpenClaw 服务。",
    "不要将服务端口暴露在公网，默认监听 127.0.0.1。",
    "警惕提示词注入攻击，不要将未经验证的输入直接传递给 AI 模型。",
    "建议定期更新 OpenClaw 到最新版本以获取安全补丁。",
]


def calculate_file_hash(file_path: str, algorithm: str = "sha256") -> Optional[str]:
    """
    计算文件的哈希值
    
    Args:
        file_path: 文件路径
        algorithm: 哈希算法（默认 SHA-256）
        
    Returns:
        Optional[str]: 哈希值字符串，文件不存在时返回 None
    """
    if not os.path.exists(file_path):
        logger.warning(f"文件不存在: {file_path}")
        return None
    
    try:
        h = hashlib.new(algorithm)
        with open(file_path, "rb") as f:
            # 分块读取，避免大文件占用过多内存
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        hash_value = h.hexdigest()
        logger.info(f"文件哈希 ({algorithm}): {file_path} = {hash_value}")
        return hash_value
    except Exception as e:
        logger.error(f"哈希计算失败: {e}")
        return None


def verify_file_hash(file_path: str, expected_hash: str, algorithm: str = "sha256") -> bool:
    """
    校验文件哈希值
    
    Args:
        file_path: 文件路径
        expected_hash: 期望的哈希值
        algorithm: 哈希算法
        
    Returns:
        bool: 哈希值是否匹配
    """
    actual_hash = calculate_file_hash(file_path, algorithm)
    if actual_hash is None:
        return False
    
    if actual_hash.lower() != expected_hash.lower():
        logger.error(
            f"文件哈希校验失败!\n"
            f"  期望: {expected_hash}\n"
            f"  实际: {actual_hash}\n"
            f"  文件可能已被篡改，请重新下载。"
        )
        return False
    
    logger.info("文件哈希校验通过")
    return True


def validate_security_config(config: dict) -> list:
    """
    验证安全配置
    
    检查配置中是否存在不安全的设置，返回警告列表。
    
    Args:
        config: 配置字典
        
    Returns:
        list: 安全警告列表
    """
    warnings = []
    
    # 检查监听地址
    listen_address = config.get("listen_address", "127.0.0.1")
    if listen_address == "0.0.0.0":
        warnings.append(
            "⚠ 监听地址设为 0.0.0.0，服务将对所有网络接口开放。"
            "请确保已设置强密码和防火墙规则。"
        )
    
    # 检查端口
    port = config.get("port", 3000)
    if port in (80, 443, 8080):
        warnings.append(
            f"⚠ 端口 {port} 是常用端口，可能与其他服务冲突。"
            "建议使用 3000-9000 范围内的非特权端口。"
        )
    
    # 检查遥测
    if config.get("telemetry_enabled", False):
        warnings.append(
            "ℹ 遥测已启用。安装程序不会发送任何数据，"
            "但 OpenClaw 本身的遥测功能可能会收集使用数据。"
        )
    
    # 检查 API Key
    if not config.get("api_key"):
        warnings.append(
            "ℹ 未设置 API Key。您需要在首次使用前配置 API Key。"
        )
    
    return warnings


def get_security_notices() -> list:
    """
    获取安全提示列表
    
    Returns:
        list: 安全提示字符串列表
    """
    return SECURITY_NOTICES.copy()


def generate_integrity_report(installer_path: str) -> str:
    """
    生成安装程序完整性报告
    
    包含文件大小、SHA-256 哈希值等信息，
    供用户校验下载文件的完整性。
    
    Args:
        installer_path: 安装程序文件路径
        
    Returns:
        str: 完整性报告文本
    """
    report_lines = [
        "OpenClaw 安装程序 - 完整性校验报告",
        "=" * 40,
    ]
    
    if os.path.exists(installer_path):
        file_size = os.path.getsize(installer_path)
        sha256 = calculate_file_hash(installer_path, "sha256")
        
        report_lines.extend([
            f"文件: {os.path.basename(installer_path)}",
            f"大小: {file_size:,} bytes ({file_size / (1024*1024):.1f} MB)",
            f"SHA-256: {sha256 or '计算失败'}",
        ])
    else:
        report_lines.append("文件不存在")
    
    report_lines.extend([
        "",
        "校验方法:",
        "  Windows: certutil -hashfile OpenClaw_Installer.exe SHA256",
        "  macOS: shasum -a 256 OpenClaw_Installer.app",
        "  Linux: sha256sum OpenClaw_Installer.AppImage",
    ])
    
    return "\n".join(report_lines)
