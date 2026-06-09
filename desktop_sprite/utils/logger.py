from __future__ import annotations

import logging


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # 静默 httpx 的访问日志（每个 GET/POST 都打一条 INFO，太吵且无业务价值）。
    # 库官方推荐设到 WARNING；调试网络问题时可手动临时调回 INFO。
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
