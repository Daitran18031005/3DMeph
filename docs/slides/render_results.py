"""Render hình kết quả của scene dev 42444738 cho slide (chạy bằng env conda `3d_metric`).

Đầu vào: dữ liệu thật trong data/scenes/arkitscenes/42444738/. Đầu ra: docs/slides/img/res_*.png.
Dùng matplotlib (không cần OpenGL ngoài màn hình). Trục "lên" lấy bằng PCA (trục phương sai nhỏ nhất):
phòng 5 x 5 m cao ~2,5 m nên đúng cho mọi biến thể; dấu của trục lên chọn sao cho sàn ở dưới.
"""

import shutil
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SCENE = ROOT / "data" / "scenes" / "arkitscenes" / "42444738"
OUT = Path(__file__).resolve().parent / "img"
RNG = np.random.default_rng(0)


def read_ply(path: Path) -> dict[str, np.ndarray]:
    """Đọc PLY binary little endian có property vô hướng (đủ cho các file của pipeline)."""
    fmt = {"float": "f4", "double": "f8", "uchar": "u1", "int": "i4", "uint": "u4", "short": "i2", "ushort": "u2"}
    with open(path, "rb") as f:
        n, props = 0, []
        while True:
            line = f.readline().decode("latin1").strip()
            if line.startswith("element vertex"):
                n = int(line.split()[-1])
            elif line.startswith("property"):
                _, t, name = line.split()
                props.append((name, "<" + fmt[t]))
            elif line == "end_header":
                break
        arr = np.fromfile(f, dtype=np.dtype(props), count=n)
    return {name: arr[name] for name, _ in props}


def to_room_frame(xyz: np.ndarray):
    """Trả về (tọa độ [a, b, up], ma trận quay) với up = trục phương sai nhỏ nhất."""
    c = xyz - np.median(xyz, axis=0)
    # lọc điểm xa (ngoài cửa sổ) để PCA ổn định
    keep = np.linalg.norm(c, axis=1) < np.percentile(np.linalg.norm(c, axis=1), 97)
    w, v = np.linalg.eigh(np.cov(c[keep].T))
    R = v[:, [2, 1, 0]]  # cột: trục lớn, trục vừa, trục nhỏ (lên)
    return c @ R, R


def crop_room(p: np.ndarray, extra=None):
    """Cắt phần phòng: bỏ điểm nhìn xuyên cửa sổ (ngoài 2–98%)."""
    lo, hi = np.percentile(p, [2, 98], axis=0)
    m = np.all((p >= lo - 0.3) & (p <= hi + 0.3), axis=1)
    return m


def scatter_top(p, color, path, title=None, cmap=None, vmin=None, vmax=None, s=0.5, cbar=None):
    fig, ax = plt.subplots(figsize=(6, 5), dpi=200)
    order = np.argsort(p[:, 2])  # điểm cao vẽ sau
    sc = ax.scatter(
        p[order, 0], p[order, 1], c=color[order], s=s, cmap=cmap, vmin=vmin, vmax=vmax, linewidths=0, rasterized=True
    )
    ax.set_aspect("equal")
    ax.axis("off")
    if cbar:
        cb = fig.colorbar(sc, ax=ax, shrink=0.7, pad=0.01)
        cb.set_label(cbar, fontsize=9)
    if title:
        ax.set_title(title, fontsize=10)
    fig.tight_layout(pad=0.2)
    fig.savefig(path, transparent=False, facecolor="white")
    plt.close(fig)


def scatter_3d(p, color, path, elev=32, azim=-55, s=0.6, cmap=None, vmin=None, vmax=None):
    fig = plt.figure(figsize=(6.4, 4.6), dpi=200)
    ax = fig.add_subplot(111, projection="3d")
    ax.scatter(
        p[:, 0],
        p[:, 1],
        p[:, 2],
        c=color,
        s=s,
        cmap=cmap,
        vmin=vmin,
        vmax=vmax,
        depthshade=False,
        linewidths=0,
        rasterized=True,
    )
    ext = np.ptp(p, axis=0)
    ax.set_box_aspect(ext / ext.max())
    ax.view_init(elev=elev, azim=azim)
    ax.axis("off")
    fig.subplots_adjust(0, 0, 1, 1)
    fig.savefig(path, facecolor="white")
    plt.close(fig)


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    # 1) keyframe: lưới 6 khung đều nhau trong 80 keyframe + 1 khung làm nền tiêu đề
    kfs = sorted((SCENE / "frames" / "keyframes").glob("*.jpg"))
    idx = np.linspace(0, len(kfs) - 1, 6).astype(int)
    ims = [Image.open(kfs[i]).convert("RGB") for i in idx]
    h = 320
    ims = [im.resize((int(im.width * h / im.height), h)) for im in ims]
    W = sum(im.width for im in ims[:3]) + 8 * 2
    sheet = Image.new("RGB", (W, h * 2 + 8), "white")
    for k, im in enumerate(ims):
        x = sum(i.width + 8 for i in ims[(k // 3) * 3 : k]) if k % 3 else 0
        sheet.paste(im, (x, (k // 3) * (h + 8)))
    sheet.save(OUT / "res_keyframes.png")
    ims[2].save(OUT / "res_keyframe_single.png")
    print("keyframes", len(kfs), "->", list(idx))

    # 2) B0: mây điểm dày MVS đã ra mét, có màu
    b0 = read_ply(SCENE / "baselines" / "colmap" / "metric" / "fused_metric.ply")
    xyz = np.c_[b0["x"], b0["y"], b0["z"]]
    rgb = np.c_[b0["red"], b0["green"], b0["blue"]] / 255.0
    p, R = to_room_frame(xyz)
    m = crop_room(p)
    p, rgb = p[m], rgb[m]
    # up: sàn có nhiều điểm hơn gần đáy -> đặt dấu sao cho trọng tâm lệch lên
    if np.mean(p[:, 2] - np.median(p[:, 2])) < 0:
        p[:, 2] *= -1
    p[:, 2] -= p[:, 2].min()
    scatter_top(p, rgb, OUT / "res_b0_top.png", s=0.4)
    sel = RNG.choice(len(p), min(len(p), 70000), replace=False)
    scatter_3d(p[sel], rgb[sel], OUT / "res_b0_3d.png", s=1.0)
    print("b0", len(p), np.ptp(p, axis=0).round(2))

    # 3) Điểm đã ghép: màu theo w_k (độ tin cậy) + 4) mặt phẳng / cổng
    rp = read_ply(SCENE / "proposed" / "plane_refinement" / "refined_points.ply")
    q = np.c_[rp["x"], rp["y"], rp["z"]]
    wk, g, pid = rp["w_k"], rp["g"], rp["plane_id"]
    pq, _ = to_room_frame(q)
    mq = crop_room(pq)
    pq, wk, g, pid = pq[mq], wk[mq], g[mq], pid[mq]
    if np.mean(pq[:, 2] - np.median(pq[:, 2])) < 0:
        pq[:, 2] *= -1
    scatter_top(
        pq, wk, OUT / "res_wk_top.png", cmap="viridis", vmin=0, vmax=0.8, s=0.5, cbar="w_k (độ tin cậy sau fusion)"
    )
    sel = RNG.choice(len(pq), min(len(pq), 60000), replace=False)
    scatter_3d(pq[sel], wk[sel], OUT / "res_wk_3d.png", cmap="viridis", vmin=0, vmax=0.8, s=1.0)

    cols = plt.get_cmap("tab10")(np.where(pid >= 0, pid % 10, 9))
    cols[pid < 0] = (0.8, 0.8, 0.8, 1)
    fig, axs = plt.subplots(1, 2, figsize=(11, 4.8), dpi=200)
    order = np.argsort(pq[:, 2])
    axs[0].scatter(pq[order, 0], pq[order, 1], c=cols[order], s=0.5, linewidths=0, rasterized=True)
    axs[0].set_title("Mặt phẳng RANSAC (mỗi màu một mặt phẳng)", fontsize=10)
    ok = g > 0
    axs[1].scatter(pq[~ok, 0], pq[~ok, 1], c="#bbbbbb", s=0.4, linewidths=0, rasterized=True)
    axs[1].scatter(pq[ok, 0], pq[ok, 1], c="#d62728", s=1.6, linewidths=0, rasterized=True)
    axs[1].set_title(f"Điểm qua cổng g=1: {int(ok.sum())}/{len(g)} ({100 * ok.mean():.2f}%)", fontsize=10)
    for a in axs:
        a.set_aspect("equal")
        a.axis("off")
    fig.tight_layout(pad=0.3)
    fig.savefig(OUT / "res_planes_gate.png", facecolor="white")
    plt.close(fig)
    print("proposed pts", len(pq), "gate pass", int(ok.sum()))

    # 5) mesh GLB (Poisson), tô bóng theo pháp tuyến
    try:
        import open3d as o3d
        import trimesh

        sc = trimesh.load(SCENE / "proposed" / "export" / "model.glb", force="scene")
        mesh = trimesh.util.concatenate([g for g in sc.geometry.values()])
        om = o3d.geometry.TriangleMesh(
            o3d.utility.Vector3dVector(mesh.vertices), o3d.utility.Vector3iVector(mesh.faces)
        )
        om = om.simplify_quadric_decimation(40000)
        V, F = np.asarray(om.vertices), np.asarray(om.triangles)
        # GLB là +Y lên: đưa về (x, z, y) để vẽ với z lên
        V = V[:, [0, 2, 1]]
        lo, hi = np.percentile(V, [1, 99], axis=0)
        keepf = np.all((V[F] >= lo - 0.5).all(axis=1) & (V[F] <= hi + 0.5).all(axis=1), axis=1)
        F = F[keepf]
        tri = V[F]
        n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-9
        light = np.array([0.4, -0.5, 0.8])
        light /= np.linalg.norm(light)
        shade = 0.35 + 0.65 * np.abs(n @ light)
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection

        fig = plt.figure(figsize=(6.4, 4.6), dpi=200)
        ax = fig.add_subplot(111, projection="3d")
        pc = Poly3DCollection(tri, facecolors=np.c_[shade, shade, shade * 1.02].clip(0, 1), linewidths=0)
        ax.add_collection3d(pc)
        ext = np.ptp(V[np.unique(F)], axis=0)
        c0 = (V[np.unique(F)].max(0) + V[np.unique(F)].min(0)) / 2
        ax.set_xlim(c0[0] - ext[0] / 2, c0[0] + ext[0] / 2)
        ax.set_ylim(c0[1] - ext[1] / 2, c0[1] + ext[1] / 2)
        ax.set_zlim(c0[2] - ext[2] / 2, c0[2] + ext[2] / 2)
        ax.set_box_aspect(ext / ext.max())
        ax.view_init(elev=38, azim=-60)
        ax.axis("off")
        fig.subplots_adjust(0, 0, 1, 1)
        fig.savefig(OUT / "res_mesh.png", facecolor="white")
        plt.close(fig)
        print("mesh faces", len(F), "bbox", ext.round(2))
    except Exception as e:  # noqa: BLE001
        print("mesh render failed:", repr(e))

    # 6) hình căn Faro có sẵn
    shutil.copy(SCENE / "evaluation" / "logs" / "faro_align_topdown_final.png", OUT / "res_faro_topdown.png")


if __name__ == "__main__":
    sys.exit(main())
