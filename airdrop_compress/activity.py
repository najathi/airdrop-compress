"""Recent activity and daily statistics, shown on the dashboard."""

from __future__ import annotations

import itertools
import json
import os
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path

KEEP_ITEMS = 200
PERSIST_ITEMS = 100
KEEP_DAYS = 90


@dataclass
class Activity:
    id: int
    name: str
    kind: str                       # image | document | plugin
    status: str = "queued"          # queued | processing | done | skipped | failed
    message: str = ""
    before: int = 0                 # bytes in
    after: int = 0                  # bytes out (all outputs)
    outputs: list[str] = field(default_factory=list)
    processor: str = ""
    started: float = field(default_factory=time.time)
    finished: float | None = None


class ActivityLog:
    def __init__(self, path: Path | None):
        self.path = path
        self.lock = threading.Lock()
        self.items: deque[Activity] = deque(maxlen=KEEP_ITEMS)
        self.days: dict[str, dict] = {}
        self.revision = 0
        self._ids = itertools.count(1)
        self._load()

    # -- recording ---------------------------------------------------------- #

    def start(self, name: str, kind: str) -> Activity:
        with self.lock:
            item = Activity(id=next(self._ids), name=name, kind=kind)
            self.items.appendleft(item)
            self.revision += 1
            return item

    def update(self, item: Activity, **changes) -> None:
        with self.lock:
            for k, v in changes.items():
                setattr(item, k, v)
            if item.status in ("done", "skipped", "failed") and item.finished is None:
                item.finished = time.time()
                if item.status != "skipped":
                    day = self.days.setdefault(time.strftime("%Y-%m-%d"),
                                               {"files": 0, "failed": 0, "before": 0, "after": 0})
                    if item.status == "done":
                        day["files"] += 1
                        if item.kind == "image":  # savings only make sense for images
                            day["before"] += item.before
                            day["after"] += item.after
                    else:
                        day["failed"] += 1
            self.revision += 1
        if item.finished:
            self._save()

    def clear(self) -> None:
        with self.lock:
            self.items.clear()
            self.days.clear()
            self.revision += 1
        self._save()

    # -- reading ------------------------------------------------------------ #

    def snapshot(self, limit: int = 60) -> list[dict]:
        with self.lock:
            return [asdict(i) for i in itertools.islice(self.items, limit)]

    def stats(self) -> dict:
        with self.lock:
            today = self.days.get(time.strftime("%Y-%m-%d"), {"files": 0, "failed": 0, "before": 0, "after": 0})
            total = {"files": 0, "before": 0, "after": 0}
            for d in self.days.values():
                for k in total:
                    total[k] += d.get(k, 0)
            busy = sum(1 for i in self.items if i.status in ("queued", "processing"))
            return {"today": dict(today), "total": total, "busy": busy}

    # -- persistence -------------------------------------------------------- #

    def _load(self) -> None:
        if not self.path:
            return
        try:
            data = json.loads(self.path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return
        known = set(Activity.__dataclass_fields__)
        for raw in reversed(data.get("items", [])):
            raw = {k: v for k, v in raw.items() if k in known}
            raw["id"] = next(self._ids)
            if raw.get("status") in ("queued", "processing"):
                continue
            self.items.appendleft(Activity(**raw))
        self.days = data.get("days", {})

    def _save(self) -> None:
        if not self.path:
            return
        with self.lock:
            finished = [asdict(i) for i in self.items if i.finished][:PERSIST_ITEMS]
            days = dict(sorted(self.days.items())[-KEEP_DAYS:])
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(f".{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps({"items": finished, "days": days}))
        os.replace(tmp, self.path)
