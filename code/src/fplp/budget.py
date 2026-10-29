"""Spending guard for runs that call paid models.

Policy, enforced by `fplp run`:
1. A cost estimate is shown before anything is sent to a paid model.
2. A paid run never starts without a hard cap (`--max-cost`, in USD) and an explicit confirmation:
   a typed "yes" in an interactive terminal, or `--yes` when run non-interactively. `--yes` is
   for use only after the run has been approved by the person paying for it.
3. During the run, no new episode starts if it could push spend past the cap. A failed episode is
   charged for the turns that completed before the failure.
4. An account error (bad or missing key, no credit, unknown model or host) stops the model's run at
   once, without using up the episodes' attempts; so do ten failures in a row.
   Cost drift: if, after 20 episodes, a model's episodes cost more than 1.5 times the estimate on
   average, its run stops. Rerunning shows a new estimate from the run's own episodes for approval.
5. Every paid run is appended to data/spend-ledger.jsonl.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from fplp.cost import episode_cost

# Tokens per episode assumed for a model with no earlier logs: deliberately high, so a first
# estimate errs toward overstating cost.
DEFAULT_TOKENS = (20_000, 2_000)
# Each running episode reserves this multiple of its estimated cost, so parallel episodes cannot
# overrun the cap by much even when an episode costs more than average.
RESERVE_FACTOR = 2.0


def is_paid(model_cfg: dict) -> bool:
    return model_cfg.get("provider") != "scripted" or model_cfg.get("price_in") is not None


# Once a run has this many of its own episodes for a model, its estimate uses them alone: they come
# from the current code and the run's own conditions, unlike older logs.
MIN_OWN_EPISODES = 10


def mean_tokens(model_name: str, raw_root: Path, logs: list[Path] | None = None
                ) -> tuple[float, float, int, float, float] | None:
    """Mean tokens in, out, (count), cache writes and cache reads per episode for a model, over the
    given logs or every log under raw_root. Logs from before prompt caching count no cache tokens, so
    an estimate from them errs high for a model that now caches."""
    total_in = total_out = total_cw = total_cr = n = 0
    for log in logs if logs is not None else raw_root.rglob(f"{model_name}.jsonl"):
        if not log.exists():
            continue
        with log.open() as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                    tin, tout = rec["tokens_in"], rec["tokens_out"]
                    cw, cr = rec.get("cache_write", 0), rec.get("cache_read", 0)
                except (json.JSONDecodeError, KeyError, TypeError):
                    continue  # blank, or truncated by an interrupted write
                total_in += tin
                total_out += tout
                total_cw += cw
                total_cr += cr
                n += 1
    return (total_in / n, total_out / n, n, total_cw / n, total_cr / n) if n else None


@dataclass
class ModelPlan:
    name: str
    episodes: int
    paid: bool
    per_episode: float | None  # estimated USD per episode
    basis: str                 # where the token estimate comes from

    @property
    def estimate(self) -> float:
        return (self.per_episode or 0.0) * self.episodes


def plan_model(model_cfg: dict, episodes: int, raw_root: Path, run_name: str | None = None) -> ModelPlan:
    paid = is_paid(model_cfg)
    if not paid:
        return ModelPlan(model_cfg["name"], episodes, False, 0.0, "free (scripted)")
    own = mean_tokens(model_cfg["name"], raw_root, [raw_root / run_name / f"{model_cfg['name']}.jsonl"]) \
        if run_name else None
    observed = own if own and own[2] >= MIN_OWN_EPISODES else mean_tokens(model_cfg["name"], raw_root)
    if observed:
        tin, tout, n, cw, cr = observed
        basis = f"mean of {n} episodes of this run" if observed is own else f"mean of {n} logged episodes"
        if model_cfg.get("prompt_cache") and not (cw or cr):
            basis += " (logged without caching: likely high)"
    else:
        (tin, tout), cw, cr = DEFAULT_TOKENS, 0, 0
        basis = "no logs yet: high default"
    return ModelPlan(model_cfg["name"], episodes, True, episode_cost(model_cfg, tin, tout, cw, cr), basis)


def format_plan(plans: list[ModelPlan], cap: float | None) -> str:
    lines = [f"{'model':<22}{'episodes':>9}{'est. $/episode':>16}{'est. total':>12}  basis"]
    for p in plans:
        per = "free" if not p.paid else (f"{p.per_episode:.4f}" if p.per_episode is not None else "no price")
        total = "-" if not p.paid else (f"${p.estimate:,.2f}" if p.per_episode is not None else "?")
        lines.append(f"{p.name:<22}{p.episodes:>9}{per:>16}{total:>12}  {p.basis}")
    paid_total = sum(p.estimate for p in plans if p.paid)
    lines.append(f"estimated spend: ${paid_total:,.2f}" + (f"   hard cap: ${cap:,.2f}" if cap is not None else ""))
    return "\n".join(lines)


class Budget:
    """Thread-safe spend tracker with reservations, so parallel episodes respect a hard cap."""

    def __init__(self, cap: float | None):
        self.cap = cap
        self.spent = 0.0
        self.reserved = 0.0
        self._lock = threading.Lock()

    def reserve(self, amount: float) -> bool:
        with self._lock:
            if self.cap is not None and self.spent + self.reserved + amount > self.cap:
                return False
            self.reserved += amount
            return True

    def settle(self, reserved: float, actual: float) -> None:
        with self._lock:
            self.reserved -= reserved
            self.spent += actual


def record_spend(ledger: Path, entry: dict) -> None:
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a") as fh:
        fh.write(json.dumps({"at": datetime.now(UTC).isoformat(), **entry}) + "\n")
