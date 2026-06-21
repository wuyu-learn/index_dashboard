"""独立验证 MiniMax CLI 网络搜索能力。

用法：
    python3 scripts/minimax_search_smoke.py "半导体行业最新政策"

前置条件：
    1. 已安装 mmx-cli
    2. 已执行 mmx auth login
"""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Dict, List


class MiniMaxSearchError(RuntimeError):
    """MiniMax 搜索调用失败。"""


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str


ROOT = Path(__file__).resolve().parent.parent


def load_project_env() -> None:
    path = ROOT / ".env"
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def _first_text(item: Dict[str, Any], keys: tuple) -> str:
    for key in keys:
        value = item.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _result_items(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []

    for key in (
        "organic",
        "results",
        "data",
        "items",
        "web_pages",
        "webPages",
    ):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = _result_items(value)
            if nested:
                return nested
    return []


def normalize_results(payload: Any) -> List[SearchResult]:
    results = []
    for item in _result_items(payload):
        title = _first_text(item, ("title", "name"))
        url = _first_text(item, ("url", "link", "href"))
        snippet = _first_text(
            item,
            ("snippet", "summary", "description", "content", "text"),
        )
        if title or url or snippet:
            results.append(SearchResult(title=title, url=url, snippet=snippet))
    return results


def search(query: str, timeout_seconds: int = 45) -> Dict[str, Any]:
    load_project_env()
    executable = shutil.which("mmx")
    if not executable:
        raise MiniMaxSearchError(
            "未找到 mmx。请先执行：npm install -g mmx-cli"
        )
    api_key = os.getenv("MINIMAX_API_KEY", "").strip()
    region = os.getenv("MINIMAX_REGION", "cn").strip() or "cn"
    if not api_key:
        raise MiniMaxSearchError("未配置 MINIMAX_API_KEY")

    command = [
        executable,
        "search",
        "query",
        "--q",
        query,
        "--output",
        "json",
        "--api-key",
        api_key,
        "--region",
        region,
        "--non-interactive",
        "--no-color",
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise MiniMaxSearchError(
            f"搜索超过 {timeout_seconds} 秒未完成"
        ) from exc

    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        detail = detail.replace(api_key, "<已隐藏>")
        raise MiniMaxSearchError(
            f"mmx search 调用失败（退出码 {completed.returncode}）：{detail}"
        )

    raw_output = completed.stdout.strip()
    try:
        payload = json.loads(raw_output)
    except json.JSONDecodeError as exc:
        raise MiniMaxSearchError(
            f"mmx 未返回合法 JSON：{raw_output[:300]}"
        ) from exc

    normalized = normalize_results(payload)
    return {
        "query": query,
        "resultCount": len(normalized),
        "raw": payload,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="验证 MiniMax 网络搜索")
    parser.add_argument("query", help="搜索关键词")
    parser.add_argument("--timeout", type=int, default=45, help="超时秒数")
    parser.add_argument("--out", type=Path, help="将完整结果保存为 JSON 文件")
    args = parser.parse_args()

    try:
        result = search(args.query, args.timeout)
    except MiniMaxSearchError as exc:
        print(f"验证失败：{exc}", file=sys.stderr)
        return 1

    output = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output, encoding="utf-8")
        print(f"saved: {args.out}")
    else:
        print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
