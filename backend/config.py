from dataclasses import dataclass
from pathlib import Path
import os


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Load a small .env file without making python-dotenv mandatory."""
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        os.environ.setdefault(key, value)


@dataclass(frozen=True)
class Settings:
    tushare_token: str
    data_dir: Path
    request_interval_seconds: float
    retry_times: int
    index_pool_file: Path = PROJECT_ROOT / "data" / "data_result_fixed.xlsx"
    index_weekly_start_date: str = "20260501"
    index_weekly_lookback_days: int = 28
    minimax_api_key: str = ""
    minimax_region: str = "cn"
    minimax_search_timeout_seconds: int = 45
    minimax_chat_timeout_seconds: int = 60

    @classmethod
    def from_env(cls) -> "Settings":
        _load_dotenv(PROJECT_ROOT / ".env")
        data_dir = Path(
            os.getenv("ETF_DATA_DIR", str(PROJECT_ROOT / "data"))
        ).expanduser()
        if not data_dir.is_absolute():
            data_dir = PROJECT_ROOT / data_dir
        index_pool_file = Path(
            os.getenv(
                "INDEX_POOL_FILE",
                str(PROJECT_ROOT / "data" / "data_result_fixed.xlsx"),
            )
        ).expanduser()
        if not index_pool_file.is_absolute():
            index_pool_file = PROJECT_ROOT / index_pool_file
        return cls(
            tushare_token=os.getenv("TUSHARE_TOKEN", "").strip(),
            data_dir=data_dir,
            request_interval_seconds=float(
                os.getenv("TUSHARE_REQUEST_INTERVAL_SECONDS", "0.4")
            ),
            retry_times=int(os.getenv("TUSHARE_RETRY_TIMES", "3")),
            index_pool_file=index_pool_file,
            index_weekly_start_date=os.getenv(
                "INDEX_WEEKLY_START_DATE", "20260501"
            ).strip(),
            index_weekly_lookback_days=int(
                os.getenv("INDEX_WEEKLY_LOOKBACK_DAYS", "28")
            ),
            minimax_api_key=os.getenv("MINIMAX_API_KEY", "").strip(),
            minimax_region=os.getenv("MINIMAX_REGION", "cn").strip() or "cn",
            minimax_search_timeout_seconds=int(
                os.getenv("MINIMAX_SEARCH_TIMEOUT_SECONDS", "45")
            ),
            minimax_chat_timeout_seconds=int(
                os.getenv("MINIMAX_CHAT_TIMEOUT_SECONDS", "60")
            ),
        )

    def require_tushare_token(self) -> str:
        if not self.tushare_token or self.tushare_token == "your_tushare_token_here":
            raise RuntimeError(
                "尚未配置 Tushare Token。请复制 .env.example 为 .env，"
                "并填写 TUSHARE_TOKEN。"
            )
        return self.tushare_token

    def require_minimax_api_key(self) -> str:
        if not self.minimax_api_key:
            raise RuntimeError("尚未配置 MINIMAX_API_KEY")
        return self.minimax_api_key
