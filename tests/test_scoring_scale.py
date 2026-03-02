from codecompass.evaluate.lib.scoring import (
    _scale_multiplier,
    build_deductions,
    count_grade_drops,
    confidence_interval_for,
    run_scoring,
)


# --- _scale_multiplier ---

def test_scale_micro_and_small():
    assert _scale_multiplier(0) == 1
    assert _scale_multiplier(49) == 1
    assert _scale_multiplier(50) == 1
    assert _scale_multiplier(499) == 1


def test_scale_medium():
    assert _scale_multiplier(500) == 2
    assert _scale_multiplier(4_999) == 2


def test_scale_large():
    assert _scale_multiplier(5_000) == 3
    assert _scale_multiplier(19_999) == 3


def test_scale_xlarge():
    assert _scale_multiplier(20_000) == 4
    assert _scale_multiplier(49_999) == 4


def test_scale_xxlarge():
    assert _scale_multiplier(50_000) == 5
    assert _scale_multiplier(99_999) == 5


def test_scale_enterprise():
    assert _scale_multiplier(100_000) == 6
    assert _scale_multiplier(999_999) == 6


# --- build_deductions ---

def test_build_deductions_default_scale_unchanged():
    # scale=1 (default): hard cap triggers at >= 3 critical types
    d = build_deductions({"critical": 2, "major": 0})
    assert d["critical_cap"] == 10          # 2 < 3, no hard cap
    assert d["critical_deduction"] == 2.0

    d = build_deductions({"critical": 3, "major": 0})
    assert d["critical_cap"] == 3           # 3 >= 3, hard cap


def test_build_deductions_xlarge_scale():
    # scale=4: hard cap triggers at >= 12 critical types
    d = build_deductions({"critical": 5, "major": 0}, scale_multiplier=4)
    assert d["critical_cap"] == 10          # 5 < 12, no hard cap
    assert d["critical_deduction"] == 5.0

    d = build_deductions({"critical": 12, "major": 0}, scale_multiplier=4)
    assert d["critical_cap"] == 3           # 12 >= 12, hard cap

    # major cap: triggers at >= 20 (5*4)
    d = build_deductions({"critical": 0, "major": 19}, scale_multiplier=4)
    assert d["major_cap"] == 10             # 19 < 20

    d = build_deductions({"critical": 0, "major": 20}, scale_multiplier=4)
    assert d["major_cap"] == 5              # 20 >= 20, hard cap


def test_build_deductions_caps_contribution():
    # Effective types counted for deduction are capped at type_cap
    d = build_deductions({"critical": 50, "major": 0}, scale_multiplier=1)
    assert d["critical_deduction"] == 3.0   # capped at 3 types * 1.0
    assert d["critical_type_count"] == 50   # raw count preserved


# --- count_grade_drops ---

def test_count_grade_drops_scale_1():
    # _CRITICAL_DROP_TABLE: [(12,3),(4,2),(1,1)] * scale=1
    assert count_grade_drops({"critical": 1, "major": 0}) == 1   # >= 1*1
    assert count_grade_drops({"critical": 4, "major": 0}) == 2   # >= 4*1
    assert count_grade_drops({"critical": 12, "major": 0}) == 3  # >= 12*1


def test_count_grade_drops_scale_4():
    # thresholds multiplied by 4
    assert count_grade_drops({"critical": 3, "major": 0}, scale_multiplier=4) == 0   # < 1*4=4
    assert count_grade_drops({"critical": 4, "major": 0}, scale_multiplier=4) == 1   # >= 4*1
    assert count_grade_drops({"critical": 16, "major": 0}, scale_multiplier=4) == 2  # >= 4*4
    assert count_grade_drops({"critical": 48, "major": 0}, scale_multiplier=4) == 3  # >= 12*4


# --- confidence_interval_for (files_read replaces source_file_count) ---

def test_confidence_interval_sparsity_uses_files_read():
    # 5 instances, 200 files_read: sparsity_floor = 0.01*200 = 2 -> not sparse
    ci = confidence_interval_for("high", True, 5, files_read=200)
    assert ci["grade_stability"] == "stable"

    # 1 instance, 200 files_read: floor=2 -> sparse -> +0.5
    ci = confidence_interval_for("high", True, 1, files_read=200)
    assert ci["confidence_interval"] == 1.5   # 1.0 base + 0.5 sparsity

    # 0 files_read: sparsity floor skipped entirely
    ci = confidence_interval_for("high", True, 1, files_read=0)
    assert ci["grade_stability"] == "stable"


# --- run_scoring adds scale block ---

def test_run_scoring_includes_scale_block():
    evidence = {
        "repository": "test",
        "discipline": "python",
        "date": "2026-01-01",
        "source_file_count": 20_000,   # XLarge -> multiplier=4
        "files_read": 150,
        "principles": {},
    }
    result = run_scoring(evidence, {}, "numerical")
    assert result["scale"]["multiplier"] == 4
    assert result["scale"]["tier"] == "XLarge"
    assert result["scale"]["files_read"] == 150
