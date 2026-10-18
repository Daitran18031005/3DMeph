#!/usr/bin/env python3
"""
download_arkitscenes.py — Tải dữ liệu ARKitScenes theo từng đợt, KHÔNG giải nén, có resume và kiểm dung lượng.

Kế hoạch §4.0c (docs/PLAN_v4.md). Dùng quy ước URL và tên file của `Download/ARKitScenes/ARKitScenes/download_data.py`
nhưng KHÔNG gọi hàm của nó: `download_file` của script đó chạy `curl` không có `-C -` (không resume), không kiểm
Content-Length, và lệnh `download_data.py` còn tự `unzip` rồi xoá zip, đặt file ở `<dir>/raw/<split>/<id>/` (thêm cấp `raw/`).

Bốn đợt (đã được người dùng duyệt; held-out KHÔNG có đợt nào, Faro held-out chưa được phép tải):
  A  vga_wide.zip + vga_wide_intrinsics.zip của scene dev (mặc định 42444738), vào data/raw/arkitscenes/<split>/<id>/
  B  Faro (.ply + _pose.txt) của visit của scene dev, vào data/raw/arkitscenes/laser_scanner_point_clouds/<visit_id>/
  C  vga_wide + intrinsics của 6 scene val (splits.csv), vào data/raw/arkitscenes/Validation/<id>/
  D  Faro của 6 visit val, vào data/raw/arkitscenes/laser_scanner_point_clouds/<visit_id>/

Cách dùng (từ thư mục gốc repo, trong env 3d_metric):
    python scripts/download_arkitscenes.py --batch all --dry-run     # chỉ HEAD, in bảng dung lượng; không tải
    python scripts/download_arkitscenes.py --batch A --yes           # tải thật đợt A (bắt buộc --yes)

Quy tắc an toàn:
  - Không có --dry-run lẫn --yes thì từ chối. Tải tuần tự, từng file một. Không giải nén, không xoá zip, không ghi đè.
  - File đã có đúng dung lượng thì bỏ qua; có nhưng sai dung lượng thì báo lỗi (không xoá, không ghi đè).
  - File đang tải ghi vào <tên>.part; chỉ đổi tên khi dung lượng khớp Content-Length; bị ngắt thì chạy lại sẽ resume.
  - Thử lại tự động: curl có --retry-all-errors và bỏ kết nối đứng (--speed-limit/--speed-time); ngoài ra mỗi file được thử
    tối đa --max_attempts lần (mặc định 5), đợi --retry_wait giây (mặc định 10), mỗi lần resume từ .part.
  - Trước mỗi đợt: ổ trống − dung lượng còn phải tải phải ≥ --min_free_gib (mặc định 15 GiB), nếu không thì DỪNG.
  - splits.csv phải khớp splits.lock; scene/visit held-out bị chặn (HeldoutError).
  - Ghi log từng file vào --log (CSV, nối thêm).

Mã thoát: 0 ok; 1 lỗi tải/dữ liệu; 2 thiếu --yes, hoặc dry-run thấy ổ không đủ; 3 ổ trống không đủ khi tải thật.
"""

import argparse
import csv
import io
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import pipeline  # noqa: E402,F401  (import torch trước, xem pipeline/__init__.py)
from pipeline.common import splits as sp  # noqa: E402

BASE_URL = "https://docs-assets.developer.apple.com/ml-research/datasets/arkitscenes/v1"
MAPPING_URL = f"{BASE_URL}/raw/laser_scanner_point_clouds/laser_scanner_point_clouds_mapping.csv"
GiB = 1024 ** 3
BATCH_ORDER = ("A", "B", "C", "D")
BATCH_DESC = {
    "A": "vga_wide + intrinsics, scene dev",
    "B": "Faro, visit của scene dev",
    "C": "vga_wide + intrinsics, 6 Validation",
    "D": "Faro, 6 visit Validation",
}
# Số đã báo (GiB, 1024^3) ngày 17/10/2026, đo bằng HEAD; sai lệch trong 1% coi là "khớp".
REPORTED_GIB = {"A": 0.69, "B": 10.22, "C": 9.53, "D": 46.21}
REPORT_TOLERANCE = 0.01
DEFAULT_MIN_FREE_GIB = 15.0
DEFAULT_MAX_ATTEMPTS = 5     # số lần chạy curl cho mỗi file (mỗi lần resume từ .part)
DEFAULT_RETRY_WAIT = 10.0    # giây đợi giữa hai lần thử


class DownloadError(RuntimeError):
    """Lỗi mạng hoặc dữ liệu khi đo/tải."""


@dataclass(frozen=True)
class Item:
    batch: str
    url: str
    dst: Path
    kind: str  # zip | ply | pose


# ---------------------------------------------------------------- mạng (tests thay thế các hàm này)

def head_size(url: str) -> int:
    """Content-Length của url bằng HEAD (không tải dữ liệu)."""
    last = None
    for _ in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=60) as f:
                return int(f.headers["Content-Length"])
        except Exception as e:  # noqa: BLE001
            last = f"{type(e).__name__}: {str(e)[:100]}"
            time.sleep(1)
    raise DownloadError(f"HEAD lỗi cho {url}: {last}")


def fetch_mapping() -> Dict[str, List[str]]:
    """{visit_id: [laser_scanner_point_clouds_id, …]} từ file mapping của ARKitScenes (đọc vào RAM)."""
    try:
        text = urllib.request.urlopen(MAPPING_URL, timeout=60).read().decode()
    except Exception as e:  # noqa: BLE001
        raise DownloadError(f"không tải được mapping Faro: {type(e).__name__}: {str(e)[:100]}") from e
    out: Dict[str, List[str]] = defaultdict(list)
    for r in csv.DictReader(io.StringIO(text)):
        out[r["visit_id"]].append(r["laser_scanner_point_clouds_id"])
    return dict(out)


STALL_SPEED_BYTES = 10240   # dưới 10 KiB/s ...
STALL_SECONDS = 30          # ... liên tục 30 giây thì coi là kết nối chết (curl thoát mã 28) thay vì treo vô hạn


def build_curl_cmd(url: str, part: Path) -> List[str]:
    """curl có resume (-C -), theo redirect, báo lỗi HTTP (--fail).

    --retry-all-errors: thử lại cả lỗi như mã 56 ("server closed abruptly"), mặc định curl không thử lại.
    --speed-limit/--speed-time: bỏ kết nối không tiến triển (lỗi ngày 18/10: đứng ở 36% khoảng 2,5 phút rồi mới báo lỗi).
    """
    return ["curl", "--fail", "--location", "--silent", "--show-error", "-C", "-",
            "--retry", "3", "--retry-delay", "5", "--retry-all-errors",
            "--speed-limit", str(STALL_SPEED_BYTES), "--speed-time", str(STALL_SECONDS),
            "-o", str(part), url]


def run_curl(url: str, part: Path, expected: int) -> int:
    """Chạy curl, in tiến độ mỗi 30 giây theo dung lượng .part. Trả về mã thoát của curl."""
    if shutil.which("curl") is None:
        raise DownloadError("không thấy curl trong PATH (Windows 10+ có curl.exe)")
    proc = subprocess.Popen(build_curl_cmd(url, part), stderr=subprocess.PIPE, text=True)
    while True:
        try:
            proc.wait(timeout=30)
            break
        except subprocess.TimeoutExpired:
            got = part.stat().st_size if part.exists() else 0
            print(f"    … {got / GiB:.2f}/{expected / GiB:.2f} GiB ({100 * got / max(expected, 1):.0f}%)", flush=True)
    if proc.returncode != 0:
        tail = (proc.stderr.read() or "").strip().splitlines()[-1:] or [""]
        print(f"    curl mã {proc.returncode}: {tail[0]}", flush=True)
    return proc.returncode


def free_bytes(path: Path) -> int:
    p = Path(path)
    while not p.exists() and p != p.parent:
        p = p.parent
    return shutil.disk_usage(p).free


# ---------------------------------------------------------------- dựng danh sách file

def load_rows(splits_csv: Path) -> List[Dict[str, str]]:
    sp.verify_lock(splits_csv)  # LockError nếu splits.csv bị sửa sau khi khoá
    return sp.read_rows(splits_csv)


def assert_no_heldout_items(items: List[Item], rows: List[Dict[str, str]]) -> None:
    """Chặn tải scene/visit held-out (Faro held-out chưa được phép)."""
    held = [r for r in rows if r["split"] == sp.SPLIT_HELDOUT]
    held_ids = {r["video_id"] for r in held}
    held_visits = {r["visit_id"] for r in held}
    for it in items:
        names = {p.name for p in it.dst.parents}
        bad = (names & held_ids) | (names & held_visits)
        if bad:
            raise sp.HeldoutError(f"đợt {it.batch} chạm scene/visit held-out {sorted(bad)}: không được tải ({it.dst})")


def build_items(batch: str, rows: List[Dict[str, str]], mapping: Dict[str, List[str]], root: Path,
                dev_scene: str = "42444738") -> List[Item]:
    by_id = {r["video_id"]: r for r in rows}
    raw_root = Path(root) / "data" / "raw" / "arkitscenes"
    laser_root = raw_root / "laser_scanner_point_clouds"

    def zips(row):
        d = Path(root) / row["source_dir"]
        return [Item(batch, f"{BASE_URL}/raw/{d.parent.name}/{row['video_id']}/{a}.zip", d / f"{a}.zip", "zip")
                for a in ("vga_wide", "vga_wide_intrinsics")]

    def faro(visit):
        ids = mapping.get(visit)
        if not ids:
            raise DownloadError(f"visit {visit} không có trong mapping Faro")
        out = []
        for i in ids:
            base = f"{BASE_URL}/raw/laser_scanner_point_clouds/{visit}/{i}"
            out.append(Item(batch, f"{base}.ply", laser_root / visit / f"{i}.ply", "ply"))
            out.append(Item(batch, f"{base}_pose.txt", laser_root / visit / f"{i}_pose.txt", "pose"))
        return out

    dev = by_id.get(dev_scene)
    if dev is None or dev["split"] != sp.SPLIT_TRAIN:
        raise ValueError(f"scene dev {dev_scene} phải có trong splits.csv và thuộc train")
    val_rows = sorted((r for r in rows if r["split"] == sp.SPLIT_VAL), key=lambda r: int(r["video_id"]))
    if batch == "A":
        items = zips(dev)
    elif batch == "B":
        items = faro(dev["visit_id"])
    elif batch == "C":
        items = [it for r in val_rows for it in zips(r)]
    elif batch == "D":
        visits = sorted({r["visit_id"] for r in val_rows}, key=int)
        items = [it for v in visits for it in faro(v)]
    else:
        raise ValueError(f"đợt không hợp lệ: {batch!r} (chỉ A, B, C, D)")
    assert_no_heldout_items(items, rows)
    return items


def parse_batches(arg: str) -> List[str]:
    parts = [p.strip().upper() for p in arg.split(",") if p.strip()]
    if parts == ["ALL"]:
        return list(BATCH_ORDER)
    bad = [p for p in parts if p not in BATCH_ORDER]
    if bad or not parts:
        raise ValueError(f"--batch không hợp lệ: {arg!r} (dùng A, B, C, D, danh sách cách nhau bằng dấu phẩy, hoặc all)")
    return [b for b in BATCH_ORDER if b in parts]


# ---------------------------------------------------------------- đo dung lượng và trạng thái

def part_path(dst: Path) -> Path:
    return Path(str(dst) + ".part")


def remaining_bytes(item: Item, size: int) -> int:
    """Số byte còn phải tải. File đúng dung lượng: 0. File sai dung lượng hoặc .part lớn hơn dự kiến: báo lỗi."""
    if item.dst.exists():
        have = item.dst.stat().st_size
        if have == size:
            return 0
        raise DownloadError(f"{item.dst} đã tồn tại nhưng sai dung lượng ({have} khác {size}); không ghi đè, hãy kiểm tra tay")
    part = part_path(item.dst)
    if part.exists():
        have = part.stat().st_size
        if have > size:
            raise DownloadError(f"{part} lớn hơn dự kiến ({have} > {size}); hãy kiểm tra tay")
        return size - have
    return size


def measure(items: List[Item], head: Optional[Callable[[str], int]] = None, workers: int = 8) -> List[int]:
    head = head or head_size
    with ThreadPoolExecutor(workers) as ex:  # chỉ HEAD (nhỏ) chạy song song; tải file luôn tuần tự
        return list(ex.map(lambda it: head(it.url), items))


def matches_reported(batch: str, total_bytes: int) -> bool:
    return abs(total_bytes / GiB - REPORTED_GIB[batch]) <= REPORTED_GIB[batch] * REPORT_TOLERANCE


def plan_batch(batch, rows, mapping, root, dev_scene):
    items = build_items(batch, rows, mapping, root, dev_scene)
    sizes = measure(items)
    todo = sum(remaining_bytes(it, s) for it, s in zip(items, sizes))
    return items, sizes, todo


# ---------------------------------------------------------------- tải

def append_log(log_path: Path, row: Dict[str, object]) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    new = not log_path.exists()
    with open(log_path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["time", "batch", "url", "dst", "expected_bytes", "status", "actual_bytes",
                                          "seconds", "note"], lineterminator="\n")
        if new:
            w.writeheader()
        w.writerow(row)


def download_item(item: Item, size: int, log_path: Path, max_attempts: int = DEFAULT_MAX_ATTEMPTS,
                  retry_wait: float = DEFAULT_RETRY_WAIT) -> bool:
    """Tải một file (resume nếu có .part), kiểm dung lượng rồi mới đổi tên. Trả về True nếu thành công.

    Mỗi lần thử chạy lại curl `-C -` nên luôn nối tiếp từ .part hiện có. Thử lại khi curl lỗi hoặc thoát mã 0 nhưng
    còn thiếu byte; .part lớn hơn dự kiến là lỗi dữ liệu, không thử lại.
    """
    t0 = time.time()
    dst = item.dst
    part = part_path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)

    def log(status, actual, note=""):
        append_log(log_path, {"time": datetime.now().isoformat(timespec="seconds"), "batch": item.batch, "url": item.url,
                              "dst": str(dst), "expected_bytes": size, "status": status, "actual_bytes": actual,
                              "seconds": round(time.time() - t0, 1), "note": note})

    if dst.exists():
        have = dst.stat().st_size
        if have == size:
            log("skipped_exists", have)
            print(f"  [BỎ QUA] {dst.name} đã có đúng {size} byte")
            return True
        log("failed", have, "đã tồn tại nhưng sai dung lượng")
        print(f"  [LỖI] {dst} tồn tại nhưng sai dung lượng ({have} khác {size}); không ghi đè")
        return False

    resumed = part.exists() and part.stat().st_size > 0
    print(f"  [{'RESUME' if resumed else 'TẢI'}] {dst.name} ({size / GiB:.3f} GiB)", flush=True)
    attempts = 0
    while not (part.exists() and part.stat().st_size == size):  # .part đã đủ thì chỉ cần kiểm và đổi tên
        attempts += 1
        try:
            rc = run_curl(item.url, part, size)
        except DownloadError as e:
            log("failed", part.stat().st_size if part.exists() else 0, str(e))
            print(f"  [LỖI] {e}")
            return False
        have = part.stat().st_size if part.exists() else 0
        if have > size:
            log("failed", have, f"{part.name} lớn hơn dự kiến ({have} > {size})")
            print(f"  [LỖI] {part.name} lớn hơn dự kiến ({have} > {size}); không đổi tên, hãy kiểm tra tay")
            return False
        if rc == 0 and have == size:
            break
        why = f"curl mã {rc}" if rc != 0 else f"dung lượng {have} khác Content-Length {size}"
        if attempts >= max_attempts:
            log("failed", have, f"{why}; đã thử {attempts} lần")
            print(f"  [LỖI] {why}; đã thử {attempts} lần; giữ {part.name} ({have}/{size} byte) để resume, không đổi tên")
            return False
        print(f"  [THỬ LẠI {attempts}/{max_attempts - 1}] {why}; có {have / GiB:.3f}/{size / GiB:.3f} GiB, "
              f"đợi {retry_wait:g}s rồi resume", flush=True)
        resumed = resumed or have > 0
        time.sleep(retry_wait)
    actual = part.stat().st_size
    os.replace(part, dst)
    log("resumed" if resumed else "downloaded", actual, f"đã thử {attempts} lần" if attempts > 1 else "")
    print(f"  [XONG] {dst.name} khớp Content-Length")
    return True


# ---------------------------------------------------------------- chương trình chính

def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Tải ARKitScenes theo đợt A/B/C/D (không giải nén, có resume)")
    ap.add_argument("--batch", required=True, help="A, B, C, D, danh sách cách nhau bằng phẩy, hoặc all")
    ap.add_argument("--dry-run", action="store_true", help="chỉ HEAD và in bảng dung lượng, không tải")
    ap.add_argument("--yes", action="store_true", help="bắt buộc để tải thật")
    ap.add_argument("--root", default=str(REPO), help="thư mục gốc repo (mặc định: repo này)")
    ap.add_argument("--splits", default=None, help="mặc định <root>/data/splits.csv")
    ap.add_argument("--dev_scene", default="42444738")
    ap.add_argument("--min_free_gib", type=float, default=DEFAULT_MIN_FREE_GIB, help="ổ phải còn dư ít nhất mức này sau mỗi đợt")
    ap.add_argument("--log", default=None, help="CSV log, mặc định <root>/data/raw/arkitscenes/download_log.csv")
    ap.add_argument("--max_attempts", type=int, default=DEFAULT_MAX_ATTEMPTS, help="số lần thử mỗi file (resume giữa các lần)")
    ap.add_argument("--retry_wait", type=float, default=DEFAULT_RETRY_WAIT, help="giây đợi giữa hai lần thử")
    args = ap.parse_args(argv)

    if not args.dry_run and not args.yes:
        print("[TỪ CHỐI] Cần --dry-run (chỉ đo) hoặc --yes (tải thật). Chưa làm gì.")
        return 2
    try:
        batches = parse_batches(args.batch)
    except ValueError as e:
        print(f"[LỖI] {e}")
        return 1

    root = Path(args.root)
    splits_csv = Path(args.splits) if args.splits else root / "data" / "splits.csv"
    log_path = Path(args.log) if args.log else root / "data" / "raw" / "arkitscenes" / "download_log.csv"
    raw_root = root / "data" / "raw" / "arkitscenes"
    min_free = args.min_free_gib * GiB
    dry = args.dry_run

    try:
        rows = load_rows(splits_csv)
        mapping = fetch_mapping() if any(b in ("B", "D") for b in batches) else {}
    except (sp.LockError, DownloadError, FileNotFoundError) as e:
        print(f"[LỖI] {e}")
        return 1

    free0 = free_bytes(raw_root)
    print(f"Ổ đĩa: trống {free0 / GiB:.2f} GiB (1 GiB = 1024^3 byte), ngưỡng dư tối thiểu {args.min_free_gib:.1f} GiB")
    print(("DRY-RUN: chỉ đo HEAD, không tải gì." if dry else "TẢI THẬT (--yes), tuần tự từng file, không giải nén."))
    summary, free_left, blocked = [], free0, False

    for b in batches:
        try:
            items, sizes, todo = plan_batch(b, rows, mapping, root, args.dev_scene)
        except (DownloadError, ValueError, sp.HeldoutError) as e:
            print(f"[LỖI] đợt {b}: {e}")
            return 1
        total = sum(sizes)
        left_after = (free_bytes(raw_root) if not dry else free_left) - todo
        ok_space = left_after >= min_free
        summary.append((b, len(items), total, todo, matches_reported(b, total), left_after, ok_space))
        if dry:
            free_left = left_after
            blocked = blocked or not ok_space
            continue
        if not ok_space:
            print(f"[DỪNG] đợt {b}: ổ còn dư {left_after / GiB:.2f} GiB sau khi tải, dưới ngưỡng {args.min_free_gib:.1f} GiB. Không tải.")
            return 3
        print(f"\n== Đợt {b}: {BATCH_DESC[b]}: {len(items)} file, còn phải tải {todo / GiB:.2f} GiB")
        for it, size in zip(items, sizes):
            if not download_item(it, size, log_path, args.max_attempts, args.retry_wait):
                print(f"[DỪNG] đợt {b} lỗi ở {it.dst.name}. Chạy lại lệnh này để resume.")
                return 1

    print("\nĐợt | mô tả                              | số file | GiB (HEAD) | còn phải tải | khớp số đã báo | ổ còn dư sau (GiB)")
    for b, n, total, todo, match, left_after, ok_space in summary:
        rep = f"{REPORTED_GIB[b]:.2f}"
        print(f"{b:^3} | {BATCH_DESC[b]:<34} | {n:>7} | {total / GiB:>10.2f} | {todo / GiB:>12.2f} | "
              f"{'khớp' if match else 'LỆCH'} (đã báo {rep}) | {left_after / GiB:>8.2f}{'' if ok_space else '  < ngưỡng'}")
    tot_all = sum(s[3] for s in summary)
    print(f"Tổng còn phải tải: {tot_all / GiB:.2f} GiB; ổ trống hiện tại {free0 / GiB:.2f} GiB; "
          f"dư sau các đợt đã chọn: {(free0 - tot_all) / GiB:.2f} GiB")
    if dry:
        if blocked:
            print(f"[DỪNG] Ổ không đủ: dư dưới {args.min_free_gib:.1f} GiB sau các đợt đã chọn. KHÔNG tải. "
                  f"Cần trống tối thiểu {(tot_all + min_free) / GiB:.2f} GiB cho các đợt đã chọn.")
            return 2
        print("[OK] Dry-run xong, ổ đủ chỗ. Chưa tải gì.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
