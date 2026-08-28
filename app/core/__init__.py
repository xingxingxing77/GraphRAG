"""
核心配置与契约层（D1 契约唯一来源，05 §3.1）。
"""
from app.core.config import AppSettings, get_settings

__all__ = ["AppSettings", "get_settings"]
