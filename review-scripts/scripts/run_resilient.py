"""Run one model's `fplp run` to completion across interruptions, under a total spending cap.

Restarts the run after a crash, a kill or ten failures in a row (an outage); stops for good on an
account error, at the cutoff time, at the cap, or after too many restarts. A cost-drift stop (one
attempt's episodes averaging over 1.5x the estimate it planned with) restarts the run too when
--estimate is given and all of the model's recorded episodes average within 1.5x of that approved
estimate, since a small sample drifts by chance; otherwise it stops for good and needs a fresh
approval. After a clean finish it reruns once if failed episodes are left to retry. Every
restart gets only the cap that is left: spend is the larger of the local ledger and, for models
billed through OpenRouter, the key's usage from GET /api/v1/key, since a hard kill loses ledger
entries. The machine is kept awake (caffeinate -ims) while this script runs, and the episode log is
copied to a backup folder at a fixed interval. Changes no code and no config; the harness's own
resume logic decides which episodes run.

Usage (from the repository root, after the run and its cap are approved):
  nohup .venv/bin/python scripts/run_resilient.py --run main --model mistral-medium-3-5 --cap 85 \
      --estimate 0.0123 --cutoff 2026-10-25T17:00:00-04:00 --backup-dir "<backup-dir>" \
      --log ../run-logs/mistral-main.log > ../run-logs/mistral-main.nohup 2>&1 &
Add --check to print the plan (key status, remaining cap, command) without starting anything.
--estimate is the approved cost per episode, the "est. $/episode" of `fplp run <config> --dry-run`.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

LEDGER = Path("data/spend-ledger.jsonl")
MAX_ATTEMPTS = 3          # as in fplp.run: an episode that failed this often is not retried
POLL = 15                 # seconds between checks while a run is going
RESTART_DELAY = 60        # seconds before restarting after a crash or an outage
GRACE = 600               # seconds a run gets to finish its running episodes after the cutoff signal


def log(msg: str) -> None:
    print(f"{datetime.now().astimezone().isoformat(timespec='seconds')}  {msg}", flush=True)


def env_value(name: str, env_file: Path) -> str | None:
    if os.environ.get(name):
        return os.environ[name]
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def key_status(key: str) -> dict | None:
    """OpenRouter key usage and limit; None if unreachable (for example during an outage)."""
    req = urllib.request.Request("https://openrouter.ai/api/v1/key", headers={"Authorization": f"Bearer {key}"})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=20).read())["data"]
    except Exception as e:  # noqa: BLE001 - any failure means "unknown", handled by the caller
        log(f"key status unavailable: {e!r}")
        return None


def ledger_entries(run: str, model: str, since: datetime) -> list[dict]:
    """Ledger entries for this run and model written at or after `since` (compared as times: the
    ledger stamps UTC, this script local time)."""
    if not LEDGER.exists():
        return []
    out = []
    for line in LEDGER.read_text().splitlines():
        try:
            e = json.loads(line)
            at = datetime.fromisoformat(e["at"])
        except (json.JSONDecodeError, KeyError, ValueError):
            continue
        if e.get("run_config") == run and e.get("model") == model and at >= since:
            out.append(e)
    return out


def retryable_failures(err_path: Path) -> int:
    """Episodes in the errors log with fewer than MAX_ATTEMPTS non-fatal attempts."""
    if not err_path.exists():
        return 0
    counts: dict[str, int] = {}
    for line in err_path.read_text().splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not e.get("fatal"):
            counts[e["episode_id"]] = counts.get(e["episode_id"], 0) + 1
    return sum(n < MAX_ATTEMPTS for n in counts.values())


def records(path: Path) -> int:
    if not path.exists():
        return 0
    n = 0
    for line in path.read_text().splitlines():
        try:
            json.loads(line)
            n += 1
        except json.JSONDecodeError:
            continue
    return n


def mean_cost(path: Path, model_cfg: dict) -> tuple[int, float]:
    """Episodes recorded in the run's output and their mean cost, priced as the harness prices them;
    a repeated episode id counts once, as in scoring."""
    from fplp.cost import record_cost  # read-only use of the harness's own pricing

    if not path.exists():
        return 0, 0.0
    seen: set[str] = set()
    total = 0.0
    for line in path.read_text().splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec["episode_id"] in seen:
            continue
        seen.add(rec["episode_id"])
        total += record_cost(model_cfg, rec) or 0.0
    return len(seen), (total / len(seen) if seen else 0.0)


def backup(files: list[Path], dest: Path) -> None:
    """Copy each file to dest as <name>, keeping the previous copy as <name>.prev; atomic per file."""
    dest.mkdir(parents=True, exist_ok=True)
    for f in files:
        if not f.exists():
            continue
        target = dest / f.name
        if target.exists():
            shutil.copy2(target, dest / f"{f.name}.prev")
        tmp = dest / f".{f.name}.tmp"
        shutil.copy2(f, tmp)
        os.replace(tmp, target)
    log(f"backup written to {dest}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--run", required=True, help="run config name in configs/runs, e.g. main")
    p.add_argument("--model", required=True)
    p.add_argument("--cap", type=float, required=True, help="total approved spend in USD across all restarts")
    p.add_argument("--cutoff", required=True, help="ISO time after which nothing new starts, e.g. 2026-10-25T17:00:00-04:00")
    p.add_argument("--estimate", type=float,
                   help="approved USD per episode; a cost-drift stop restarts while all episodes average within 1.5x of it")
    p.add_argument("--max-restarts", type=int, default=8)
    p.add_argument("--min-remaining", type=float, default=0.50, help="stop when less than this is left of the cap")
    p.add_argument("--backup-dir", type=Path)
    p.add_argument("--backup-every", type=int, default=1800, help="seconds")
    p.add_argument("--log", type=Path, help="also append this script's messages to this file")
    p.add_argument("--env-file", type=Path, default=Path(".env"))
    p.add_argument("--config", type=Path, help="run config path (default: configs/runs/<run>.yaml)")
    p.add_argument("--out-dir", type=Path, default=Path("data/raw"), help="as fplp run --out-dir (tests only)")
    p.add_argument("--restart-delay", type=int, default=RESTART_DELAY, help="seconds (tests only)")
    p.add_argument("--poll", type=int, default=POLL, help="seconds between checks while a run is going (tests only)")
    p.add_argument("--check", action="store_true", help="print the plan and exit without running")
    args = p.parse_args()
    global LEDGER
    LEDGER = args.out_dir.parent / LEDGER.name  # where fplp run writes its ledger for this --out-dir

    if args.log:
        args.log.parent.mkdir(parents=True, exist_ok=True)
        sys.stdout = open(args.log, "a", buffering=1)  # noqa: SIM115 - kept open for the whole run
        sys.stderr = sys.stdout
    cutoff = datetime.fromisoformat(args.cutoff)
    config = args.config or Path("configs/runs") / f"{args.run}.yaml"
    out_path = args.out_dir / args.run / f"{args.model}.jsonl"
    err_path = out_path.with_name(f"{args.model}.errors.jsonl")
    if not config.exists():
        sys.exit(f"no run config {config}")
    from fplp.config import load_models  # read-only use of the harness's own model registry
    from fplp.run import COST_DRIFT
    model_cfg = load_models("configs/models.yaml").get(args.model)
    if model_cfg is None:
        sys.exit(f"model {args.model} not in configs/models.yaml")
    via_openrouter = "openrouter.ai" in (model_cfg.get("base_url") or "")
    key = env_value(model_cfg.get("api_key_env", "OPENROUTER_API_KEY"), args.env_file) if via_openrouter else None
    start_iso = datetime.now().astimezone()

    base = None
    if via_openrouter:
        status = key_status(key) if key else None
        if not status:
            sys.exit("cannot read the OpenRouter key status; nothing started")
        base = status["usage"]
        remaining_key = status.get("limit_remaining")
        log(f"OpenRouter key: limit {status.get('limit')}, used {base:.4f}, remaining {remaining_key}")
        if remaining_key is not None and remaining_key < args.cap:
            msg = (f"the key's remaining limit (${remaining_key:.2f}) is below the cap (${args.cap:.2f}); "
                   "raise the key limit or lower the cap")
            if args.check:
                log("CHECK: " + msg)
            else:
                sys.exit(msg + "; nothing started")
    else:
        log("model not billed through OpenRouter: spend comes from the local ledger only (a hard kill loses entries)")

    def spent() -> float | None:
        ledger = sum(e.get("budget_spent", 0.0) for e in ledger_entries(args.run, args.model, start_iso))
        if not via_openrouter:
            return ledger
        status = key_status(key)
        if status is None:
            return None
        return max(ledger, status["usage"] - base)

    cmd_base = [".venv/bin/fplp", "run", str(config), "--model", args.model, "--yes"]
    if args.out_dir != Path("data/raw"):
        cmd_base += ["--out-dir", str(args.out_dir)]
    log(f"plan: {args.run}/{args.model}, cap ${args.cap:.2f}, cutoff {cutoff.isoformat()}, "
        f"{records(out_path)} records so far, backups to {args.backup_dir or 'none'}, "
        f"approved estimate {f'${args.estimate:.4f}/episode' if args.estimate else 'none (a cost-drift stop is final)'}")
    if args.check:
        log("CHECK: would run " + " ".join(cmd_base + ["--max-cost", f"{args.cap:.2f}"]))
        return

    awake = subprocess.Popen(["caffeinate", "-ims", "-w", str(os.getpid())])  # ends with this script
    restarts, retry_pass_done = 0, False
    last_backup = time.monotonic()
    files = [out_path, err_path, LEDGER] + ([args.log] if args.log else [])
    dest = args.backup_dir / f"{args.run}-{args.model}" if args.backup_dir else None
    reason = "unknown"
    try:
        while True:
            if datetime.now().astimezone() >= cutoff:
                reason = "cutoff reached"
                break
            s = spent()
            while s is None:  # do not start blind during an outage
                time.sleep(args.restart_delay)
                if datetime.now().astimezone() >= cutoff:
                    break
                s = spent()
            if s is None:
                reason = "cutoff reached during an outage"
                break
            left = args.cap - s
            if left < args.min_remaining:
                reason = f"cap reached (spent ${s:.2f} of ${args.cap:.2f})"
                break
            started = datetime.now().astimezone()
            log(f"start (restart {restarts}): {records(out_path)} records, spent ${s:.4f}, passing --max-cost {left:.2f}")
            attempt_log = (args.log.parent if args.log else Path(".")) / f"{args.run}-{args.model}-attempt{restarts}.log"
            with open(attempt_log, "a") as fh:
                # A command started in the background inherits SIGINT as ignored, and Python keeps it so;
                # restore the default in the run, or the cutoff's SIGINT would not stop it.
                child = subprocess.Popen(cmd_base + ["--max-cost", f"{left:.2f}"], stdout=fh, stderr=subprocess.STDOUT,
                                         preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_DFL))
                signalled = False
                while (rc := child.poll()) is None:
                    time.sleep(args.poll)
                    if dest and time.monotonic() - last_backup >= args.backup_every:
                        backup(files, dest)
                        last_backup = time.monotonic()
                    if not signalled and datetime.now().astimezone() >= cutoff:
                        log("cutoff: sending SIGINT so running episodes finish and are kept")
                        child.send_signal(signal.SIGINT)
                        signalled, deadline = True, time.monotonic() + GRACE
                    if signalled and time.monotonic() > deadline:
                        log("cutoff grace period over: killing the run")
                        child.kill()
            entries = ledger_entries(args.run, args.model, started)
            last = entries[-1] if entries else {}
            log(f"run exited with code {rc}; {records(out_path)} records; ledger: "
                f"{ {k: last.get(k) for k in ('episodes', 'failed', 'fatal', 'failure_streak', 'cost_drift', 'interrupted')} if last else 'no entry (hard kill or crash)'}")
            if rc == 0:
                if retryable_failures(err_path) and not retry_pass_done:
                    retry_pass_done = True
                    restarts += 1
                    log(f"{retryable_failures(err_path)} failed episode(s) left to retry: one more pass")
                    continue
                reason = "finished"
                break
            if rc == 130 or signalled:
                reason = "cutoff reached" if signalled else "interrupted (Ctrl-C or SIGINT)"
                break
            if last.get("fatal"):
                reason = f"account error: {last['fatal']}; fix the account, then restart this script"
                break
            if last.get("cost_drift"):
                n, mean = mean_cost(out_path, model_cfg)
                if not (args.estimate and n and mean <= COST_DRIFT * args.estimate):
                    overall = f"; all {n} episodes average ${mean:.4f}" if n else ""
                    reason = (f"cost drift: episodes cost more than {COST_DRIFT}x the estimate{overall}"
                              f"{f' (approved ${args.estimate:.4f})' if args.estimate else ''}; needs a fresh approval")
                    break
                log(f"cost drift in one attempt, but all {n} episodes so far average ${mean:.4f}, "
                    f"within {COST_DRIFT}x the approved ${args.estimate:.4f}: treated as chance")
            restarts += 1
            if restarts > args.max_restarts:
                reason = f"gave up after {args.max_restarts} restarts"
                break
            why = ("cost drift on a small sample" if last.get("cost_drift")
                   else "ten failures in a row" if last.get("failure_streak") else "crash or kill")
            log(f"{why}: restarting in {args.restart_delay} s")
            time.sleep(args.restart_delay)
    finally:
        if dest:
            backup(files, dest)
        s = spent()
        log(f"STOPPED: {reason}. {records(out_path)} records; {retryable_failures(err_path)} retryable failures left; "
            f"spent about ${s if s is not None else float('nan'):.2f} since this script started")
        awake.terminate()


if __name__ == "__main__":
    main()
