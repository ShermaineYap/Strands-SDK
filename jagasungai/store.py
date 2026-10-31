"""Small JSON key-value store: local files for development, S3 in production.

Keys used:
  memory/<community>.json        last bands, last send (what the next brief compares to)
  pending/<community>.json       draft awaiting coordinator approval
  dispatch/<community>.json      send log used by the rate-limit guard
  snapshots/<state>/<ts>.json    every polled snapshot (replay + audit)
  audit/<community>.jsonl        one line per graph decision
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol


class Store(Protocol):
    def get(self, key: str) -> Any | None: ...
    def put(self, key: str, value: Any) -> None: ...
    def delete(self, key: str) -> None: ...
    def append_line(self, key: str, value: Any) -> None: ...


def _dumps(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, default=lambda o: o.isoformat() if isinstance(o, datetime) else str(o))


class FileStore:
    def __init__(self, root: str | Path = ".jagasungai") -> None:
        self.root = Path(root)

    def _p(self, key: str) -> Path:
        p = self.root / key
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def get(self, key: str) -> Any | None:
        p = self.root / key
        return json.loads(p.read_text()) if p.exists() else None

    def put(self, key: str, value: Any) -> None:
        self._p(key).write_text(_dumps(value))

    def delete(self, key: str) -> None:
        p = self.root / key
        if p.exists():
            p.unlink()

    def append_line(self, key: str, value: Any) -> None:
        with self._p(key).open("a") as f:
            f.write(_dumps(value) + "\n")


class S3Store:  # pragma: no cover - needs AWS
    def __init__(self, bucket: str, prefix: str = "jagasungai/", region: str | None = None) -> None:
        import boto3

        self.s3 = boto3.client("s3", region_name=region)
        self.bucket, self.prefix = bucket, prefix

    def get(self, key: str) -> Any | None:
        try:
            obj = self.s3.get_object(Bucket=self.bucket, Key=self.prefix + key)
        except self.s3.exceptions.NoSuchKey:
            return None
        return json.loads(obj["Body"].read())

    def put(self, key: str, value: Any) -> None:
        self.s3.put_object(Bucket=self.bucket, Key=self.prefix + key, Body=_dumps(value).encode(),
                           ContentType="application/json")

    def delete(self, key: str) -> None:
        self.s3.delete_object(Bucket=self.bucket, Key=self.prefix + key)

    def append_line(self, key: str, value: Any) -> None:
        # S3 has no append; audit lines are written as one object per event.
        stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S%f")
        self.put(f"{key.removesuffix('.jsonl')}/{stamp}.json", value)


def store_from_env() -> Store:
    bucket = os.environ.get("JAGASUNGAI_BUCKET")
    if bucket:
        return S3Store(bucket, region=os.environ.get("AWS_REGION"))
    return FileStore(os.environ.get("JAGASUNGAI_STATE_DIR", ".jagasungai"))
