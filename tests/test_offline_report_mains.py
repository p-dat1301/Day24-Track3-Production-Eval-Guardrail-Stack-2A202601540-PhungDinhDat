"""Offline report-main regression tests."""

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _run(script: str) -> dict:
    environment = os.environ | {"OPENAI_API_KEY": ""}
    subprocess.run(
        [sys.executable, script],
        cwd=ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    report = "judge_results.json" if "phase_b" in script else "guard_results.json"
    return json.loads((ROOT / "reports" / report).read_text(encoding="utf-8"))


def test_phase_b_main_writes_offline_human_label_report():
    # Given: offline environment and repository human-label fixture
    # When: Phase B main runs
    report = _run("src/phase_b_judge.py")
    # Then: every human-labelled pair is judged with provenance
    assert report["provenance"] == "offline_deterministic"
    assert len(report["judged_pairs"]) == 10
    assert report["kappa"]["sample_size"] == 10


def test_phase_c_main_writes_offline_adversarial_report():
    # Given: offline environment and repository adversarial fixture
    # When: Phase C main runs
    report = _run("src/phase_c_guard.py")
    # Then: every adversarial input is evaluated with measured latency
    assert report["provenance"] == "offline_deterministic"
    assert len(report["adversarial_results"]) == 20
    assert "total_ms" in report["latency"]
