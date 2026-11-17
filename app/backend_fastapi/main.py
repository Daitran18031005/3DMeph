"""Backend FastAPI cho app quay 3D (M6, ĐC §19 Hình 23–24): nhận gói quay, chạy pipeline trên GPU từng job một, trả GLB.

    uvicorn app.backend_fastapi.main:app --host 0.0.0.0 --port 8000      # từ thư mục gốc repo, env 3d_metric

POST /jobs (multipart `capture`: zip gồm capture.json + frames/*.jpg) → {job_id}
GET  /jobs/{id}              → {status, stage, progress, error_code, message}
GET  /jobs/{id}/result       → model.glb (khi status = done)
GET  /jobs/{id}/measurements → measurements.json
Trạng thái theo Hình 24: queued → keyframe → colmap+vggt → fusion → plane → export → done | failed.
"""

from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import uuid
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

REPO = Path(__file__).resolve().parents[2]
JOBS_ROOT = REPO / "data" / "scenes" / "app"
CONFIG = REPO / "configs" / "default.yaml"
STAGES = ["keyframe", "sfm", "mvs", "vggt", "align", "fuse", "gate", "export"]
STATUS_OF = {"keyframe": "keyframe", "sfm": "colmap+vggt", "mvs": "colmap+vggt", "vggt": "colmap+vggt",
             "align": "fusion", "fuse": "fusion", "gate": "plane", "export": "export"}
MAX_UPLOAD = 2 * 1024 ** 3
JOB_ID = re.compile(r"^[0-9a-f]{12}$")


def run_stage_subprocess(job_id: str, stage: str) -> Tuple[bool, Optional[str], str]:
    """Chạy MỘT stage bằng `pipeline.run` (process riêng: giải phóng GPU giữa VGGT và COLMAP). Trả về (ok, mã lỗi, thông điệp)."""
    cmd = [sys.executable, "-m", "pipeline.run", "--scene", f"app/{job_id}", "--config", str(CONFIG), "--from-stage", stage, "--to-stage", stage]
    p = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, encoding="utf-8", errors="replace", env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    if p.returncode == 0:
        return True, None, ""
    meta = JOBS_ROOT / job_id / "evaluation" / "logs" / "run_meta.json"
    code = None
    if meta.is_file():
        code = json.loads(meta.read_text(encoding="utf-8")).get("stages", {}).get(stage, {}).get("error_code")
    return False, code or "E_STAGE_FAILED", f"exit {p.returncode}\n" + (p.stdout + p.stderr)[-2000:]


class JobManager:
    """Hàng đợi một luồng: GPU 8 GB chỉ chạy một job tại một thời điểm. Trạng thái lưu ở `job.json` trong thư mục scene."""

    def __init__(self, root: Path, runner: Callable[[str, str], Tuple[bool, Optional[str], str]] = run_stage_subprocess):
        self.root, self.runner, self.q = root, runner, queue.Queue()

    def start(self) -> None:
        """Gọi khi server thật khởi động (lifespan), KHÔNG gọi lúc import: tránh chạy job thật trong test."""
        for p in sorted(self.root.glob("*/job.json"), key=lambda p: p.stat().st_mtime) if self.root.is_dir() else []:
            doc = json.loads(p.read_text(encoding="utf-8"))
            if doc.get("status") not in ("done", "failed"):              # server chết giữa chừng: chạy tiếp từ stage đang dở
                self.q.put((p.parent.name, doc.get("stage") or STAGES[0]))
        threading.Thread(target=self._loop, daemon=True).start()

    def path(self, job_id: str) -> Path:
        if not JOB_ID.match(job_id):
            raise HTTPException(404, "job không tồn tại")
        return self.root / job_id

    def read(self, job_id: str) -> Dict:
        p = self.path(job_id) / "job.json"
        if not p.is_file():
            raise HTTPException(404, "job không tồn tại")
        return json.loads(p.read_text(encoding="utf-8"))

    def write(self, job_id: str, **kw) -> None:
        p = self.path(job_id) / "job.json"
        doc = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {"job_id": job_id}
        doc.update(kw, updated=time.strftime("%Y-%m-%dT%H:%M:%S"))
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(p)

    def submit(self, zip_path: Path) -> str:
        job_id = uuid.uuid4().hex[:12]
        cap = self.path(job_id) / "raw" / "capture"
        cap.mkdir(parents=True)
        try:
            with zipfile.ZipFile(zip_path) as z:
                for name in z.namelist():                                  # chặn path traversal (tên tuyệt đối, "..")
                    target = (cap / name).resolve()
                    if not str(target).startswith(str(cap.resolve())):
                        raise HTTPException(400, f"tên file không hợp lệ trong zip: {name}")
                z.extractall(cap)
        except zipfile.BadZipFile:
            raise HTTPException(400, "capture không phải file zip")
        if not (cap / "capture.json").is_file():
            raise HTTPException(400, "zip thiếu capture.json")
        mode = json.loads((cap / "capture.json").read_text(encoding="utf-8")).get("scale_mode")
        if mode not in ("ar", "tape"):
            raise HTTPException(400, "capture.json: scale_mode phải là 'ar' hoặc 'tape'")
        self.write(job_id, status="queued", stage=None, progress=0.0, error_code=None, message="", scale_mode=mode)
        self.q.put((job_id, STAGES[0]))
        return job_id

    def _loop(self) -> None:
        while True:
            job_id, start = self.q.get()
            for i, st in enumerate(STAGES):
                if i < STAGES.index(start):
                    continue
                self.write(job_id, status=STATUS_OF[st], stage=st, progress=round(i / len(STAGES), 3))
                ok, code, msg = self.runner(job_id, st)
                if not ok:
                    self.write(job_id, status="failed", error_code=code, message=msg)
                    break
            else:
                self.write(job_id, status="done", stage=None, progress=1.0)


def create_app(root: Path = JOBS_ROOT, runner=run_stage_subprocess) -> FastAPI:
    jobs = JobManager(root, runner)

    @asynccontextmanager
    async def lifespan(_):
        jobs.start()
        yield

    api = FastAPI(title="3DMeph backend", version="0.1", lifespan=lifespan)
    api.state.jobs = jobs

    @api.post("/jobs")
    async def post_job(capture: UploadFile = File(...)):
        root.mkdir(parents=True, exist_ok=True)
        tmp = root / f"upload_{uuid.uuid4().hex}.zip"
        size = 0
        with open(tmp, "wb") as f:
            while chunk := await capture.read(1 << 20):
                size += len(chunk)
                if size > MAX_UPLOAD:
                    f.close()
                    tmp.unlink(missing_ok=True)
                    raise HTTPException(413, "gói quay quá lớn")
                f.write(chunk)
        try:
            return {"job_id": jobs.submit(tmp)}
        finally:
            tmp.unlink(missing_ok=True)

    @api.get("/jobs/{job_id}")
    def get_job(job_id: str):
        return jobs.read(job_id)

    @api.get("/jobs/{job_id}/result")
    def get_result(job_id: str):
        if jobs.read(job_id)["status"] != "done":
            raise HTTPException(409, "job chưa xong")
        return FileResponse(jobs.path(job_id) / "proposed" / "export" / "model.glb", media_type="model/gltf-binary", filename="model.glb")

    @api.get("/jobs/{job_id}/measurements")
    def get_measurements(job_id: str):
        if jobs.read(job_id)["status"] != "done":
            raise HTTPException(409, "job chưa xong")
        return json.loads((jobs.path(job_id) / "proposed" / "export" / "measurements.json").read_text(encoding="utf-8"))

    return api


app = create_app()
