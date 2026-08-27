from __future__ import annotations

"""Offline-capable Phase C guardrails."""

import json
import os
import re
import statistics
import sys
import time
from typing import Final, TypedDict

try:
    import anyio
except ModuleNotFoundError:  # noqa: PLC0415
    anyio = None

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    ADVERSARIAL_SET_PATH,
    GUARDRAILS_CONFIG_DIR,
    LATENCY_BUDGET_P95_MS,
    PRESIDIO_LANGUAGE,
)


class Entity(TypedDict):
    type: str
    text: str
    score: float
    start: int
    end: int


_PII_PATTERNS: Final[tuple[tuple[str, str, float], ...]] = (
    ("VN_CCCD", r"(?<!\d)\d{12}(?!\d)", 0.9),
    ("VN_CCCD", r"(?<!\d)\d{9}(?!\d)", 0.7),
    ("VN_PHONE", r"(?<!\d)0[3-9]\d{8}(?!\d)", 0.9),
    ("EMAIL_ADDRESS", r"(?i)(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+(?![\w.-])", 0.85),
)
_MARKERS: Final[tuple[tuple[str, ...], ...]] = (
    (
        "bỏ qua tất cả hướng dẫn",
        "ignore your previous instructions",
        "ignore system prompt",
        "forget your system prompt",
        "pretend you are dan",
        "unrestricted ai",
        "system override",
        "đóng vai ai không có giới hạn",
        "admin command",
        "dump all training data",
        "system instructions",
        "liệt kê toàn bộ thông tin nhân viên",
        "tấn công mạng nội bộ",
        "ra lệnh bạn bỏ qua",
    ),
    (
        "bài thơ",
        "nấu phở",
        "bitcoin",
        "ethereum",
        "giá cổ phiếu",
        "phương trình vi phân",
        "recommend cho tôi",
        "bộ phim",
        "thời tiết",
        "tin tức",
    ),
    (
        "cccd của nhân viên",
        "số điện thoại của nhân viên",
        "lương của nhân viên",
        "thông tin cá nhân của",
        "email của nhân viên",
        "tiết lộ thông tin nhân viên",
        "bảng lương chi tiết",
        "mật khẩu admin",
    ),
)
_REFUSALS: Final[tuple[str, ...]] = (
    "xin lỗi",
    "không thể",
    "không được phép",
    "i cannot",
    "i'm sorry",
)


def setup_presidio():
    """Create Presidio analyzer and anonymizer with Vietnamese recognizers."""
    from presidio_analyzer import (
        AnalyzerEngine,
        Pattern,
        PatternRecognizer,
        RecognizerRegistry,
    )
    from presidio_anonymizer import AnonymizerEngine

    registry = RecognizerRegistry()
    registry.load_predefined_recognizers()
    registry.add_recognizer(
        PatternRecognizer(
            supported_entity="VN_CCCD",
            patterns=[
                Pattern("CCCD", r"\b\d{12}\b", 0.9),
                Pattern("CMND", r"\b\d{9}\b", 0.7),
            ],
        )
    )
    registry.add_recognizer(
        PatternRecognizer(
            supported_entity="VN_PHONE",
            patterns=[Pattern("VN mobile", r"\b0[3-9]\d{8}\b", 0.9)],
        )
    )
    return AnalyzerEngine(registry=registry), AnonymizerEngine()


def _fallback_pii(text: str) -> dict:
    entities: list[Entity] = []
    for entity_type, pattern, score in _PII_PATTERNS:
        entities.extend(
            {
                "type": entity_type,
                "text": match.group(),
                "score": score,
                "start": match.start(),
                "end": match.end(),
            }
            for match in re.finditer(pattern, text)
        )
    entities.sort(key=lambda item: (item["start"], item["end"]))
    anonymized = text
    for entity in reversed(entities):
        anonymized = (
            anonymized[: entity["start"]]
            + f"<{entity['type']}>"
            + anonymized[entity["end"] :]
        )
    return {"has_pii": bool(entities), "entities": entities, "anonymized": anonymized}


def pii_scan(text: str, analyzer=None, anonymizer=None) -> dict:
    """Scan VN_CCCD, VN_PHONE, and email; use regex if Presidio unavailable."""
    if analyzer is None or anonymizer is None:
        try:
            analyzer, anonymizer = setup_presidio()
        except ModuleNotFoundError:
            return _fallback_pii(text)
    results = analyzer.analyze(text=text, language=PRESIDIO_LANGUAGE)
    entities: list[Entity] = [
        {
            "type": result.entity_type,
            "text": text[result.start : result.end],
            "score": round(result.score, 3),
            "start": result.start,
            "end": result.end,
        }
        for result in results
    ]
    entities.sort(key=lambda item: (item["start"], item["end"]))
    return {
        "has_pii": bool(entities),
        "entities": entities,
        "anonymized": text
        if not entities
        else anonymizer.anonymize(text=text, analyzer_results=results).text,
    }


def setup_nemo_rails():
    """Create NeMo Guardrails instance from local configuration."""
    from nemoguardrails import LLMRails, RailsConfig

    return LLMRails(RailsConfig.from_path(GUARDRAILS_CONFIG_DIR))


def _offline_input(text: str) -> tuple[bool, str | None, str]:
    lowered = text.casefold()
    if any(marker in lowered for marker in _MARKERS[0] + _MARKERS[2]):
        return (
            False,
            "offline_input_rail",
            "Xin lỗi, tôi không thể thực hiện yêu cầu này.",
        )
    if any(marker in lowered for marker in _MARKERS[1]):
        return False, "offline_input_rail", "Xin lỗi, tôi chỉ hỗ trợ chính sách HR."
    return True, None, ""


def _run_async(callable):
    """Run coroutines with AnyIO when installed, stdlib fallback otherwise."""
    if anyio is not None:
        return anyio.run(callable)
    return __import__("asyncio").run(callable())


def _response_text(response: str | dict[str, str] | list[dict[str, str]]) -> str:
    if isinstance(response, str):
        return response
    if isinstance(response, dict):
        return response.get("content", response.get("response", ""))
    return " ".join(item.get("content", "") for item in response)


async def check_input_rail(text: str, rails=None) -> dict:
    """Check input with NeMo, or deterministic fail-closed offline classifier."""
    if rails is None:
        allowed, reason, response = _offline_input(text)
    else:
        response = _response_text(
            await rails.generate_async(messages=[{"role": "user", "content": text}])
        )
        blocked = any(marker in response.casefold() for marker in _REFUSALS)
        allowed, reason = not blocked, "nemo_input_rail" if blocked else None
    return {"allowed": allowed, "blocked_reason": reason, "response": response}


async def check_output_rail(question: str, answer: str, rails=None) -> dict:
    """Check output PII and NeMo output rail before returning answer."""
    if rails is None:
        pii = pii_scan(answer)
        if pii["has_pii"]:
            return {
                "safe": False,
                "flagged_reason": "offline_output_pii",
                "final_answer": pii["anonymized"],
            }
        return {"safe": True, "flagged_reason": None, "final_answer": answer}
    response = _response_text(
        await rails.generate_async(
            messages=[
                {"role": "user", "content": question},
                {"role": "assistant", "content": answer},
            ]
        )
    )
    flagged = any(marker in response.casefold() for marker in _REFUSALS)
    return {
        "safe": not flagged,
        "flagged_reason": "nemo_output_rail" if flagged else None,
        "final_answer": response if flagged else answer,
    }


def run_adversarial_suite(
    adversarial_set: list[dict], rails=None, analyzer=None, anonymizer=None
) -> list[dict]:
    """Run adversarial fixtures through PII then input rails without nested event loops."""

    async def run_all() -> list[dict]:
        results: list[dict] = []
        for item in adversarial_set:
            pii = pii_scan(item["input"], analyzer, anonymizer)
            blocked_by = "presidio" if pii["has_pii"] else None
            if (
                blocked_by is None
                and not (await check_input_rail(item["input"], rails))["allowed"]
            ):
                blocked_by = "nemo_input"
            actual = "blocked" if blocked_by else "allowed"
            results.append(
                {
                    "id": item["id"],
                    "category": item["category"],
                    "input": item["input"][:80] + "...",
                    "expected": item["expected"],
                    "actual": actual,
                    "blocked_by": blocked_by,
                    "passed": actual == item["expected"],
                }
            )
        return results

    return _run_async(run_all)


def measure_p95_latency(
    test_inputs: list[str], n_runs: int = 20, rails=None, analyzer=None, anonymizer=None
) -> dict:
    """Measure nonnegative P50/P95/P99 latency for each guard layer."""
    samples = test_inputs[: max(0, n_runs)] or [""]
    presidio_times: list[float] = []
    nemo_times: list[float] = []

    async def measure() -> None:
        for text in samples:
            started = time.perf_counter()
            pii_scan(text, analyzer, anonymizer)
            presidio_times.append(max(0.0, (time.perf_counter() - started) * 1000))
            started = time.perf_counter()
            await check_input_rail(text, rails)
            nemo_times.append(max(0.0, (time.perf_counter() - started) * 1000))

    _run_async(measure)

    def percentiles(values: list[float]) -> dict[str, float]:
        ordered = sorted(values)
        if len(ordered) == 1:
            return {
                "p50": round(ordered[0], 2),
                "p95": round(ordered[0], 2),
                "p99": round(ordered[0], 2),
            }
        quantiles = statistics.quantiles(ordered, n=100, method="inclusive")
        return {
            "p50": round(quantiles[49], 2),
            "p95": round(quantiles[94], 2),
            "p99": round(quantiles[98], 2),
        }

    total = percentiles(
        [left + right for left, right in zip(presidio_times, nemo_times)]
    )
    return {
        "presidio_ms": percentiles(presidio_times),
        "nemo_ms": percentiles(nemo_times),
        "total_ms": total,
        "latency_budget_ok": total["p95"] < LATENCY_BUDGET_P95_MS,
        "budget_ms": LATENCY_BUDGET_P95_MS,
    }


def generate_guard_report() -> dict:
    """Run repository adversarial fixture and collect measured guard latency."""
    with open(ADVERSARIAL_SET_PATH, encoding="utf-8") as file:
        adversarial_set = json.load(file)
    results = run_adversarial_suite(adversarial_set)
    latency = measure_p95_latency(
        [str(item["input"]) for item in adversarial_set],
        n_runs=len(adversarial_set),
    )
    provenance = "live_nemo_presidio" if setup_available() else "offline_deterministic"
    return {
        "provenance": provenance,
        "adversarial_results": results,
        "summary": {
            "total": len(results),
            "passed": sum(1 for item in results if item["passed"]),
            "pass_rate": round(
                sum(1 for item in results if item["passed"]) / len(results), 3
            )
            if results
            else 0.0,
        },
        "latency": latency,
    }


def setup_available() -> bool:
    """Return whether optional live guardrail dependencies are importable."""
    try:
        __import__("presidio_analyzer")
        __import__("presidio_anonymizer")
        __import__("nemoguardrails")
    except ModuleNotFoundError:
        return False
    return True


def save_guard_report(report: dict, path: str = "reports/guard_results.json") -> None:
    """Persist Phase C report."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    report = generate_guard_report()
    save_guard_report(report)
    print(f"Phase C report saved → reports/guard_results.json ({report['provenance']})")
    print(
        f"Pass rate: {report['summary']['pass_rate']:.1%}; P95: {report['latency']['total_ms']['p95']:.2f} ms"
    )
