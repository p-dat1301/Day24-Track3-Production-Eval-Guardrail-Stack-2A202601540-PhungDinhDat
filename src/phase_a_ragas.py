from __future__ import annotations

"""Phase A: RAGAS Production Evaluation — 50q, 3 distributions, cluster analysis."""

import importlib
import json
import os
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from config import ANSWERS_PATH, TEST_SET_PATH
except ModuleNotFoundError:
    _PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    TEST_SET_PATH = os.path.join(_PROJECT_ROOT, "test_set_50q.json")
    ANSWERS_PATH = os.path.join(_PROJECT_ROOT, "answers_50q.json")

Distribution = str  # "factual" | "multi_hop" | "adversarial"


class MetricValues(Protocol):
    faithfulness: float
    answer_relevancy: float
    context_precision: float
    context_recall: float


DIAGNOSTIC_TREE = {
    "faithfulness": ("LLM hallucinating", "Tighten system prompt, lower temperature"),
    "context_recall": ("Missing relevant chunks", "Improve chunking or add BM25"),
    "context_precision": (
        "Too many irrelevant chunks",
        "Add reranking or metadata filter",
    ),
    "answer_relevancy": ("Answer doesn't match question", "Improve prompt template"),
}


@dataclass
class RagasResult:
    question_id: int
    distribution: Distribution
    question: str
    answer: str
    contexts: list[str]
    ground_truth: str
    faithfulness: float
    answer_relevancy: float
    context_precision: float
    context_recall: float

    @property
    def avg_score(self) -> float:
        return (
            self.faithfulness
            + self.answer_relevancy
            + self.context_precision
            + self.context_recall
        ) / 4

    @property
    def worst_metric(self) -> str:
        scores = {
            "faithfulness": self.faithfulness,
            "answer_relevancy": self.answer_relevancy,
            "context_precision": self.context_precision,
            "context_recall": self.context_recall,
        }
        return min(scores, key=lambda metric: scores[metric])


# ─── Đã implement sẵn ────────────────────────────────────────────────────────


def load_test_set_50q(path: str = TEST_SET_PATH) -> list[dict]:
    """Load 50q test set với 3 distributions."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_answers(path: str = ANSWERS_PATH) -> list[dict]:
    """Load pre-generated answers từ setup_answers.py."""
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"answers_50q.json không tìm thấy tại {path}\n"
            "→ Chạy trước: python setup_answers.py"
        )
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_phase_a_report(
    results: list[RagasResult], clusters: dict, path: str = "reports/ragas_50q.json"
) -> None:
    """Save Phase A report to JSON."""
    os.makedirs(os.path.dirname(path), exist_ok=True)

    per_dist: dict[str, dict] = {}
    for dist in ["factual", "multi_hop", "adversarial"]:
        subset = [r for r in results if r.distribution == dist]
        if subset:
            per_dist[dist] = {
                "count": len(subset),
                "faithfulness": sum(r.faithfulness for r in subset) / len(subset),
                "answer_relevancy": sum(r.answer_relevancy for r in subset)
                / len(subset),
                "context_precision": sum(r.context_precision for r in subset)
                / len(subset),
                "context_recall": sum(r.context_recall for r in subset) / len(subset),
                "avg_score": sum(r.avg_score for r in subset) / len(subset),
            }

    report = {
        "total_questions": len(results),
        "per_distribution": per_dist,
        "failure_clusters": clusters,
        "bottom_10": [
            {
                "rank": i + 1,
                "question_id": r.question_id,
                "distribution": r.distribution,
                "question": r.question,
                "avg_score": round(r.avg_score, 4),
                "worst_metric": r.worst_metric,
            }
            for i, r in enumerate(sorted(results, key=lambda x: x.avg_score)[:10])
        ],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"Phase A report saved → {path}")


# ─── Tasks 1-4: Sinh viên implement ──────────────────────────────────────────


def group_by_distribution(test_set: list[dict]) -> dict[str, list[dict]]:
    """Task 1: Nhóm 50 câu hỏi theo 3 distributions.

    Returns:
        {"factual": [...], "multi_hop": [...], "adversarial": [...]}
    """
    groups: dict[str, list[dict]] = {"factual": [], "multi_hop": [], "adversarial": []}
    for item in test_set:
        distribution = item.get("distribution")
        if distribution in groups:
            groups[distribution].append(item)
    return groups


def run_ragas_50q(answers: list[dict]) -> list[RagasResult]:
    """Task 2: Chạy RAGAS 4 metrics trên toàn bộ 50 câu hỏi.

    Gợi ý — import từ Day 18 của bạn:
        from src.m4_eval import evaluate_ragas

    Steps:
        1. Extract questions, answers, contexts, ground_truths từ answers list
        2. Gọi evaluate_ragas() từ m4_eval.py
        3. Kết hợp kết quả với distribution info từ answers list
        4. Return list[RagasResult]
    """
    """Evaluate answers, using m4_eval when available and local fallback otherwise."""
    questions = [str(item.get("question", "")) for item in answers]
    answer_texts = [str(item.get("answer", "")) for item in answers]
    contexts = [_contexts(item.get("contexts", [])) for item in answers]
    ground_truths = [str(item.get("ground_truth", "")) for item in answers]

    try:
        module = importlib.import_module("src.m4_eval")
        evaluate_ragas = module.evaluate_ragas
    except (ImportError, ModuleNotFoundError, AttributeError):
        print("RAGAS offline fallback: src/m4_eval.py or dependencies unavailable")
        return _fallback_results(
            answers, questions, answer_texts, contexts, ground_truths
        )

    try:
        raw = evaluate_ragas(questions, answer_texts, contexts, ground_truths)
    except (ImportError, ModuleNotFoundError, RuntimeError, ValueError):
        print("RAGAS offline fallback: evaluate_ragas unavailable or failed")
        return _fallback_results(
            answers, questions, answer_texts, contexts, ground_truths
        )

    per_question = raw.get("per_question", [])
    if not per_question or len(per_question) != len(answers):
        print("RAGAS offline fallback: incomplete per-question output")
        return _fallback_results(
            answers, questions, answer_texts, contexts, ground_truths
        )
    return [
        _result_from_metric(item, metric) for item, metric in zip(answers, per_question)
    ]


def _contexts(value: list[str] | tuple[str, ...] | str) -> list[str]:
    return [value] if isinstance(value, str) else [str(context) for context in value]


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[\\wÀ-ỹ]+", text.casefold()))


def _overlap(left: str, right: str) -> float:
    expected = _tokens(right)
    return len(_tokens(left) & expected) / len(expected) if expected else 0.0


def _fallback_results(
    answers: list[dict],
    questions: list[str],
    answer_texts: list[str],
    contexts: list[list[str]],
    ground_truths: list[str],
) -> list[RagasResult]:
    """Compute deterministic lexical metrics without network/model dependencies."""
    results: list[RagasResult] = []
    for item, question, answer, item_contexts, ground_truth in zip(
        answers, questions, answer_texts, contexts, ground_truths
    ):
        relevant = max(
            (_overlap(context, ground_truth) for context in item_contexts), default=0.0
        )
        results.append(
            RagasResult(
                question_id=int(item.get("id", 0)),
                distribution=str(item.get("distribution", "")),
                question=question,
                answer=answer,
                contexts=item_contexts,
                ground_truth=ground_truth,
                faithfulness=_overlap(answer, " ".join(item_contexts)),
                answer_relevancy=_overlap(answer, ground_truth),
                context_precision=relevant,
                context_recall=relevant,
            )
        )
    return results


def _metric_value(metric: Mapping[str, float] | MetricValues, name: str) -> float:
    if isinstance(metric, Mapping):
        return float(metric.get(name, 0.0))
    values = {
        "faithfulness": metric.faithfulness,
        "answer_relevancy": metric.answer_relevancy,
        "context_precision": metric.context_precision,
        "context_recall": metric.context_recall,
    }
    return values.get(name, 0.0)


def _result_from_metric(
    item: dict, metric: Mapping[str, float] | MetricValues
) -> RagasResult:
    return RagasResult(
        question_id=int(item.get("id", 0)),
        distribution=str(item.get("distribution", "")),
        question=str(item.get("question", "")),
        answer=str(item.get("answer", "")),
        contexts=_contexts(item.get("contexts", [])),
        ground_truth=str(item.get("ground_truth", "")),
        faithfulness=_metric_value(metric, "faithfulness"),
        answer_relevancy=_metric_value(metric, "answer_relevancy"),
        context_precision=_metric_value(metric, "context_precision"),
        context_recall=_metric_value(metric, "context_recall"),
    )


def bottom_10(results: list[RagasResult]) -> list[dict]:
    """Task 3: Lấy 10 câu hỏi có avg_score thấp nhất.

    Returns:
        [{"rank": 1, "question_id": ..., "distribution": ...,
          "question": ..., "avg_score": ..., "worst_metric": ...,
          "diagnosis": ..., "suggested_fix": ...}, ...]
    """
    output: list[dict] = []
    for rank, result in enumerate(
        sorted(results, key=lambda item: item.avg_score)[:10], 1
    ):
        diagnosis, suggested_fix = DIAGNOSTIC_TREE[result.worst_metric]
        output.append(
            {
                "rank": rank,
                "question_id": result.question_id,
                "distribution": result.distribution,
                "question": result.question,
                "avg_score": round(result.avg_score, 4),
                "worst_metric": result.worst_metric,
                "diagnosis": diagnosis,
                "suggested_fix": suggested_fix,
            }
        )
    return output


def cluster_analysis(results: list[RagasResult]) -> dict:
    """Task 4: Phân tích failure clusters theo (worst_metric × distribution).

    Mục tiêu: tìm ra distribution nào hay bị failure nhất và metric nào yếu nhất.

    Returns:
        {
          "matrix": {
            "faithfulness":      {"factual": 3, "multi_hop": 5, "adversarial": 2},
            "answer_relevancy":  {...},
            "context_precision": {...},
            "context_recall":    {...},
          },
          "dominant_failure_distribution": "multi_hop",
          "dominant_failure_metric": "context_recall",
          "insight": "..."
        }
    """
    distributions = ("factual", "multi_hop", "adversarial")
    matrix = {
        metric: {distribution: 0 for distribution in distributions}
        for metric in DIAGNOSTIC_TREE
    }
    for result in results:
        if result.worst_metric in matrix and result.distribution in distributions:
            matrix[result.worst_metric][result.distribution] += 1
    dominant_dist = max(
        distributions,
        key=lambda distribution: sum(matrix[metric][distribution] for metric in matrix),
    )
    dominant_metric = max(matrix, key=lambda metric: sum(matrix[metric].values()))
    insight = (
        f"Distribution '{dominant_dist}' có nhiều failure nhất. "
        f"Metric '{dominant_metric}' là điểm yếu chủ đạo. "
        f"Gợi ý: {DIAGNOSTIC_TREE[dominant_metric][1]}"
    )
    return {
        "matrix": matrix,
        "dominant_failure_distribution": dominant_dist,
        "dominant_failure_metric": dominant_metric,
        "insight": insight,
    }


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    test_set = load_test_set_50q()
    print(f"Loaded {len(test_set)} questions")

    groups = group_by_distribution(test_set)
    for dist, qs in groups.items():
        print(f"  {dist}: {len(qs)} questions")

    answers = load_answers()
    results = run_ragas_50q(answers)

    if results:
        b10 = bottom_10(results)
        clusters = cluster_analysis(results)
        save_phase_a_report(results, clusters)
        print("\nBottom 10 worst questions:")
        for item in b10:
            print(
                f"  #{item['rank']} [{item['distribution']}] {item['question'][:50]}... "
                f"avg={item['avg_score']:.3f} worst={item['worst_metric']}"
            )
        print(
            f"\nDominant failure: {clusters.get('dominant_failure_distribution')} / "
            f"{clusters.get('dominant_failure_metric')}"
        )
    else:
        print("⚠️  No results — implement run_ragas_50q() first.")
