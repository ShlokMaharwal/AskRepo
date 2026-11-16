"""Metrics on relevant path/symbol targets, with fixed-window overlap support."""

from statistics import mean


def overlaps(chunk: dict, relevant: dict) -> bool:
    if chunk["path"] != relevant["path"]:
        return False
    if not relevant.get("symbol"):
        return True
    return any(
        chunk["start_line"] <= end and chunk["end_line"] >= start
        for start, end in relevant["ranges"]
    )


def recall_at_k(ranked: list[dict], relevant: list[dict], k: int) -> float:
    if not relevant:
        raise ValueError("A question needs at least one relevant path/symbol")
    return sum(any(overlaps(chunk, target) for chunk in ranked[:k]) for target in relevant) / len(
        relevant
    )


def reciprocal_rank(ranked: list[dict], relevant: list[dict]) -> float:
    for rank, chunk in enumerate(ranked, 1):
        if any(overlaps(chunk, target) for target in relevant):
            return 1 / rank
    return 0.0


def measure(ranked: list[dict], relevant: list[dict], latency_ms: float) -> dict:
    return {
        "recall@1": recall_at_k(ranked, relevant, 1),
        "recall@5": recall_at_k(ranked, relevant, 5),
        "recall@10": recall_at_k(ranked, relevant, 10),
        "mrr": reciprocal_rank(ranked[:10], relevant),
        "hit_rate@10": float(
            any(any(overlaps(chunk, target) for target in relevant) for chunk in ranked[:10])
        ),
        "latency_ms": latency_ms,
    }


def aggregate(rows: list[dict]) -> dict:
    if not rows:
        raise ValueError("Cannot aggregate an empty evaluation")
    return {key: mean(row[key] for row in rows) for key in rows[0]}
