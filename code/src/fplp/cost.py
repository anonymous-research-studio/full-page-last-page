"""Token use and cost per model from episode logs, with a projection for a planned run.

Prices come from `price_in` and `price_out` (USD per million tokens) in configs/models.yaml, and for a
model with `prompt_cache`, `price_cache_write` and `price_cache_read` for the input tokens written to
and read from the provider's prompt cache. `tokens_in` counts every input token, cached or not.

Usage:
  uv run fplp cost data/raw/check-wide
  uv run fplp cost data/raw/check-wide --project configs/runs/main.yaml
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from fplp.conditions import build_conditions
from fplp.config import load_models, load_run_config

# Without configured cache prices, cache writes are charged at Anthropic's 5-minute write premium and
# cache reads at the full input price, so a missing price can only overstate spend.
CACHE_WRITE_DEFAULT = 1.25


def episode_cost(model_cfg: dict, tokens_in: float, tokens_out: float, cache_write: float = 0,
                 cache_read: float = 0) -> float | None:
    """USD for the given token counts; cache_write and cache_read are the parts of tokens_in that
    were written to and read from the prompt cache."""
    if model_cfg.get("price_in") is None or model_cfg.get("price_out") is None:
        return None
    price_in = model_cfg["price_in"]
    write = model_cfg.get("price_cache_write", CACHE_WRITE_DEFAULT * price_in)
    read = model_cfg.get("price_cache_read", price_in)
    return ((tokens_in - cache_write - cache_read) * price_in + cache_write * write + cache_read * read
            + tokens_out * model_cfg["price_out"]) / 1e6


def record_cost(model_cfg: dict, rec: dict) -> float | None:
    """Cost of one episode record (older records have no cache fields)."""
    return episode_cost(model_cfg, rec["tokens_in"], rec["tokens_out"], rec.get("cache_write", 0),
                        rec.get("cache_read", 0))


def _logs(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for p in map(Path, paths):
        files.extend(sorted(f for f in p.glob("*.jsonl") if not f.name.endswith(".errors.jsonl")) if p.is_dir() else [p])
    return files


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("inputs", nargs="+", help="episode .jsonl files or directories of them")
    parser.add_argument("--models-file", default="configs/models.yaml")
    parser.add_argument("--project", help="run config to project cost for, from mean tokens per episode")
    args = parser.parse_args(argv)

    registry = load_models(args.models_file)
    totals: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0, 0, 0])
    for f in _logs(args.inputs):
        with f.open() as fh:
            for line in fh:
                if line.strip():
                    rec = json.loads(line)
                    t = totals[rec["model"]]
                    t[0] += 1
                    t[1] += rec["tokens_in"]
                    t[2] += rec["tokens_out"]
                    t[3] += rec.get("cache_write", 0)
                    t[4] += rec.get("cache_read", 0)

    plan = None
    if args.project:
        cfg = load_run_config(args.project, require_items=True)
        plan = (cfg, build_conditions(cfg))

    print(f"{'model':<22}{'episodes':>9}{'mean in':>10}{'mean out':>10}{'cost':>10}" + ("   projected" if plan else ""))
    for model, (n, tin, tout, cw, cr) in sorted(totals.items()):
        entry = registry.get(model, {})
        cost = episode_cost(entry, tin, tout, cw, cr)
        line = f"{model:<22}{n:>9}{tin / n:>10.0f}{tout / n:>10.0f}" + (f"{cost:>10.2f}" if cost is not None else f"{'n/a':>10}")
        if plan:
            cfg, conditions = plan
            cap = entry.get("replicates")
            planned = sum(1 for c in conditions if cap is None or c.replicate < cap)
            per = episode_cost(entry, tin / n, tout / n, cw / n, cr / n)
            line += f"   {planned} episodes" + (f", about ${per * planned:.0f}" if per is not None else "")
        print(line)


if __name__ == "__main__":
    main()
