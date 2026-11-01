"""oci-manager: 仅管理 Oracle Cloud (OCI) 的 Web 面板 + Telegram Bot + Web SSH。

设计原则（对齐 R-Bot 的安全模型）：
1. 云 API 私钥只存在部署本程序的机器上，不经过第三方服务器；
2. 本程序本身不存储 Telegram 之外的任何云密钥；
3. 所有危险操作（终止实例、删卷、删桶）都要求调用方显式确认。
"""

__version__ = "0.1.0"
