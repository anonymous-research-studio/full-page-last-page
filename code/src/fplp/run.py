"""Run every condition in a config against each model.

Writes one JSON line per episode to data/raw/<config name>/<model>.jsonl. Reruns skip
episodes already written, so an interrupted run resumes. Failed episodes go to
<model>.errors.jsonl and are retried on later runs, up to MAX_ATTEMPTS attempts in all; after that
they are reported as missing. Each episode stores the code version and settings that produced it.

Runs that call paid models are guarded (see fplp.budget): the cost estimate is printed first,
and the run refuses to start without a hard cap (--max-cost USD) and an explicit confirmation.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import threading
import time
import traceback
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

from fplp.agents import make_client
from fplp.budget import RESERVE_FACTOR, Budget, ModelPlan, format_plan, plan_model, record_spend
from fplp.conditions import DEFAULT_MAX_TOOL_CALLS, Condition, build_conditions, config_key, planned
from fplp.config import ConfigError, load_env_file, load_models, load_run_config
from fplp.cost import episode_cost, record_cost
from fplp.episode import run_episode
from fplp.provenance import provenance
from fplp.tasks.specs import build_episode

LEDGER = Path("data/spend-ledger.jsonl")
MAX_ATTEMPTS = 3  # an episode that fails this many times (provider errors) is reported as missing
MAX_CONSECUTIVE_FAILURES = 10  # this many failures in a row stop a model's run (an outage, not bad luck)
COST_DRIFT = 1.5           # stop a paid model's run when its mean episode cost exceeds this multiple of the estimate,
DRIFT_MIN_EPISODES = 20    # judged once this many of its episodes have finished in the current run


def fatal_reason(exc: BaseException) -> str | None:
    """An account-level error that every further request would hit too: it stops the model's run and
    does not count as an attempt for the episode. None for ordinary, retryable failures."""
    status = getattr(exc, "status_code", None)
    text = str(exc).lower()
    if status in (401, 403):
        return "authentication or permission"
    if status == 402 or "credit balance" in text or "insufficient credits" in text:
        return "out of credit"
    if status == 404:
        return "model or pinned host not found"
    if isinstance(exc, TypeError) and ("api_key" in text or "authentication" in text):
        return "no credentials"
    return None


def key_env(model_cfg: dict) -> str | None:
    """The environment variable holding the model's API key; None when no key is needed."""
    if model_cfg.get("provider") == "anthropic":
        return "ANTHROPIC_API_KEY"
    if model_cfg.get("provider") == "openai_compatible":
        base = model_cfg.get("base_url") or ""
        return None if ("localhost" in base or "127.0.0.1" in base) else model_cfg.get("api_key_env", "OPENAI_API_KEY")
    return None


def _pinned_host(model_cfg: dict) -> str | None:
    order = ((model_cfg.get("extra_body") or {}).get("provider") or {}).get("order")
    return order[0].split("/")[0].lower() if order else None


def _end_with_newline(path: Path) -> None:
    """After a hard kill a log can end mid-line; start the next record on a fresh line."""
    if path.exists() and path.stat().st_size:
        with path.open("rb") as fh:
            fh.seek(-1, 2)
            last = fh.read(1)
        if last != b"\n":
            with path.open("a") as fh:
                fh.write("\n")


def _done_ids(path: Path) -> set[str]:
    """Episode ids already written. A truncated last line (an interrupted write) is ignored, so the
    episode simply reruns."""
    if not path.exists():
        return set()
    done = set()
    with path.open() as fh:
        for line in fh:
            try:
                done.add(json.loads(line)["episode_id"])
            except (json.JSONDecodeError, KeyError):
                continue
    return done


def _attempts(err_path: Path) -> Counter:
    """Failed attempts per episode id, from the errors log (one line per failure)."""
    counts: Counter = Counter()
    if err_path.exists():
        with err_path.open() as fh:
            for line in fh:
                try:
                    e = json.loads(line)
                    if not e.get("fatal"):  # account errors are not the episode's attempts
                        counts[e["episode_id"]] += 1
                except (json.JSONDecodeError, KeyError, AttributeError):
                    continue
    return counts


def print_plan(conditions: list[Condition], models: list[dict], max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS) -> None:
    """Episodes per model after each model's replicate cap, then the cells (all replicates)."""
    counts = {m["name"]: len(planned(m, conditions, max_tool_calls)) for m in models}
    for name, n in counts.items():
        print(f"{name}: {n} episodes")
    if models:
        print(f"total: {sum(counts.values())} episodes")
    print(f"{len(conditions)} conditions (every replicate), by cell:")
    cells = Counter((c.arm, c.signal_form.value, c.extent.value, c.task_need.value) for c in conditions)
    for (arm, form, extent, need), n in sorted(cells.items()):
        print(f"  {arm:<14} {form:<17} {extent:<11} {need:<17} {n}")


def pending(model_cfg: dict, conditions: list[Condition], out_dir: Path, max_episodes: int | None,
            seed: int = 0, max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS):
    """Episodes still to run for one model, after resume, its replicate cap and the attempt limit,
    in a seeded random order: if a run stops early (spending cap, interruption), the missing
    episodes are spread across conditions instead of being the last forms and arms in config order.
    Returns (ids done, episodes to run, ids given up after MAX_ATTEMPTS failures)."""
    done = _done_ids(out_dir / f"{model_cfg['name']}.jsonl")
    attempts = _attempts(out_dir / f"{model_cfg['name']}.errors.jsonl")
    todo = [(eid, c) for eid, c in planned(model_cfg, conditions, max_tool_calls) if eid not in done]
    exhausted = {eid for eid, _ in todo if attempts[eid] >= MAX_ATTEMPTS}
    todo = [(eid, c) for eid, c in todo if eid not in exhausted]
    random.Random(f"{seed}:{model_cfg['name']}").shuffle(todo)
    return done, (todo if max_episodes is None else todo[:max_episodes]), exhausted


def confirm_paid_run(plans: list[ModelPlan], args) -> None:
    """Refuse a paid run unless it has a hard cap and an explicit confirmation."""
    paid = [p for p in plans if p.paid and p.episodes]
    if not paid:
        return
    if missing := [p.name for p in paid if p.per_episode is None]:
        sys.exit(f"paid model(s) without prices in the model registry: {missing}; add price_in/price_out first")
    if args.max_cost is None:
        sys.exit("This run calls paid models. Nothing was sent. Set a hard spending cap with --max-cost USD, "
                 "and confirm before running.")
    estimate = sum(p.estimate for p in paid)
    if estimate > args.max_cost:
        print(f"note: the estimate (${estimate:,.2f}) exceeds the cap; the run will stop starting episodes "
              f"before ${args.max_cost:,.2f} and the rest can be run later.")
    if args.yes:
        return
    if sys.stdin.isatty():
        if input(f"Spend up to ${args.max_cost:,.2f} on this run? Type yes to proceed: ").strip().lower() == "yes":
            return
        sys.exit("Not confirmed. Nothing was sent.")
    sys.exit("Not confirmed. Nothing was sent. When running non-interactively, pass --yes only after the "
             "run and its cap have been approved.")


def run_model(model_cfg: dict, todo: list, n_done: int, plan: ModelPlan, budget: Budget,
              cfg: dict, out_dir: Path, args, prov: dict, summary: dict) -> None:
    """Run one model's episodes, updating `summary` as results arrive, so the caller can record spend
    even if the run stops early. On Ctrl-C (or an error while writing) no new episode starts, queued
    ones are cancelled, and episodes already running are waited for and kept, since they are paid for."""
    client = make_client(model_cfg)
    out_path = out_dir / f"{client.name}.jsonl"
    err_path = out_dir / f"{client.name}.errors.jsonl"
    print(f"{client.name}: {n_done} done, {len(todo)} to run")
    max_calls = cfg.get("max_tool_calls", DEFAULT_MAX_TOOL_CALLS)
    attempts = _attempts(err_path)
    reserve = RESERVE_FACTOR * (plan.per_episode or 0.0) if plan.paid else 0.0
    stop = threading.Event()
    streak_hit, drift_hit = threading.Event(), threading.Event()
    in_row = [0]  # consecutive failures, across worker threads
    done = [0, 0.0]  # episodes finished in this run and their cost, for the drift check
    in_row_lock = threading.Lock()

    def work(eid: str, c: Condition) -> dict | None:
        if stop.is_set() or not budget.reserve(reserve):
            return None  # stopping, or the cap is reached: do not start this episode
        try:
            rec = run_episode(client, build_episode(c), max_tool_calls=max_calls)
        except BaseException as e:
            # Charge the turns that completed before the failure (a rejected request is not billed).
            budget.settle(reserve, episode_cost(model_cfg, *getattr(e, "partial_tokens", (0, 0))) or 0.0)
            # Stop here, in the worker, so no further episode starts while the main thread catches up.
            if isinstance(e, Exception) and fatal_reason(e):
                stop.set()
            else:
                with in_row_lock:
                    in_row[0] += 1
                    if in_row[0] >= MAX_CONSECUTIVE_FAILURES:
                        streak_hit.set()
                        stop.set()
            raise
        cost = record_cost(model_cfg, rec) or 0.0
        budget.settle(reserve, cost)
        with in_row_lock:
            in_row[0] = 0
            done[0] += 1
            done[1] += cost
            if (plan.paid and plan.per_episode and done[0] >= DRIFT_MIN_EPISODES
                    and done[1] / done[0] > COST_DRIFT * plan.per_episode):
                drift_hit.set()  # costing well above the estimate: start nothing more
                stop.set()
        rec["episode_id"] = eid
        rec["run_config"] = cfg["name"]
        rec["model_config"] = model_cfg
        rec["config_key"] = config_key(model_cfg, max_calls)
        rec["provenance"] = prov
        rec["attempt"] = attempts[eid] + 1
        rec["finished_at"] = datetime.now(UTC).isoformat()
        return rec

    failed_ids: list[str] = []
    empty = 0
    host = _pinned_host(model_cfg)
    live = model_cfg.get("provider") != "scripted"

    def halt() -> None:
        stop.set()
        for f in futures:
            f.cancel()

    def add_tokens(tokens_in: int, tokens_out: int, cache_write: int = 0, cache_read: int = 0) -> None:
        summary["tokens_in"] += tokens_in
        summary["tokens_out"] += tokens_out
        summary["cache_write"] += cache_write
        summary["cache_read"] += cache_read
        summary["cost"] = episode_cost(model_cfg, summary["tokens_in"], summary["tokens_out"],
                                       summary["cache_write"], summary["cache_read"])

    def handle(fut, out, err) -> None:
        nonlocal empty
        if fut.cancelled():
            summary["skipped"] += 1
            return
        eid, c = futures[fut]
        try:
            rec = fut.result()
        except Exception as e:
            fatal = fatal_reason(e)
            add_tokens(*getattr(e, "partial_tokens", (0, 0)))
            err.write(json.dumps({
                "episode_id": eid,
                "attempt": None if fatal else attempts[eid] + 1,
                "fatal": bool(fatal),
                "at": datetime.now(UTC).isoformat(),
                "condition": c.to_dict(),
                "error": repr(e),
                "traceback": traceback.format_exc(),
            }) + "\n")
            err.flush()
            if fatal:
                summary["fatal"] = fatal
                halt()
                return
            summary["failed"] += 1
            failed_ids.append(eid)
            if streak_hit.is_set():
                summary["failure_streak"] = True
                halt()
            return
        if rec is None:
            summary["skipped"] += 1
            return
        out.write(json.dumps(rec, ensure_ascii=False) + "\n")
        out.flush()
        summary["episodes"] += 1
        add_tokens(rec["tokens_in"], rec["tokens_out"], rec.get("cache_write", 0), rec.get("cache_read", 0))
        empty += rec["empty_reply"]
        if drift_hit.is_set() and not summary["cost_drift"]:
            summary["cost_drift"] = True
            halt()
        if live:
            if host:  # with fallbacks off this should never happen; it would mean silent re-routing
                summary["host_mismatch"] += sum(bool(t.get("served_by")) and not str(t["served_by"]).lower().startswith(host)
                                                for t in rec["turns"])
            summary["no_usage"] += sum(not t["tokens_in"] and not t["tokens_out"] for t in rec["turns"])

    started, every = time.monotonic(), max(10, len(todo) // 10)
    _end_with_newline(out_path)
    _end_with_newline(err_path)
    with out_path.open("a") as out, err_path.open("a") as err:
        pool = ThreadPoolExecutor(max_workers=args.workers)
        futures = {pool.submit(work, eid, c): (eid, c) for eid, c in todo}
        handled: set = set()
        try:
            for finished, fut in enumerate(as_completed(futures), 1):
                handle(fut, out, err)
                handled.add(fut)
                if finished % every == 0 and finished < len(todo):
                    minutes = (time.monotonic() - started) / 60
                    print(f"{client.name}: {finished}/{len(todo)} ({summary['failed']} failed, {empty} empty) "
                          f"{minutes:.1f} min")
        except BaseException as exc:
            stop.set()
            cancelled = sum(f.cancel() for f in futures)
            summary["skipped"] += cancelled
            if not isinstance(exc, KeyboardInterrupt):
                raise
            summary["interrupted"] = True
            running = [f for f in futures if f not in handled and not f.cancelled()]
            print(f"\n{client.name}: INTERRUPTED. {cancelled} queued episode(s) cancelled; waiting for "
                  f"{len(running)} running episode(s) so their paid results are kept (Ctrl-C again to abandon them)")
            try:
                for f in running:
                    handle(f, out, err)
            except KeyboardInterrupt:
                print(f"{client.name}: abandoned the running episodes; they may still be billed")
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
    _drop_resolved_errors(err_path, _done_ids(out_path))
    cost = summary["cost"]
    spend = f", about ${cost:.2f}" if cost is not None else ""
    print(f"{client.name}: {'stopped' if summary['interrupted'] else 'finished'}, {summary['failed']} failed; "
          f"{summary['tokens_in']:,} tokens in ({summary['cache_read']:,} read from the prompt cache), "
          f"{summary['tokens_out']:,} out{spend}")
    if summary["fatal"]:
        print(f"{client.name}: STOPPED: account error ({summary['fatal']}). No further requests were sent and no "
              f"episode's attempts were used. Fix the account (key, credit), then rerun the same command.")
    elif summary["cost_drift"]:
        per = (summary["cost"] or 0.0) / max(1, summary["episodes"])
        print(f"{client.name}: STOPPED: episodes cost ${per:.4f} on average, more than {COST_DRIFT}x the "
              f"${plan.per_episode:.4f} estimate. Nothing more was started. Rerunning shows a new estimate "
              "based on this run's own episodes, for approval.")
    elif summary["failure_streak"]:
        print(f"{client.name}: STOPPED after {MAX_CONSECUTIVE_FAILURES} failures in a row (see {err_path.name}); "
              "rerun the same command to retry once the provider recovers")
    if gave_up := sum(attempts[eid] + 1 >= MAX_ATTEMPTS for eid in failed_ids):
        print(f"{client.name}: {gave_up} episode(s) have now failed {MAX_ATTEMPTS} times and will be "
              "reported as missing, not retried")
    if retry := len(failed_ids) - gave_up:
        print(f"{client.name}: {retry} episode(s) failed; rerun the same command to retry them "
              f"(up to {MAX_ATTEMPTS} attempts in all)")
    if summary["host_mismatch"]:
        print(f"{client.name}: WARNING {summary['host_mismatch']} turn(s) were served by a host other than the "
              f"pinned {host!r}; check the provider settings before trusting this run")
    if summary["no_usage"]:
        print(f"{client.name}: WARNING {summary['no_usage']} turn(s) reported no token usage; cost is undercounted")
    if summary["skipped"] and not (summary["interrupted"] or summary["fatal"] or summary["failure_streak"]
                                   or summary["cost_drift"]):
        print(f"{client.name}: STOPPED at the spending cap; {summary['skipped']} episode(s) not started "
              "(rerun with a higher approved cap to continue)")
    if empty:
        print(f"{client.name}: WARNING {empty} episode(s) ended with an empty reply (no text, no tool call); "
              "check the host's tool-call parsing with `fplp show --empty` before trusting this run")


def _drop_resolved_errors(err_path: Path, done: set[str]) -> None:
    """Keep only errors for episodes that still have no result (every attempt, so the attempt
    count survives); remove the file if none remain."""
    if not err_path.exists():
        return
    open_errors = []
    with err_path.open() as fh:
        for line in fh:
            try:
                if json.loads(line)["episode_id"] not in done:
                    open_errors.append(line if line.endswith("\n") else line + "\n")
            except (json.JSONDecodeError, KeyError):
                continue  # a truncated line from an interrupted write
    if open_errors:
        err_path.write_text("".join(open_errors))
    else:
        err_path.unlink()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("config", help="run config, e.g. configs/runs/pilot.yaml")
    parser.add_argument("--dry-run", action="store_true", help="print the episode plan and cost estimate, then exit")
    parser.add_argument("--models-file", default="configs/models.yaml")
    parser.add_argument("--model", action="append", help="run only this model (repeatable)")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--max-episodes", type=int, help="cap new episodes per model (smoke tests)")
    parser.add_argument("--max-cost", type=float, help="hard spending cap in USD; required for paid models")
    parser.add_argument("--yes", action="store_true",
                        help="confirm a paid run non-interactively; use only after the run and cap are approved")
    parser.add_argument("--out-dir", default="data/raw")
    parser.add_argument("--env-file", default=".env", help="API keys as KEY=VALUE lines (default: .env)")
    args = parser.parse_args(argv)
    load_env_file(args.env_file)

    try:
        cfg = load_run_config(args.config, require_items=True)
    except ConfigError as e:
        sys.exit(str(e))
    conditions = build_conditions(cfg)
    names = args.model or cfg.get("models") or []
    if not names:
        if args.dry_run:
            print_plan(conditions, [])
            return
        sys.exit("no models: list them under `models` in the config or pass --model")
    registry = load_models(args.models_file)
    if missing := [n for n in names if n not in registry]:
        sys.exit(f"models not defined in {args.models_file}: {missing}")

    out_dir = Path(args.out_dir) / cfg["name"]
    max_calls = cfg.get("max_tool_calls", DEFAULT_MAX_TOOL_CALLS)
    work = {n: pending(registry[n], conditions, out_dir, args.max_episodes, cfg.get("seed", 0), max_calls)
            for n in names}
    for n in names:
        if exhausted := work[n][2]:
            print(f"{n}: {len(exhausted)} episode(s) failed {MAX_ATTEMPTS} times; reported as missing, not retried")
    plans = {n: plan_model(registry[n], len(work[n][1]), Path(args.out_dir), cfg["name"]) for n in names}
    if args.dry_run:
        print_plan(conditions, [registry[n] for n in names], max_calls)
        print()
        print(format_plan(list(plans.values()), args.max_cost))
        return

    print(format_plan(list(plans.values()), args.max_cost))
    prov = provenance()
    if prov["git_dirty"]:
        print("WARNING: the working tree has uncommitted changes; episodes are stored with git_dirty=true "
              "and cannot be traced to a commit")
    confirm_paid_run(list(plans.values()), args)
    # A missing key must stop the run before anything is sent: the Anthropic SDK would otherwise fall
    # back to a stored login, which may bill a different account.
    if missing := [f"{n} needs {env}" for n in names if plans[n].paid and plans[n].episodes
                   and (env := key_env(registry[n])) and not os.environ.get(env)]:
        sys.exit(f"API key not set: {'; '.join(missing)} (in .env or the environment). Nothing was sent.")
    any_paid = any(p.paid and p.episodes for p in plans.values())
    budget = Budget(args.max_cost if any_paid else None)
    out_dir.mkdir(parents=True, exist_ok=True)
    interrupted = stopped = False
    for name in names:
        done, todo, _ = work[name]
        summary = {"model": name, "episodes": 0, "failed": 0, "skipped": 0, "tokens_in": 0, "tokens_out": 0,
                   "cache_write": 0, "cache_read": 0, "cost": 0.0, "interrupted": False, "fatal": None, "failure_streak": False, "cost_drift": False,
                   "host_mismatch": 0, "no_usage": 0}
        try:
            run_model(registry[name], todo, len(done), plans[name], budget, cfg, out_dir, args, prov, summary)
        finally:  # the ledger is written even if the run stops on an error or an interrupt
            if plans[name].paid and (summary["episodes"] or summary["failed"] or summary["fatal"]):
                record_spend(Path(args.out_dir).parent / LEDGER.name, {
                    "run_config": cfg["name"], "cap": args.max_cost, "estimate": plans[name].estimate,
                    "budget_spent": round(budget.spent, 4), **summary})
        if summary["interrupted"]:
            interrupted = True
            break
        stopped = stopped or bool(summary["fatal"] or summary["failure_streak"] or summary["cost_drift"])
    if any_paid:
        print(f"total spend this run: about ${budget.spent:,.2f} of a ${args.max_cost:,.2f} cap")
    if interrupted:
        sys.exit(130)
    if stopped:
        sys.exit(1)


if __name__ == "__main__":
    main()
