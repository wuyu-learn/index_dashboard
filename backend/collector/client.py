import time
from typing import Any, Callable

from backend.config import Settings


class TushareClient:
    """Thin wrapper providing lazy initialization, throttling, and retries."""

    def __init__(
        self,
        settings: Settings,
        pro_api: Any = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.settings = settings
        self._pro_api = pro_api
        self._sleep = sleep
        self._last_request_at: float = 0.0

    @property
    def pro(self) -> Any:
        if self._pro_api is None:
            try:
                import tushare as ts
            except ImportError as exc:
                raise RuntimeError(
                    "缺少 tushare 依赖，请先执行：pip install -r requirements.txt"
                ) from exc
            self._pro_api = ts.pro_api(self.settings.require_tushare_token())
        return self._pro_api

    def call(self, endpoint: str, **params: Any) -> Any:
        method = getattr(self.pro, endpoint)
        last_error: Exception = RuntimeError("unknown Tushare error")

        for attempt in range(1, self.settings.retry_times + 1):
            elapsed = time.monotonic() - self._last_request_at
            wait_seconds = self.settings.request_interval_seconds - elapsed
            if self._last_request_at and wait_seconds > 0:
                self._sleep(wait_seconds)

            try:
                result = method(**params)
                self._last_request_at = time.monotonic()
                return result
            except Exception as exc:  # Tushare exposes several transport errors.
                last_error = exc
                self._last_request_at = time.monotonic()
                if attempt < self.settings.retry_times:
                    self._sleep(min(2 ** (attempt - 1), 8))

        raise RuntimeError(
            f"Tushare 接口 {endpoint} 连续调用失败 "
            f"({self.settings.retry_times} 次)：{last_error}"
        ) from last_error
