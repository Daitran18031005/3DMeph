"""Chia scene ARKitScenes theo venue (visit_id) và chặn dùng scene held-out để chỉnh tham số.

Quy tắc (ĐC §10, §12; kế hoạch §4.0b):
  - val     = 6 scene thư mục `Validation` (khoá V_ref, G_ref, τ_e, τ_σ và các ngưỡng).
  - heldout = 5 scene lấy từ `Training` theo venue, chọn bằng seed cố định, **khoá** (splits.lock).
  - train   = phần còn lại.
  - Venue có 2 scene (ví dụ 472473, 466899) phải nằm trọn trong một tập.
  - Venue của scene dev không bao giờ vào held-out (scene dev luôn ở train).
Held-out chạy đúng một lần: mọi hàm tính tham số từ dữ liệu phải gọi `guard_reference`, nó `raise HeldoutError`
khi thấy scene held-out.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import random
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence

SPLIT_TRAIN, SPLIT_VAL, SPLIT_HELDOUT = "train", "val", "heldout"
SPLITS = (SPLIT_TRAIN, SPLIT_VAL, SPLIT_HELDOUT)
SPLIT_COLUMNS = ["video_id", "visit_id", "split", "sky_direction", "source_dir", "seed"]
DEFAULT_SEED = 42
DEFAULT_N_HELDOUT = 5


class HeldoutError(ValueError):
    """Dùng scene held-out để tính tham số/ngưỡng (bị cấm: held-out chỉ chạy một lần)."""


class LockError(ValueError):
    """splits.csv không khớp splits.lock (bị sửa sau khi khoá)."""


def lock_path_for(splits_csv: os.PathLike) -> Path:
    return Path(splits_csv).with_suffix(".lock")


def select_splits(scenes: Sequence[Mapping[str, str]], seed: int = DEFAULT_SEED,
                  n_heldout: int = DEFAULT_N_HELDOUT, dev_scene: Optional[str] = None) -> Dict[str, str]:
    """Trả về {video_id: split}.

    scenes: mỗi phần tử có `video_id`, `visit_id`, `fold` ('Training' hoặc 'Validation').
    Held-out: gom ứng viên (venue Training, bỏ venue của scene dev) theo venue, sắp theo số, hoán vị bằng
    `random.Random(seed)`, rồi lấy lần lượt venue nếu số scene còn thiếu đủ chứa (venue 2 scene vào cùng nhau).
    """
    by_venue: Dict[str, List[str]] = defaultdict(list)
    fold_of: Dict[str, str] = {}
    visit_of: Dict[str, str] = {}
    for s in scenes:
        vid, visit, fold = str(s["video_id"]), str(s["visit_id"]), str(s["fold"])
        if fold not in ("Training", "Validation"):
            raise ValueError(f"fold không hợp lệ cho {vid}: {fold!r}")
        fold_of[vid], visit_of[vid] = fold, visit
        by_venue[visit].append(vid)
    for visit, vids in by_venue.items():  # venue không được trải trên hai fold
        if len({fold_of[v] for v in vids}) > 1:
            raise ValueError(f"venue {visit} có scene ở cả Training và Validation: {vids}")

    dev_visit = None
    if dev_scene is not None:
        if dev_scene not in visit_of:
            raise ValueError(f"scene dev {dev_scene} không có trong danh sách scene")
        if fold_of[dev_scene] != "Training":
            raise ValueError("scene dev phải thuộc Training")
        dev_visit = visit_of[dev_scene]

    candidates = sorted({visit_of[v] for v, f in fold_of.items() if f == "Training"} - {dev_visit}, key=int)
    random.Random(seed).shuffle(candidates)
    remaining, chosen = n_heldout, []
    for visit in candidates:
        if remaining == 0:
            break
        size = len(by_venue[visit])
        if size <= remaining:
            chosen.append(visit)
            remaining -= size
    if remaining:
        raise ValueError(f"không chọn đủ {n_heldout} scene held-out (còn thiếu {remaining})")

    heldout_venues = set(chosen)
    out: Dict[str, str] = {}
    for vid, fold in fold_of.items():
        if fold == "Validation":
            out[vid] = SPLIT_VAL
        elif visit_of[vid] in heldout_venues:
            out[vid] = SPLIT_HELDOUT
        else:
            out[vid] = SPLIT_TRAIN
    check_split_integrity(out, visit_of, dev_scene)
    return out


def check_split_integrity(split_of: Mapping[str, str], visit_of: Mapping[str, str],
                          dev_scene: Optional[str] = None) -> None:
    """Không venue nào ở hai tập; scene dev ∈ train."""
    venue_splits: Dict[str, set] = defaultdict(set)
    for vid, sp in split_of.items():
        if sp not in SPLITS:
            raise ValueError(f"split không hợp lệ cho {vid}: {sp!r}")
        venue_splits[visit_of[vid]].add(sp)
    bad = {v: sorted(s) for v, s in venue_splits.items() if len(s) > 1}
    if bad:
        raise ValueError(f"venue nằm ở nhiều tập (rò rỉ): {bad}")
    if dev_scene is not None and split_of.get(dev_scene) != SPLIT_TRAIN:
        raise ValueError(f"scene dev {dev_scene} phải thuộc train, nhận {split_of.get(dev_scene)!r}")


def _canonical_bytes(path: os.PathLike) -> bytes:
    """Nội dung file với xuống dòng chuẩn hoá về LF (git autocrlf trên Windows không làm đổi hash)."""
    return Path(path).read_bytes().replace(b"\r\n", b"\n")


def file_sha256(path: os.PathLike) -> str:
    return hashlib.sha256(_canonical_bytes(path)).hexdigest()


def write_splits(rows: Sequence[Mapping[str, str]], path: os.PathLike) -> None:
    """Ghi splits.csv (LF), sắp theo (split, video_id) để đầu ra xác định."""
    order = {s: i for i, s in enumerate((SPLIT_TRAIN, SPLIT_VAL, SPLIT_HELDOUT))}
    rows = sorted(rows, key=lambda r: (order[r["split"]], int(r["video_id"])))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=SPLIT_COLUMNS, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in SPLIT_COLUMNS})


def write_lock(splits_csv: os.PathLike, seed: int) -> Path:
    """splits.lock: sha256 của splits.csv + seed + số scene mỗi tập. Không có mốc thời gian để giữ tính xác định."""
    rows = read_rows(splits_csv)
    counts = {s: sum(1 for r in rows if r["split"] == s) for s in SPLITS}
    lock = lock_path_for(splits_csv)
    lock.write_text(json.dumps({"sha256": file_sha256(splits_csv), "seed": seed, "n_rows": len(rows),
                                "counts": counts, "file": Path(splits_csv).name}, indent=2) + "\n", encoding="utf-8")
    return lock


def verify_lock(splits_csv: os.PathLike) -> None:
    lock = lock_path_for(splits_csv)
    if not lock.is_file():
        raise LockError(f"chưa có {lock.name}: chia tập chưa được khoá")
    expected = json.loads(lock.read_text(encoding="utf-8"))["sha256"]
    if file_sha256(splits_csv) != expected:
        raise LockError(f"{Path(splits_csv).name} không khớp {lock.name}: bị sửa sau khi khoá")


def read_rows(path: os.PathLike) -> List[Dict[str, str]]:
    with open(path, "r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_splits(path: os.PathLike, verify: bool = True) -> Dict[str, str]:
    """Đọc {video_id: split}. Mặc định kiểm splits.lock; sửa tay file sau khi khoá sẽ bị từ chối."""
    if verify:
        verify_lock(path)
    return {r["video_id"]: r["split"] for r in read_rows(path)}


def heldout_ids(splits: Mapping[str, str]) -> List[str]:
    return sorted(v for v, s in splits.items() if s == SPLIT_HELDOUT)


def guard_reference(video_ids: Iterable[str], splits: Mapping[str, str], allowed: Sequence[str] = (SPLIT_VAL,)) -> None:
    """Chặn tính tham số từ dữ liệu không được phép.

    Scene held-out → HeldoutError. Scene không thuộc `allowed` (mặc định chỉ val) hoặc không có trong splits →
    ValueError. V_ref, G_ref và mọi ngưỡng chỉ được đo trên 6 scene Validation.
    """
    ids = [str(v) for v in video_ids]
    if not ids:
        raise ValueError("không có scene nào để tính tham số")
    for v in ids:
        sp = splits.get(v)
        if sp == SPLIT_HELDOUT:
            raise HeldoutError(f"scene {v} là held-out: không được dùng để tính tham số/ngưỡng (chạy đúng một lần)")
    for v in ids:
        sp = splits.get(v)
        if sp is None:
            raise ValueError(f"scene {v} không có trong splits.csv")
        if sp not in allowed:
            raise ValueError(f"scene {v} thuộc tập {sp!r}; chỉ được dùng tập {list(allowed)}")
