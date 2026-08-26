from __future__ import annotations

"""Phase B: LLM-as-Judge — pairwise, swap-and-average, Cohen κ, bias analysis."""

import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from collections.abc import Mapping
from typing import Final, TypedDict


class Scores(TypedDict):
    A: float
    B: float


class JudgeDict(TypedDict):
    winner: str
    reasoning: str
    scores: Scores


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import HUMAN_LABELS_PATH, JUDGE_MODEL, OPENAI_API_KEY

_VALID_WINNERS: Final[frozenset[str]] = frozenset({"A", "B", "tie"})


@dataclass
class JudgeResult:
    question: str
    answer_a: str
    answer_b: str
    winner_pass1: str
    winner_pass2: str
    final_winner: str
    reasoning_pass1: str
    reasoning_pass2: str
    position_consistent: bool
    scores_pass1: Scores = field(default_factory=lambda: {"A": 0.0, "B": 0.0})
    scores_pass2: Scores = field(default_factory=lambda: {"A": 0.0, "B": 0.0})


def _normalise_result(
    raw: dict[str, str | float | int | None | dict[str, str | float | int | None]],
) -> dict[str, str | Scores]:
    winner = str(raw.get("winner", "tie")).strip().lower()
    winner = {"a": "A", "b": "B", "tie": "tie"}.get(winner, "tie")
    raw_scores = raw.get("scores", {})
    if not isinstance(raw_scores, dict):
        raw_scores = {}
    scores = {
        "A": _normalise_score(raw_scores.get("A", raw_scores.get("a", 0.0))),
        "B": _normalise_score(raw_scores.get("B", raw_scores.get("b", 0.0))),
    }
    reasoning = str(raw.get("reasoning", "")).strip()
    if winner != "tie" and not reasoning:
        reasoning = f"Answer {winner} scores higher on the requested criteria."
    return {"winner": winner, "reasoning": reasoning, "scores": scores}


def _normalise_score(value: str | float | int | None) -> float:
    try:
        score = float(value) if value is not None else 0.0
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, score))


def _fallback_judge(question: str, answer_a: str, answer_b: str) -> dict:
    question_terms = set(re.findall(r"\w+", question.lower()))

    def score(answer: str) -> float:
        answer_terms = set(re.findall(r"\w+", answer.lower()))
        overlap = len(question_terms & answer_terms) / max(len(question_terms), 1)
        has_content = min(len(answer.strip()) / 160.0, 1.0)
        return round(0.7 * overlap + 0.3 * has_content, 3)

    scores = {"A": score(answer_a), "B": score(answer_b)}
    if scores["A"] == scores["B"]:
        winner = "tie"
        reasoning = "Deterministic fallback found equal scores."
    else:
        winner = "A" if scores["A"] > scores["B"] else "B"
        reasoning = f"Deterministic fallback selected answer {winner} by lexical relevance and content coverage."
    return {"winner": winner, "reasoning": reasoning, "scores": scores}


def pairwise_judge(question: str, answer_a: str, answer_b: str) -> dict:
    """Choose stronger answer with configured OpenAI judge or deterministic fallback."""
    if not OPENAI_API_KEY.strip():
        return _fallback_judge(question, answer_a, answer_b)

    prompt = (
        "Evaluate two answers for accuracy, completeness, and conciseness. "
        "Return JSON only with winner (A, B, or tie), reasoning, and scores A/B in [0,1].\n\n"
        f"Question: {question}\nAnswer A: {answer_a}\nAnswer B: {answer_b}"
    )
    try:
        openai_module = __import__("openai")
        response = openai_module.OpenAI(api_key=OPENAI_API_KEY).chat.completions.create(
            model=JUDGE_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "You are a strict answer-quality judge. Return JSON only.",
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            return _fallback_judge(question, answer_a, answer_b)
        return _normalise_result(parsed)
    except (ImportError, OSError, TypeError, ValueError, KeyError, AttributeError):
        return _fallback_judge(question, answer_a, answer_b)


def swap_and_average(question: str, answer_a: str, answer_b: str) -> JudgeResult:
    """Judge original and swapped answer order, converting swapped scores back to A/B."""
    pass1 = _normalise_result(pairwise_judge(question, answer_a, answer_b))
    pass2_raw = _normalise_result(pairwise_judge(question, answer_b, answer_a))
    swap_map = {"A": "B", "B": "A", "tie": "tie"}
    winner_pass2 = swap_map[pass2_raw["winner"]]
    final = pass1["winner"] if pass1["winner"] == winner_pass2 else "tie"
    return JudgeResult(
        question=question,
        answer_a=answer_a,
        answer_b=answer_b,
        winner_pass1=pass1["winner"],
        winner_pass2=winner_pass2,
        final_winner=final,
        reasoning_pass1=pass1["reasoning"],
        reasoning_pass2=pass2_raw["reasoning"],
        position_consistent=pass1["winner"] == winner_pass2,
        scores_pass1=pass1["scores"],
        scores_pass2={"A": pass2_raw["scores"]["B"], "B": pass2_raw["scores"]["A"]},
    )


def cohen_kappa(judge_labels: list[int], human_labels: list[int]) -> float:
    """Return Cohen's kappa for binary labels, including degenerate inputs."""
    if len(judge_labels) != len(human_labels):
        raise ValueError("label lists must have equal length")
    if not judge_labels:
        return 0.0
    if any(label not in (0, 1) for label in [*judge_labels, *human_labels]):
        raise ValueError("labels must be 0 or 1")
    n = len(judge_labels)
    observed = (
        sum(judge == human for judge, human in zip(judge_labels, human_labels)) / n
    )
    judge_one = sum(judge_labels) / n
    human_one = sum(human_labels) / n
    expected = judge_one * human_one + (1 - judge_one) * (1 - human_one)
    if expected == 1.0:
        return 1.0 if observed == 1.0 else 0.0
    return max(-1.0, min(1.0, (observed - expected) / (1 - expected)))


def bias_report(judge_results: list[JudgeResult]) -> dict:
    """Measure position instability and preference for longer winning answers."""
    total = len(judge_results)
    position_bias_count = sum(
        not result.position_consistent for result in judge_results
    )
    decisive = sum(result.final_winner in {"A", "B"} for result in judge_results)
    a_wins_a_longer = sum(
        result.final_winner == "A" and len(result.answer_a) > len(result.answer_b)
        for result in judge_results
    )
    b_wins_b_longer = sum(
        result.final_winner == "B" and len(result.answer_b) > len(result.answer_a)
        for result in judge_results
    )
    verbosity_count = a_wins_a_longer + b_wins_b_longer
    position_rate = position_bias_count / total if total else 0.0
    verbosity_rate = verbosity_count / decisive if decisive else 0.0
    return {
        "total_judged": total,
        "position_bias_rate": round(position_rate, 3),
        "position_bias_count": position_bias_count,
        "verbosity_bias": round(verbosity_rate, 3),
        "verbosity_details": {
            "a_wins_a_longer": a_wins_a_longer,
            "b_wins_b_longer": b_wins_b_longer,
            "total_decisive": decisive,
        },
        "interpretation": (
            "Position bias cao — nên dùng swap-and-average."
            if position_rate > 0.3
            else "Position bias thấp — judge ổn định."
        ),
    }


def _report_path(filename: str) -> str:
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports", filename
    )


def generate_judge_report() -> dict:
    """Judge actual answers against ground truth for every human-labelled fixture."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "answers_50q.json"), encoding="utf-8") as file:
        answers = {int(item["id"]): item for item in json.load(file)}
    with open(HUMAN_LABELS_PATH, encoding="utf-8") as file:
        labels = json.load(file)

    results: list[JudgeResult] = []
    judge_labels: list[int] = []
    human_labels: list[int] = []
    for label in labels:
        answer = answers[int(label["question_id"])]
        result = swap_and_average(
            str(label["question"]), str(answer["answer"]), str(answer["ground_truth"])
        )
        results.append(result)
        judge_labels.append(1 if result.final_winner == "B" else 0)
        human_labels.append(int(label["human_label"]))

    provenance = "live_openai" if OPENAI_API_KEY.strip() else "offline_deterministic"
    return {
        "provenance": provenance,
        "judge_model": JUDGE_MODEL
        if provenance == "live_openai"
        else "lexical_fallback",
        "judged_pairs": [asdict(result) for result in results],
        "kappa": {
            "value": round(cohen_kappa(judge_labels, human_labels), 4),
            "sample_size": len(human_labels),
            "judge_labels": judge_labels,
            "human_labels": human_labels,
        },
        "bias": bias_report(results),
    }


def save_judge_report(report: dict, path: str | None = None) -> str:
    """Persist Phase B report without altering Phase A artifacts."""
    destination = path or _report_path("judge_results.json")
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    with open(destination, "w", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)
    return destination


if __name__ == "__main__":
    report = generate_judge_report()
    path = save_judge_report(report)
    print(f"Phase B report saved → {path} ({report['provenance']})")
    print(
        f"Cohen's κ: {report['kappa']['value']:.4f}; pairs: {len(report['judged_pairs'])}"
    )
