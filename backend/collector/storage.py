from datetime import datetime
import json
import os
from pathlib import Path
from typing import Any, Dict

import pandas as pd


def write_csv_atomic(data: pd.DataFrame, destination: Path) -> Path:
    """Write a CSV through a temporary file, then atomically replace it."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    try:
        data.to_csv(temporary, index=False, encoding="utf-8")
        os.replace(str(temporary), str(destination))
    finally:
        if temporary.exists():
            temporary.unlink()
    return destination


class SyncStateStore:
    def __init__(self, data_dir: Path) -> None:
        self.path = data_dir / "metadata" / "sync_state.json"

    def record(
        self,
        dataset: str,
        status: str,
        row_count: int,
        file_path: Path = None,
        trade_date: str = None,
        scope: str = None,
        error: str = None,
    ) -> None:
        state = self._read()
        suffix = trade_date or scope
        key = f"{dataset}:{suffix}" if suffix else dataset
        record: Dict[str, Any] = {
            "dataset": dataset,
            "status": status,
            "row_count": row_count,
            "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        if trade_date:
            record["trade_date"] = trade_date
        if scope:
            record["scope"] = scope
        if file_path:
            record["file"] = str(file_path)
        if error:
            record["error"] = error
        state[key] = record
        self._write(state)

    def _read(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _write(self, state: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(state, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(str(temporary), str(self.path))
