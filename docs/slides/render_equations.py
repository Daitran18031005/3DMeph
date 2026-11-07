"""Render các công thức dùng trong slide thành PNG trong suốt (matplotlib mathtext, env `3d_metric`).

Số (n) là số công thức của đề cương Docs/TaiTao3D_Metric_3DMeph.pdf; dạng chữ lấy từ README các module
(pipeline/*/README.md) đã đối chiếu với đề cương. Chạy: python render_equations.py -> img/eq_<key>.png
"""

import re
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

OUT = Path(__file__).resolve().parent / "img"
INK = "#10303A"

EQ = {
    # keyframe
    "overlap": r"$\mathrm{Overlap}=\dfrac{W-\Delta}{W}\times 100\%$",  # (1)
    "nchunk": r"$N_{chunk}=\left\lceil\dfrac{N_{kf}-o}{c-o}\right\rceil$",  # (2)
    "qblur": r"$q_{blur}=\min\left(1,\dfrac{V}{V_{ref}}\right),\ \ V=\mathrm{Var}(\nabla^{2}I)$",  # (3)
    "qexp": r"$q_{exposure}=1-\dfrac{\#\{I\leq 5\}+\#\{I\geq 250\}}{\#\mathrm{pixel}}$",  # (20)
    "qtex": r"$q_{texture}=\min\left(1,\dfrac{\|\nabla I\|_{N(k)}}{G_{ref}}\right)$",  # (20)
    # COLMAP / VGGT
    "ereproj": r"$e_{reproj}=\left\|\pi(RX+t)-x\right\|$",
    "cmodel": r"$c_{model}=1-\dfrac{1}{\mathrm{conf}}$",
    # căn tỉ lệ
    "sm": r"$s_{m}=\dfrac{L_{real}}{L_{model}}$",  # (4)
    "umeyama1": r"$y\approx s\,R\,x+t$",  # (13)
    "umeyama2": r"$\Sigma_{xy}=UDV^{\top},\ \ R=USV^{\top},\ \ s=\dfrac{\mathrm{tr}(DS)}{\sigma_{x}^{2}},\ \ t=\mu_{y}-sR\mu_{x}$",  # (14)-(17)
    "xmet": r"$X_{met}=s_{m}\,(s\,R\,X_{VGGT}+t)$",  # (18)
    # fusion
    "fconf": r"$f(x)=e^{-x/\tau}$",  # (21)
    "w": r"$w_{i,k}=c_{model}\cdot e^{-e_{reproj}/\tau_{e}}\cdot e^{-\sigma_{depth}/\tau_{\sigma}}\cdot q_{blur}\cdot q_{texture}\cdot q_{exposure}$",  # (19)
    "wtilde": r"$\tilde{w}_{i,k}=\dfrac{w_{i,k}}{\sum_{j\in V_{k}}w_{j,k}},\ \ \hat{P}_{k}=\sum_{i}\tilde{w}_{i,k}\,P_{i,k}$",  # (22)
    "wk": r"$w_{k}=\sum_{i}\tilde{w}_{i,k}\,w_{i,k}$",
    # plane gate
    "rk": r"$r_{k}=\left|n^{\top}P_{k}+d\right|$",  # (23)
    "gate": r"$g_{k}=\mathbb{1}\left[\,r_{k}<\tau_{r}\ \wedge\ \theta_{k}<\tau_{n}\ \wedge\ s_{k}\in S_{struct}\ \wedge\ w_{k}>\tau_{w}\right]$",  # (24)
    "proj": r"$P'_{k}=P_{k}-\alpha\,g_{k}\,\left(n^{\top}P_{k}+d\right)\,n$",  # (25)
    # đo và đánh giá
    "measure": r"$\|B-A\|_{2}=\sqrt{(x_{B}-x_{A})^{2}+(y_{B}-y_{A})^{2}+(z_{B}-z_{A})^{2}}$",  # (30)
    "delta": r"$\Delta\%=\dfrac{m_{before}-m_{after}}{m_{before}}\times 100\%$",  # (31)
    "mae": r"$\mathrm{MAE}=\dfrac{1}{M}\sum_{m=1}^{M}\left|\hat{L}_{m}-L_{m}\right|$",  # (32)
}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    plt.rcParams["mathtext.fontset"] = "cm"
    for key, tex in EQ.items():
        tex = re.sub(r"_\{([A-Za-z]{2,})\}", r"_{\\mathrm{\1}}", tex)  # chỉ số nhiều chữ: chữ đứng, không nghiêng
        fig = plt.figure(figsize=(0.1, 0.1), dpi=300)
        fig.text(0, 0, tex, fontsize=26, color=INK)
        fig.savefig(OUT / f"eq_{key}.png", transparent=True, bbox_inches="tight", pad_inches=0.04)
        plt.close(fig)
    print(len(EQ), "công thức ->", OUT)


if __name__ == "__main__":
    sys.exit(main())
