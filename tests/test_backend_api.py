"""Test app/backend_fastapi/main.py với runner giả (không chạy GPU): POST → trạng thái → kết quả; lỗi trả failed + mã; chặn zip độc."""

import io
import json
import time
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.backend_fastapi import main as bk


def _zip(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


def _capture(mode="ar"):
    return _zip({"capture.json": json.dumps({"scale_mode": mode, "frames": []}), "frames/000000.jpg": b"x"})


def _wait(client, job_id, until=("done", "failed"), timeout=5.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        doc = client.get(f"/jobs/{job_id}").json()
        if doc["status"] in until:
            return doc
        time.sleep(0.02)
    raise AssertionError(f"job kẹt ở {doc}")


@pytest.fixture
def make_client(tmp_path):
    def make(runner):
        return TestClient(bk.create_app(tmp_path, runner)).__enter__()
    return make


def test_job_chay_het_cac_stage_roi_tra_glb(make_client, tmp_path):
    seen = []

    def runner(job_id, stage):
        seen.append(stage)
        if stage == "export":
            out = tmp_path / job_id / "proposed" / "export"
            out.mkdir(parents=True)
            (out / "model.glb").write_bytes(b"glTF")
            (out / "measurements.json").write_text('{"unit": "m"}', encoding="utf-8")
        return True, None, ""

    c = make_client(runner)
    job_id = c.post("/jobs", files={"capture": ("c.zip", _capture(), "application/zip")}).json()["job_id"]
    doc = _wait(c, job_id)
    assert doc["status"] == "done" and doc["progress"] == 1.0 and seen == bk.STAGES
    assert c.get(f"/jobs/{job_id}/result").content == b"glTF"
    assert c.get(f"/jobs/{job_id}/measurements").json() == {"unit": "m"}


def test_job_loi_tra_failed_va_ma_loi(make_client):
    c = make_client(lambda job_id, stage: (stage != "sfm", None if stage != "sfm" else "E_SFM_FAILED", "boom"))
    job_id = c.post("/jobs", files={"capture": ("c.zip", _capture("tape"), "application/zip")}).json()["job_id"]
    doc = _wait(c, job_id)
    assert doc["status"] == "failed" and doc["error_code"] == "E_SFM_FAILED" and doc["stage"] == "sfm"
    assert c.get(f"/jobs/{job_id}/result").status_code == 409


def test_khoi_dong_lai_chay_tiep_job_do_dang(tmp_path):
    (tmp_path / "aaaaaaaaaaaa").mkdir()
    (tmp_path / "aaaaaaaaaaaa" / "job.json").write_text(json.dumps({"job_id": "aaaaaaaaaaaa", "status": "fusion", "stage": "fuse"}), encoding="utf-8")
    (tmp_path / "bbbbbbbbbbbb").mkdir()
    (tmp_path / "bbbbbbbbbbbb" / "job.json").write_text(json.dumps({"job_id": "bbbbbbbbbbbb", "status": "done"}), encoding="utf-8")
    seen = []
    c = TestClient(bk.create_app(tmp_path, lambda j, s: (seen.append((j, s)) or True, None, ""))).__enter__()
    assert _wait(c, "aaaaaaaaaaaa")["status"] == "done"
    assert seen == [("aaaaaaaaaaaa", s) for s in ("fuse", "gate", "export")]


def test_tu_choi_zip_doc_va_thieu_capture(make_client):
    c = make_client(lambda j, s: (True, None, ""))
    evil = _zip({"../evil.txt": "x", "capture.json": json.dumps({"scale_mode": "ar"})})
    assert c.post("/jobs", files={"capture": ("c.zip", evil, "application/zip")}).status_code == 400
    assert c.post("/jobs", files={"capture": ("c.zip", _zip({"a.txt": "x"}), "application/zip")}).status_code == 400
    assert c.post("/jobs", files={"capture": ("c.zip", _capture("abc"), "application/zip")}).status_code == 400
    assert c.get("/jobs/../../etc").status_code == 404
