"""日志配置：同时输出到控制台与文件。"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_FILE_MAX_BYTES = 5 * 1024 * 1024  # 单个日志文件最大 5MB
LOG_FILE_BACKUP_COUNT = 3  # 最多保留 3 个滚动备份

_configured = False


def setup_logging(level: str = "INFO", log_file: Path | None = None) -> None:
    """初始化全局日志：控制台 + 滚动文件双输出，重复调用安全。"""
    global _configured
    if _configured:
        return

    root_logger = logging.getLogger()
    root_logger.setLevel(level.upper())
    formatter = logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=LOG_FILE_MAX_BYTES,
            backupCount=LOG_FILE_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """获取命名日志器。"""
    return logging.getLogger(name)
