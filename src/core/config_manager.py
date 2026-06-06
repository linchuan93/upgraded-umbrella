"""
OpenClaw 一键安装程序 - 配置管理模块

功能：
1. 管理 OpenClaw 配置文件的读写
2. 支持预置 API Key
3. 支持端口配置
4. 支持监听地址配置（默认 127.0.0.1）
5. 配置文件备份与回滚

设计原则：
- 配置文件使用 JSON 格式（可读性好，解析方便）
- 所有修改前自动备份原文件
- 提供 rollback 方法回滚到上一个版本
- 敏感信息（API Key）不直接写入日志
"""

import os
import json
import shutil
import logging
import time
from typing import Optional, Dict, Any
from dataclasses import dataclass, field, asdict
from pathlib import Path

from .platform_detector import PlatformInfo, OSType

logger = logging.getLogger("OpenClawInstaller")


@dataclass
class OpenClawConfig:
    """OpenClaw 配置数据类"""
    # API 配置
    api_key: str = ""
    api_provider: str = "anthropic"  # anthropic / openai / custom
    
    # 网络配置
    listen_address: str = "127.0.0.1"  # 默认只监听本地，不暴露公网
    port: int = 3000
    
    # 守护进程配置
    daemon_enabled: bool = True
    daemon_autostart: bool = True
    
    # 日志配置
    log_level: str = "info"
    log_path: str = ""
    
    # 其他
    telemetry_enabled: bool = False  # 默认关闭遥测
    auto_update: bool = True


class ConfigManager:
    """
    配置管理器
    
    负责：
    1. 读写 OpenClaw 配置文件
    2. 预置 API Key 等敏感信息
    3. 安全配置（监听地址、端口等）
    4. 配置备份与回滚
    
    用法:
        cm = ConfigManager(platform_info)
        cm.load()
        cm.set_api_key("sk-xxx")
        cm.set_port(8080)
        cm.save()
    """
    
    def __init__(self, platform_info: PlatformInfo):
        """
        初始化配置管理器
        
        Args:
            platform_info: 平台信息对象
        """
        self.platform = platform_info
        self.config = OpenClawConfig()
        self._config_path = self._get_config_path()
        self._backup_dir = os.path.join(
            os.path.expanduser("~"), ".openclaw", "config_backups"
        )
    
    def load(self) -> bool:
        """
        加载配置文件
        
        如果配置文件不存在，使用默认配置。
        
        Returns:
            bool: 是否成功加载
        """
        if not os.path.exists(self._config_path):
            logger.info(f"配置文件不存在，使用默认配置: {self._config_path}")
            return True
        
        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # 合并到配置对象
            for key, value in data.items():
                if hasattr(self.config, key):
                    setattr(self.config, key, value)
            
            logger.info(f"配置已加载: {self._config_path}")
            return True
            
        except json.JSONDecodeError as e:
            logger.warning(f"配置文件格式错误: {e}，使用默认配置")
            return False
        except Exception as e:
            logger.warning(f"配置加载异常: {e}")
            return False
    
    def save(self) -> bool:
        """
        保存配置文件
        
        保存前自动备份当前配置。
        
        Returns:
            bool: 是否成功保存
        """
        # 先备份
        self._backup()
        
        try:
            # 确保目录存在
            config_dir = os.path.dirname(self._config_path)
            if config_dir:
                os.makedirs(config_dir, exist_ok=True)
            
            # 写入配置
            data = asdict(self.config)
            
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"配置已保存: {self._config_path}")
            return True
            
        except Exception as e:
            logger.error(f"配置保存失败: {e}")
            return False
    
    def set_api_key(self, api_key: str) -> None:
        """
        设置 API Key
        
        Args:
            api_key: API Key 字符串
        """
        self.config.api_key = api_key
        logger.info("API Key 已设置")
    
    def set_port(self, port: int) -> None:
        """
        设置监听端口
        
        Args:
            port: 端口号
        """
        self.config.port = port
        logger.info(f"端口已设置为: {port}")
    
    def set_listen_address(self, address: str) -> None:
        """
        设置监听地址
        
        出于安全考虑，默认为 127.0.0.1。
        用户若需远程访问可手动修改为 0.0.0.0。
        
        Args:
            address: 监听地址
        """
        self.config.listen_address = address
        if address != "127.0.0.1":
            logger.warning(
                f"监听地址设置为 {address}，服务将对外暴露。"
                "请确保已设置强密码和防火墙规则！"
            )
    
    def apply_security_defaults(self) -> None:
        """
        应用安全默认配置
        
        包括：
        - 监听地址设为 127.0.0.1（不暴露公网）
        - 关闭遥测
        - 启用守护进程
        """
        self.config.listen_address = "127.0.0.1"
        self.config.telemetry_enabled = False
        self.config.daemon_enabled = True
        logger.info("已应用安全默认配置")
    
    def rollback(self) -> bool:
        """
        回滚到上一个配置版本
        
        Returns:
            bool: 是否回滚成功
        """
        if not os.path.exists(self._backup_dir):
            logger.warning("无配置备份可回滚")
            return False
        
        try:
            backups = sorted(os.listdir(self._backup_dir), reverse=True)
            if not backups:
                return False
            
            latest_backup = os.path.join(self._backup_dir, backups[0])
            shutil.copy2(latest_backup, self._config_path)
            logger.info(f"配置已回滚: {latest_backup}")
            return self.load()
            
        except Exception as e:
            logger.error(f"配置回滚失败: {e}")
            return False
    
    def get_config_summary(self) -> Dict[str, Any]:
        """
        获取配置摘要（隐藏敏感信息）
        
        Returns:
            Dict: 配置摘要字典
        """
        data = asdict(self.config)
        # 隐藏 API Key
        if data.get("api_key"):
            data["api_key"] = data["api_key"][:8] + "..." + data["api_key"][-4:]
        return data
    
    def _get_config_path(self) -> str:
        """
        获取配置文件路径
        
        不同平台的配置文件位置：
        - Windows: %APPDATA%/openclaw/config.json
        - macOS: ~/.openclaw/config.json
        - Linux: ~/.openclaw/config.json
        
        Returns:
            str: 配置文件绝对路径
        """
        if self.platform.os_type == OSType.WINDOWS:
            app_data = os.environ.get("APPDATA", os.path.expanduser("~"))
            return os.path.join(app_data, "openclaw", "config.json")
        else:
            return os.path.join(os.path.expanduser("~"), ".openclaw", "config.json")
    
    def _backup(self) -> None:
        """
        备份当前配置文件
        
        保留最近 5 个备份，自动清理旧备份。
        """
        if not os.path.exists(self._config_path):
            return
        
        try:
            os.makedirs(self._backup_dir, exist_ok=True)
            
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            backup_name = f"config_{timestamp}.json"
            backup_path = os.path.join(self._backup_dir, backup_name)
            
            shutil.copy2(self._config_path, backup_path)
            
            # 清理旧备份（保留最近 5 个）
            backups = sorted(os.listdir(self._backup_dir))
            while len(backups) > 5:
                old_backup = os.path.join(self._backup_dir, backups[0])
                os.unlink(old_backup)
                backups.pop(0)
            
            logger.debug(f"配置已备份: {backup_path}")
            
        except Exception as e:
            logger.warning(f"配置备份失败: {e}")
