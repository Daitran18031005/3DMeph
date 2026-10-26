"""Test cho scripts/check_docs.py: bản sao sạch phải qua; từng loại lỗi cố ý gây ra phải bị phát hiện."""

import importlib.util
import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def _load_module():
    spec = importlib.util.spec_from_file_location("check_docs_under_test", REPO / "scripts" / "check_docs.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def sandbox(tmp_path):
    root = tmp_path / "repo"
    shutil.copytree(
        REPO, root,
        ignore=shutil.ignore_patterns(".git", "raw", "processed", "self_collected", "scenes",
                                      "__pycache__", ".pytest_cache", "tests"),
    )
    return root


def run_all(root):
    cd = _load_module()
    cd.REPO = root
    cd.errors.clear()
    cd.check_config_vs_readme()
    cd.check_module_headings()
    for p in cd.readme_files():
        cd.check_content(p)
        cd.check_links(p)
        cd.run_bash_blocks(p, run=False)
    return list(cd.errors)


def edit(path, old, new):
    text = path.read_text(encoding="utf-8")
    assert old in text, f"không tìm thấy đoạn cần sửa trong {path.name}"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def test_clean_copy_passes(sandbox):
    assert run_all(sandbox) == []


def test_detects_undocumented_config_key(sandbox):
    cfg = sandbox / "configs" / "default.yaml"
    edit(cfg, "  use_quality: true", "  use_quality: true\n  brand_new_key: 1")
    errs = run_all(sandbox)
    assert any("fusion.brand_new_key" in e and "chưa được mô tả" in e for e in errs)


def test_detects_readme_key_missing_from_config(sandbox):
    readme = sandbox / "pipeline" / "fusion" / "README.md"
    edit(readme, "| `fusion.e_cap_px` | 4.0 |", "| `fusion.ghost` | 1 | x |\n| `fusion.e_cap_px` | 4.0 |")
    errs = run_all(sandbox)
    assert any("fusion.ghost" in e for e in errs)


def test_detects_value_mismatch(sandbox):
    readme = sandbox / "pipeline" / "fusion" / "README.md"
    edit(readme, "| `fusion.tau_e` | 2.0 |", "| `fusion.tau_e` | 3.0 |")
    errs = run_all(sandbox)
    assert any("fusion.tau_e" in e and "default.yaml" in e for e in errs)


def test_detects_legacy_lambda_symbol(sandbox):
    edit(sandbox / "pipeline" / "fusion" / "README.md", "## Vai trò\n", "## Vai trò\n\nDùng λ_r làm thang.\n")
    assert any("λ_r" in e for e in run_all(sandbox))


def test_detects_formula_number_out_of_range_but_ignores_function_calls(sandbox):
    readme = sandbox / "pipeline" / "plane_gate" / "README.md"
    edit(readme, "## Vai trò\n", "## Vai trò\n\nTheo công thức (99) và f(0)=1.\n")
    errs = run_all(sandbox)
    assert any("(99)" in e for e in errs)
    assert not any("(0)" in e for e in errs)  # f(0) là lời gọi hàm, không phải số công thức


def test_detects_unqualified_581(sandbox):
    edit(sandbox / "pipeline" / "common" / "README.md", "## Vai trò\n", "## Vai trò\n\nGiá trị V_ref là 581.\n")
    assert any("581" in e for e in run_all(sandbox))


def test_detects_missing_heading(sandbox):
    edit(sandbox / "pipeline" / "export" / "README.md", "## Lỗi thường gặp", "## Mục khác")
    errs = run_all(sandbox)
    assert any("export" in e and "Lỗi thường gặp" in e for e in errs)


def test_detects_untagged_bash_block_and_broken_link(sandbox):
    readme = sandbox / "pipeline" / "colmap" / "README.md"
    edit(readme, "## Vai trò\n", "## Vai trò\n\n```bash\necho chưa gắn nhãn\n```\n\n[hỏng](khong_ton_tai.md)\n")
    errs = run_all(sandbox)
    assert any("# check" in e and "colmap" in e for e in errs)
    assert any("khong_ton_tai.md" in e for e in errs)


def test_module_without_readme_is_reported(sandbox):
    new = sandbox / "pipeline" / "newmod"
    new.mkdir()
    (new / "__init__.py").write_text("", encoding="utf-8")
    assert any("newmod" in e and "README" in e for e in run_all(sandbox))
