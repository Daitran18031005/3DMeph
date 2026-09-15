# pipeline/

Lõi kỹ thuật của 3DMeph — 2 pipeline độc lập + module fusion:

- colmap/     : chạy COLMAP SfM (Bundle Adjustment -> e^reproj) + MVS
                (photometric/geometric depth -> sigma^depth) HOÀN TOÀN TÁCH BIỆT với VGGT
                (đây là điểm khác biệt cốt lõi so với demo_colmap.py có sẵn của VGGT).
- vggt/       : chạy VGGT feed-forward, lấy c^model (aleatoric uncertainty, Section 3.4).
- fusion/     : công thức 6 thành phần w_tilde = c^model * e^{-lambda_r * e^reproj}
                * e^{-lambda_d * sigma^depth} * q^blur * q^texture * q^exposure
                + train_confidence_head.py (L_p2s + L_cons + L_reg, nâng cấp rule-based -> MLP)
- alignment/  : Umeyama/Procrustes robust (qua pycolmap) căn khung toạ độ COLMAP <-> VGGT
- eval/       : tính sai số chiều dài, plane error so với Replica ground truth
