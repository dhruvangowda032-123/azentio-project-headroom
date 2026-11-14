"""Verify committed deterministic reports reproduce offline without altering them."""

import json
from pathlib import Path

from covenants.evaluation import evaluate
from covenants.providers import ReplayProvider

ROOT = Path(__file__).resolve().parents[1]


def verify() -> None:
    for name in ("rules", "fake"):
        expected = json.loads((ROOT / "reports" / f"eval_{name}.json").read_text())
        actual = evaluate(ReplayProvider(ROOT / "fixtures/recordings" / name), ROOT)
        for field in ("metrics", "input_tokens", "output_tokens", "mean_latency_ms", "max_latency_ms"):
            assert actual[field] == expected[field], (name, field)
        print(f"{name}: quality metrics and original usage/timing reproduced exactly")


if __name__ == "__main__":
    verify()

