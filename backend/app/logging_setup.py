"""滚动文件日志:按天 + 单文件 50MB 双触发滚动,保留 7 天,全局单 handler。"""
from __future__ import annotations

import logging
import os
import glob
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
MAX_BYTES = 50 * 1024 * 1024
KEEP_DAYS = 7

_handler: logging.Handler | None = None


class DailySizeRotatingHandler(RotatingFileHandler):
    """按天滚动 + 超过 MAX_BYTES 立即滚动(大小滚动追加 .1/.2 序号);过期文件按日戳清理。"""

    def __init__(self, base_path: str):
        self.base_path = base_path
        stamp = datetime.now().strftime("%Y%m%d")
        super().__init__(f"{base_path}.{stamp}", maxBytes=MAX_BYTES,
                         backupCount=KEEP_DAYS * 50, encoding="utf-8")
        self.day_stamp = stamp

    def emit(self, record: logging.LogRecord) -> None:
        today = datetime.now().strftime("%Y%m%d")
        if today != self.day_stamp:  # 跨天:换新文件并清理过期
            self.day_stamp = today
            self.baseFilename = os.path.abspath(f"{self.base_path}.{today}")
            self.stream = None
            if self.backupCount > 0:
                self._cleanup_expired()
        super().emit(record)

    def _cleanup_expired(self) -> None:
        cutoff = (datetime.now() - timedelta(days=KEEP_DAYS)).strftime("%Y%m%d")
        for f in glob.glob(f"{self.base_path}.*"):
            stamp = f.rsplit(".", 1)[-1]
            if stamp[:8] < cutoff:
                try:
                    os.remove(f)
                except OSError:
                    pass


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    global _handler
    logger = logging.getLogger("irs-calc")
    logger.setLevel(level)
    if _handler is None:  # 全局只挂一个滚动 handler,避免并发滚动冲突
        os.makedirs(LOG_DIR, exist_ok=True)
        _handler = DailySizeRotatingHandler(os.path.join(LOG_DIR, "irs-calc.log"))
        _handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s"))
        logger.addHandler(_handler)
        logger.propagate = False
    return logger
