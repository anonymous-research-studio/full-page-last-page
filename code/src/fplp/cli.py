"""Single entry point: `fplp <command> [options]`. Each command's `--help` lists its options."""

from __future__ import annotations

import importlib
import sys

from fplp import __version__

COMMANDS = {
    "run": ("fplp.run", "run every condition in a config against each model"),
    "score": ("fplp.metrics", "score episode logs into one CSV row per episode"),
    "show": ("fplp.show", "print episode transcripts for qualitative review"),
    "cost": ("fplp.cost", "token use and cost per model; projects a planned run's cost"),
    "health": ("fplp.health", "protocol health of a run, cell by cell (no outcome rates)"),
    "rates": ("fplp.analysis.rates", "per-cell rates with bootstrap 95% CIs"),
    "go-no-go": ("fplp.analysis.go_no_go", "apply the pilot decision rules"),
    "hypotheses": ("fplp.analysis.hypotheses", "pre-registered tests of H1 to H5, per model"),
    "model": ("fplp.analysis.model", "logistic regression of fetching on signal form"),
    "figure": ("fplp.analysis.figure", "headline figure: fetch when needed vs. past a last page"),
    "tables": ("fplp.analysis.tables", "the paper's results tables (LaTeX rows) and figure"),
    "robustness": ("fplp.analysis.robustness", "amendment 2's exploratory checks (wording, total name)"),
    "reference": ("fplp.analysis.reference", "a model's fetch rates beside simple reference agents"),
    "multiplicity": ("fplp.analysis.multiplicity", "one correction across all main contrasts (sensitivity)"),
    "disclosure": ("fplp.analysis.disclosure", "sample replies for labeling; check the disclosure flag"),
    "stamp": ("fplp.provenance", "record the commit and input checksums beside a generated output"),
    "simulate": ("fplp.analysis.simulate", "simulate scored episodes with known effects"),
    "power": ("fplp.analysis.power", "power of the pilot decision rules by items per cell"),
}


def usage() -> str:
    width = max(map(len, COMMANDS))
    lines = [f"usage: fplp <command> [options]   (fplp {__version__})", "", "commands:"]
    lines += [f"  {name:<{width}}  {desc}" for name, (_, desc) in COMMANDS.items()]
    lines += ["", "Run `fplp <command> --help` for a command's options."]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(usage())
        return
    if argv[0] in ("-V", "--version"):
        print(__version__)
        return
    command, rest = argv[0], argv[1:]
    if command not in COMMANDS:
        print(f"fplp: unknown command {command!r}\n\n{usage()}", file=sys.stderr)
        raise SystemExit(2)
    sys.stdout.reconfigure(line_buffering=True)  # progress shows up promptly in logs and background runs
    sys.argv[0] = f"fplp {command}"  # so each command's argparse usage line reads "fplp <command>"
    importlib.import_module(COMMANDS[command][0]).main(rest)


if __name__ == "__main__":
    main()
