"""
OpenClaw 一键安装程序 - 网络检测与镜像配置模块

功能：
1. 检测当前网络连通性
2. 自动识别国内网络环境
3. 自动配置 npm/pip 等工具使用国内镜像源
4. 网络超时自动切换镜像源

设计原则：
- 网络检测采用多节点并行 ping，快速判断连通性
- 镜像切换是可逆的，记录原始配置以便回退
- 所有网络操作设置合理超时，避免长时间阻塞
"""

import subprocess
import logging
import time
import os
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field

from .platform_detector import PlatformInfo, OSType

logger = logging.getLogger("OpenClawInstaller")

# ── 网络检测目标 ──
CONNECTIVITY_TARGETS = {
    "official_npm": ("registry.npmjs.org", 443),
    "official_nodejs": ("nodejs.org", 443),
    "official_python": ("pypi.org", 443),
    "china_npm_mirror": ("registry.npmmirror.com", 443),
    "china_node_mirror": ("npmmirror.com", 443),
    "china_pip_mirror": ("pypi.tuna.tsinghua.edu.cn", 443),
    "openclaw": ("openclaw.ai", 443),
}

# ── 国内镜像配置 ──
MIRROR_CONFIG = {
    "npm": {
        "official": "https://registry.npmjs.org",
        "china": "https://registry.npmmirror.com",
    },
    "pip": {
        "official": "https://pypi.org/simple",
        "china": "https://pypi.tuna.tsinghua.edu.cn/simple",
    },
    "node_download": {
        "official": "https://nodejs.org/dist",
        "china": "https://npmmirror.com/mirrors/node",
    },
    "python_download": {
        "official": "https://www.python.org/ftp/python",
        "china": "https://repo.huaweicloud.com/python",
    },
}


@dataclass
class NetworkStatus:
    """网络状态数据类"""
    is_connected: bool = False
    is_china_network: bool = False
    can_reach_official: bool = False
    can_reach_china_mirror: bool = False
    latency_official_ms: float = -1.0
    latency_china_mirror_ms: float = -1.0
    recommended_mirror: str = "official"  # "official" or "china"


class NetworkManager:
    """
    网络管理器
    
    负责：
    1. 检测网络连通性和延迟
    2. 判断是否需要使用国内镜像
    3. 自动配置 npm/pip 等工具的镜像源
    4. 网络故障时自动切换镜像
    
    用法:
        nm = NetworkManager(platform_info)
        status = nm.detect()
        if status.is_china_network:
            nm.configure_mirrors()
    """
    
    def __init__(self, platform_info: PlatformInfo):
        """
        初始化网络管理器
        
        Args:
            platform_info: 平台信息对象
        """
        self.platform = platform_info
        self.status = NetworkStatus()
        self._original_configs: Dict[str, str] = {}  # 保存原始配置以便回退
    
    def detect(self) -> NetworkStatus:
        """
        执行网络检测
        
        检测流程：
        1. 检查基本网络连通性
        2. 测试官方源延迟
        3. 测试国内镜像延迟
        4. 根据延迟判断网络环境
        5. 推荐最优镜像源
        
        Returns:
            NetworkStatus: 网络状态信息
        """
        logger.info("开始网络检测...")
        
        # ── 1. 基本连通性检测 ──
        self.status.is_connected = self._check_basic_connectivity()
        if not self.status.is_connected:
            logger.error("网络不可用，请检查网络连接")
            return self.status
        
        # ── 2. 并行测试官方源和国内镜像延迟 ──
        self.status.can_reach_official, self.status.latency_official_ms = \
            self._measure_latency("registry.npmjs.org", 443)
        self.status.can_reach_china_mirror, self.status.latency_china_mirror_ms = \
            self._measure_latency("registry.npmmirror.com", 443)
        
        # ── 3. 判断网络环境 ──
        # 如果官方源延迟 > 2000ms 或无法连接，且国内镜像可用 → 判定为国内网络
        if self.status.can_reach_china_mirror:
            if not self.status.can_reach_official or self.status.latency_official_ms > 2000:
                self.status.is_china_network = True
                self.status.recommended_mirror = "china"
                logger.info("检测到国内网络环境，推荐使用国内镜像源")
            elif self.status.latency_china_mirror_ms < self.status.latency_official_ms * 0.5:
                # 国内镜像明显更快
                self.status.is_china_network = True
                self.status.recommended_mirror = "china"
                logger.info("国内镜像源延迟更低，推荐使用国内镜像")
            else:
                self.status.recommended_mirror = "official"
                logger.info("官方源连接正常，使用官方源")
        elif self.status.can_reach_official:
            self.status.recommended_mirror = "official"
            logger.info("仅官方源可达，使用官方源")
        else:
            logger.error("官方源和国内镜像均不可达")
        
        logger.info(
            f"网络检测完成: 连接={'是' if self.status.is_connected else '否'}, "
            f"国内网络={'是' if self.status.is_china_network else '否'}, "
            f"官方延迟={self.status.latency_official_ms:.0f}ms, "
            f"镜像延迟={self.status.latency_china_mirror_ms:.0f}ms"
        )
        
        return self.status
    
    def configure_mirrors(self, force_china: bool = False) -> bool:
        """
        配置包管理器镜像源
        
        根据 recommended_mirror 自动配置 npm 和 pip 的 registry。
        如果 force_china=True，则无论检测结果如何都使用国内镜像。
        
        Args:
            force_china: 是否强制使用国内镜像
            
        Returns:
            bool: 配置是否成功
        """
        mirror_type = "china" if (force_china or self.status.recommended_mirror == "china") else "official"
        
        logger.info(f"配置镜像源: {mirror_type}")
        
        success = True
        
        # ── 配置 npm registry ──
        npm_registry = MIRROR_CONFIG["npm"][mirror_type]
        if not self._configure_npm_registry(npm_registry):
            success = False
        
        # ── 配置 pip 镜像 ──
        pip_index = MIRROR_CONFIG["pip"][mirror_type]
        if not self._configure_pip_index(pip_index):
            success = False  # pip 配置失败不阻塞，只记录
        
        return success
    
    def restore_mirrors(self) -> None:
        """
        恢复原始镜像配置
        
        在安装完成或失败时调用，将 npm/pip 恢复为用户原始配置。
        """
        for key, value in self._original_configs.items():
            try:
                if key == "npm_registry":
                    subprocess.run(
                        ["npm", "config", "set", "registry", value],
                        capture_output=True, timeout=10
                    )
                elif key == "pip_index":
                    pip_conf = os.path.expanduser("~/.pip/pip.conf")
                    if os.path.exists(pip_conf):
                        # 简单替换 index-url
                        with open(pip_conf, "r") as f:
                            content = f.read()
                        if value in content:
                            logger.info(f"已恢复 pip 配置: {value}")
            except Exception as e:
                logger.warning(f"恢复 {key} 配置失败: {e}")
    
    # ── 内部方法 ──
    
    def _check_basic_connectivity(self) -> bool:
        """
        检查基本网络连通性
        
        尝试连接多个已知可靠的服务器。
        
        Returns:
            bool: 网络是否可用
        """
        test_hosts = ["8.8.8.8", "1.1.1.1", "223.5.5.5"]  # DNS 服务器
        
        for host in test_hosts:
            try:
                if self.platform.os_type == OSType.WINDOWS:
                    result = subprocess.run(
                        ["ping", "-n", "1", "-w", "3000", host],
                        capture_output=True, timeout=5
                    )
                else:
                    result = subprocess.run(
                        ["ping", "-c", "1", "-W", "3", host],
                        capture_output=True, timeout=5
                    )
                if result.returncode == 0:
                    return True
            except Exception:
                continue
        
        return False
    
    def _measure_latency(self, host: str, port: int) -> Tuple[bool, float]:
        """
        测量到指定主机的网络延迟
        
        使用 TCP 连接测试（比 ping 更准确，因为某些服务器禁 ICMP）。
        
        Args:
            host: 目标主机
            port: 目标端口
            
        Returns:
            Tuple[bool, float]: (是否可达, 延迟毫秒数)
        """
        import socket
        
        try:
            start = time.time()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((host, port))
            latency = (time.time() - start) * 1000  # 转为毫秒
            sock.close()
            return True, latency
        except (socket.timeout, socket.error, OSError) as e:
            logger.debug(f"连接 {host}:{port} 失败: {e}")
            return False, -1.0
    
    def _configure_npm_registry(self, registry: str) -> bool:
        """
        配置 npm registry
        
        先保存当前配置，再设置新的 registry。
        
        Args:
            registry: 新的 registry URL
            
        Returns:
            bool: 是否配置成功
        """
        try:
            # 保存当前配置
            result = subprocess.run(
                ["npm", "config", "get", "registry"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                current = result.stdout.strip()
                self._original_configs["npm_registry"] = current
                logger.debug(f"当前 npm registry: {current}")
            
            # 设置新配置
            result = subprocess.run(
                ["npm", "config", "set", "registry", registry],
                capture_output=True, timeout=10
            )
            if result.returncode == 0:
                logger.info(f"npm registry 已设置为: {registry}")
                return True
            else:
                logger.warning(f"npm registry 设置失败")
                return False
                
        except FileNotFoundError:
            # npm 尚未安装，跳过（后续安装 Node.js 后再配置）
            logger.debug("npm 未安装，跳过 registry 配置")
            return True
        except Exception as e:
            logger.warning(f"npm registry 配置异常: {e}")
            return False
    
    def _configure_pip_index(self, index_url: str) -> bool:
        """
        配置 pip 镜像源
        
        Args:
            index_url: pip index URL
            
        Returns:
            bool: 是否配置成功
        """
        try:
            pip_path = self.platform.python_path or "pip3"
            
            # 保存当前配置
            result = subprocess.run(
                [pip_path, "config", "get", "global.index-url"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0 and result.stdout.strip():
                self._original_configs["pip_index"] = result.stdout.strip()
            
            # 设置新配置
            result = subprocess.run(
                [pip_path, "config", "set", "global.index-url", index_url],
                capture_output=True, timeout=10
            )
            if result.returncode == 0:
                logger.info(f"pip index 已设置为: {index_url}")
                return True
            else:
                logger.warning("pip index 设置失败")
                return False
                
        except FileNotFoundError:
            logger.debug("pip 未安装，跳过 index 配置")
            return True
        except Exception as e:
            logger.warning(f"pip index 配置异常: {e}")
            return False
    
    def check_port_available(self, port: int) -> Tuple[bool, Optional[str]]:
        """
        检查指定端口是否可用
        
        Args:
            port: 端口号
            
        Returns:
            Tuple[bool, Optional[str]]: (是否可用, 占用进程信息)
        """
        import socket
        
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(("127.0.0.1", port))
            sock.close()
            
            if result == 0:
                # 端口被占用，尝试获取占用进程
                process_info = self._get_port_process(port)
                return False, process_info
            else:
                return True, None
                
        except Exception as e:
            logger.debug(f"端口 {port} 检测异常: {e}")
            return True, None
    
    def find_available_port(self, start_port: int = 3000, max_attempts: int = 100) -> int:
        """
        从指定端口开始，查找第一个可用端口
        
        Args:
            start_port: 起始端口号
            max_attempts: 最大尝试次数
            
        Returns:
            int: 可用端口号，若未找到返回 -1
        """
        for port in range(start_port, start_port + max_attempts):
            available, _ = self.check_port_available(port)
            if available:
                logger.info(f"找到可用端口: {port}")
                return port
        logger.error(f"在 {start_port}-{start_port + max_attempts} 范围内未找到可用端口")
        return -1
    
    def _get_port_process(self, port: int) -> Optional[str]:
        """
        获取占用指定端口的进程信息
        
        Args:
            port: 端口号
            
        Returns:
            Optional[str]: 进程信息字符串
        """
        try:
            if self.platform.os_type == OSType.WINDOWS:
                result = subprocess.run(
                    ["netstat", "-ano"],
                    capture_output=True, text=True, timeout=5
                )
                for line in result.stdout.splitlines():
                    if f":{port}" in line and "LISTENING" in line:
                        parts = line.split()
                        pid = parts[-1]
                        return f"PID: {pid}"
            else:
                result = subprocess.run(
                    ["lsof", "-i", f":{port}", "-P", "-n"],
                    capture_output=True, text=True, timeout=5
                )
                if result.stdout.strip():
                    return result.stdout.strip().splitlines()[0]
        except Exception:
            pass
        return None
