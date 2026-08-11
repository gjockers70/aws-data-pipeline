from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ingestion.identifiers import validate_run_id


class LocalManifestStore:
    def __init__(self, manifest_root: Path) -> None:
        self._manifest_root = manifest_root

    def path_for(self, run_id: str) -> Path:
        validate_run_id(run_id)
        return self._manifest_root / "world_bank" / f"run_id={run_id}.json"

    def load(self, run_id: str) -> dict[str, Any] | None:
        path = self.path_for(run_id)
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise TypeError(f"Manifest must contain a JSON object: {path}")
        return payload

    def write(self, manifest: dict[str, Any]) -> Path:
        path = self.path_for(str(manifest["run_id"]))
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
        return path
