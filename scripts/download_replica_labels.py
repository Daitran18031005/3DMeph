#!/usr/bin/env python3
"""
download_replica_labels.py — lấy nhãn còn thiếu của Replica (preseg, semantic, glass.sur) từ kho chính thức mà KHÔNG lưu kho 33,9 GB.

Kho `replica_v1_0.tar.gz` được chia 17 phần trên GitHub release v1.0. Script tải tuần tự từng phần và đổ thẳng vào `tarfile` chế độ dòng (`r|gz`),
chỉ ghi các file nhãn vào `data/raw/replica/<scene>/`; phần còn lại (mesh, texture đã có) bị bỏ qua. Đĩa chỉ cần cỡ nhãn; băng thông ~34 GB.
Mất kết nối giữa chừng thì nối lại trong cùng phần bằng HTTP Range; gzip dạng dòng không nhảy được nên dừng hẳn phải chạy lại từ đầu.
Không ghi đè file đã có; chặn tên tuyệt đối/"..".

    python scripts/download_replica_labels.py --dry-run          # HEAD 17 phần, in tổng dung lượng
    python scripts/download_replica_labels.py --yes              # tải dạng dòng và lọc (cần người dùng duyệt)
"""

from __future__ import annotations

import argparse
import io
import sys
import tarfile
import time
import urllib.request
from pathlib import Path, PurePosixPath

REPO = Path(__file__).resolve().parents[1]
BASE = "https://github.com/facebookresearch/Replica-Dataset/releases/download/v1.0/replica_v1_0.tar.gz.part"
PARTS = [f"a{c}" for c in "abcdefghijklmnopq"]                     # aa … aq (17 phần)
WANTED = {"preseg.json", "preseg.bin", "semantic.json", "semantic.bin", "glass.sur"}
UA = {"User-Agent": "replica-label-fetch/1.0"}


def head(url: str) -> int:
    with urllib.request.urlopen(urllib.request.Request(url, method="HEAD", headers=UA), timeout=60) as r:
        return int(r.headers["Content-Length"])


class PartStream(io.RawIOBase):
    """Nối 17 phần thành một luồng đọc; nối lại bằng Range khi đứt kết nối (tối đa `retries` lần mỗi phần)."""

    def __init__(self, sizes, retries=8, log=print):
        self.sizes, self.retries, self.log = sizes, retries, log
        self.i, self.pos, self.resp, self.total = 0, 0, None, 0

    def readable(self):
        return True

    def _open(self):
        req = urllib.request.Request(BASE + PARTS[self.i], headers={**UA, "Range": f"bytes={self.pos}-"})
        self.resp = urllib.request.urlopen(req, timeout=120)

    def readinto(self, b):
        while self.i < len(PARTS):
            if self.pos >= self.sizes[self.i]:
                self.log(f"[tải] xong phần {PARTS[self.i]} ({self.total / 1e9:.1f} GB đã đọc)")
                self.i, self.pos, self.resp = self.i + 1, 0, None
                continue
            for attempt in range(self.retries):
                try:
                    if self.resp is None:
                        self._open()
                    n = self.resp.readinto(b)
                    if n == 0:
                        raise ConnectionError("hết dữ liệu sớm")
                    self.pos += n
                    self.total += n
                    return n
                except (OSError, ConnectionError) as e:
                    self.log(f"[tải] phần {PARTS[self.i]} lỗi ở {self.pos} B ({e}); nối lại lần {attempt + 1}")
                    self.resp = None
                    time.sleep(min(60, 5 * (attempt + 1)))
            raise ConnectionError(f"phần {PARTS[self.i]} lỗi quá {self.retries} lần")
        return 0


def target_for(name: str, out_root: Path, scenes=frozenset()):
    """`<...>/<scene>/<file>` → out_root/<scene>/<file> nếu là file nhãn cần lấy và tên an toàn; ngược lại None.
    Scene trong `scenes` (tải lại cả scene): giữ mọi file `replica_v1/<scene>/...` (mesh, textures, nhãn)."""
    p = PurePosixPath(name)                                               # tên trong tar là POSIX: Path của Windows coi "/x" là tương đối
    if p.is_absolute() or ".." in p.parts:
        return None
    hit = [i for i, part in enumerate(p.parts[:-1]) if part in scenes]   # tar không có thư mục gốc chung: tìm thành phần là tên scene
    if hit:
        return out_root.joinpath(*p.parts[hit[0]:])
    if p.name not in WANTED or len(p.parts) < 2:
        return None
    return out_root / p.parts[-2] / p.name


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(REPO / "data" / "raw" / "replica"))
    ap.add_argument("--scenes", nargs="*", default=[], help="tải lại toàn bộ các scene này (mesh, textures, nhãn)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--yes", action="store_true", help="bắt buộc để tải thật")
    a = ap.parse_args(argv)
    sizes = [head(BASE + p) for p in PARTS]
    scenes = frozenset(a.scenes)
    print(f"17 phần, tổng {sum(sizes):,} B ({sum(sizes) / 1e9:.2f} GB) băng thông; giữ nhãn {sorted(WANTED)}"
          + (f" và toàn bộ scene {sorted(scenes)}" if scenes else ""))
    if a.dry_run or not a.yes:
        print("chỉ dry-run" if a.dry_run else "cần --yes để tải thật")
        return 0
    out = Path(a.out)
    got = 0
    with tarfile.open(fileobj=io.BufferedReader(PartStream(sizes), 1 << 20), mode="r|gz") as tar:
        for m in tar:
            dst = target_for(m.name, out, scenes)
            if dst is None or not m.isfile():
                continue
            if dst.parts[len(out.parts)] in scenes:
                dst.parent.mkdir(parents=True, exist_ok=True)
            if not dst.parent.is_dir():
                print(f"[bỏ] {m.name}: không có scene {dst.parent.name} trên đĩa")
                continue
            if dst.exists():
                print(f"[giữ] {dst} đã có, không ghi đè")
                continue
            tmp = dst.with_suffix(dst.suffix + ".part")
            with tar.extractfile(m) as src, open(tmp, "wb") as f:
                while chunk := src.read(1 << 20):
                    f.write(chunk)
            tmp.replace(dst)
            got += 1
            print(f"[ghi] {dst} ({m.size:,} B)")
    print(f"xong: {got} file nhãn")
    return 0


if __name__ == "__main__":
    sys.exit(main())
