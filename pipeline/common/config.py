"""Nạp configs/default.yaml. Các khoá được mô tả ở README từng module và đối chiếu bởi
scripts/check_docs.py."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = REPO_ROOT / "configs" / "default.yaml"
DEFAULT_COLMAP_EXE = REPO_ROOT.parent / "colmap" / "bin" / "colmap.exe"

_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _expand_env(value: Any) -> Any:
    """Thay ${TÊN} bằng biến môi trường; nếu biến không có thì giá trị là None (không đoán)."""
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    if isinstance(value, str):
        m = _ENV_PATTERN.fullmatch(value.strip())
        if m:
            return os.environ.get(m.group(1)) or None
        return _ENV_PATTERN.sub(lambda mm: os.environ.get(mm.group(1), ""), value)
    return value


def load_config(path: Optional[os.PathLike] = None) -> Dict[str, Any]:
    p = Path(path) if path else DEFAULT_CONFIG
    with open(p, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return _expand_env(raw)


def flatten_keys(cfg: Dict[str, Any], prefix: str = "") -> List[str]:
    """Danh sách khoá lá dạng 'fusion.tau_e' (mục trung gian không tính)."""
    keys: List[str] = []
    for k, v in cfg.items():
        name = f"{prefix}.{k}" if prefix else str(k)
        if isinstance(v, dict) and v:
            keys.extend(flatten_keys(v, name))
        else:
            keys.append(name)
    return keys


def get(cfg: Dict[str, Any], dotted: str) -> Any:
    cur: Any = cfg
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            raise KeyError(f"không có khoá cấu hình {dotted!r}")
        cur = cur[part]
    return cur


def require(cfg: Dict[str, Any], dotted: str) -> Any:
    """Như get nhưng báo lỗi rõ khi giá trị là null (tham số chưa đo/khoá)."""
    v = get(cfg, dotted)
    if v is None:
        raise ValueError(f"tham số {dotted} chưa có giá trị (null); cần đo/khoá trên Validation, xem configs/README.md")
    return v


def resolve_colmap_exe(cfg: Optional[Dict[str, Any]] = None) -> Path:
    """paths.colmap_exe > biến COLMAP_EXE > ../colmap/bin/colmap.exe so với repo."""
    if cfg:
        try:
            v = get(cfg, "paths.colmap_exe")
            if v:
                return Path(v)
        except KeyError:
            pass
    env = os.environ.get("COLMAP_EXE")
    return Path(env) if env else DEFAULT_COLMAP_EXE


def config_hash(cfg: Dict[str, Any]) -> str:
    """sha256 của cấu hình (ghi vào run_meta.json để tái lập)."""
    blob = json.dumps(cfg, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()
