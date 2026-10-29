"""Headline figure: follow-up when needed (y) vs. unnecessary fetching when not (x).

One point per signal form, with bootstrap 95% whiskers on both axes. y: needs-all tasks where
more rows exist. x: needs-all tasks on a full page that is truthfully the last one (extent
last_full); if the data have no such cells, page-1-sufficient tasks instead. Top-left means the agent
follows the signal: it fetches when the signal says more exist and stops when it says the page is the
last. A point to the right is not necessarily worse: one extra call to check a full last page can be
a sensible precaution, so the x axis is a cost, not an error rate (amendment 1).

Identity is carried by direct labels on every point. Color and marker shape encode only the
signal family (structured field, natural language, combined, no signal), so the figure stays
readable in grayscale print. Palette: reference slots 1-3 plus neutral gray; the first three
slots validate all-pairs (dataviz validate_palette.js).

Usage:
  uv run fplp figure data/processed/pilot.csv --out results/figures/calibration
  ... --facet-models   # one panel per model, shared axes
"""

from __future__ import annotations

import argparse

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from fplp.analysis.common import MODEL_NAMES, analysis_sample

INK = "#0b0b0b"
INK_MUTED = "#52514e"
GRID = "#e4e3df"
SURFACE = "#fcfcfb"

FAMILY = {
    "has_more": "structured", "next_cursor": "structured", "total_count": "structured",
    "total_matches": "structured", "link_header": "structured", "page_info": "structured",
    "nl_note": "natural language", "nl_note_json": "natural language",
    "placeholder_row": "natural language", "cursor_plus_note": "combined", "none": "no signal",
}
STYLE = {  # color, marker
    "structured": ("#2a78d6", "o"),
    "natural language": ("#eb6834", "s"),
    "combined": ("#1baf7a", "^"),
    "no signal": (INK_MUTED, "D"),
}
LABEL = {
    "has_more": "has_more", "next_cursor": "next_cursor", "total_count": "total_count",
    "total_matches": "total_matches", "link_header": "Link header", "page_info": "pageInfo", "nl_note": "NL note (text)",
    "nl_note_json": "NL note (JSON)", "placeholder_row": "placeholder row",
    "cursor_plus_note": "cursor + note", "none": "no signal",
}


def _boot(x: np.ndarray, rng: np.random.Generator, n_boot: int) -> tuple[float, float, float]:
    if len(x) == 0:
        return np.nan, np.nan, np.nan
    means = rng.choice(x, size=(n_boot, len(x)), replace=True).mean(axis=1)
    return x.mean(), np.quantile(means, 0.025), np.quantile(means, 0.975)


def _masks(d: pd.DataFrame) -> tuple[pd.Series, pd.Series, str]:
    """y: fetch needed. x: a truthful full last page if present, else page-1-sufficient tasks."""
    extent = d["extent"] if "extent" in d else pd.Series("more_full", index=d.index)
    y = (d["task_need"] == "needs_all") & (extent == "more_full")
    last_full = (d["task_need"] == "needs_all") & (extent == "last_full")
    if last_full.any():
        return y, last_full, "Fetched past a full page that was the last one"
    return y, (d["task_need"] == "page1_sufficient") & (extent == "more_full"), "Fetched more when page 1 sufficed"


def points(df: pd.DataFrame, n_boot: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    d = analysis_sample(df)  # the pre-registered exclusions: refusals and empty replies
    d = d[(d["arm"] == "core") & (d["settled_on_page1"] == 0) & (d["own_small_page"] == 0)]  # as in the fetch tests
    ymask, xmask, _ = _masks(d)
    rows = []
    for form in sorted(d["signal_form"].unique()):
        y = d.loc[ymask & (d["signal_form"] == form), "follow_up"].to_numpy(dtype=float)
        x = d.loc[xmask & (d["signal_form"] == form), "follow_up"].to_numpy(dtype=float)
        ym, ylo, yhi = _boot(y, rng, n_boot)
        xm, xlo, xhi = _boot(x, rng, n_boot)
        rows.append({"form": form, "x": xm, "x_lo": xlo, "x_hi": xhi, "y": ym, "y_lo": ylo, "y_hi": yhi})
    return pd.DataFrame(rows)


# Candidate label offsets (points): near the marker first, then farther out with a leader line.
OFFSETS = [(dx * r, dy * r) for r in (1, 2, 3.4, 4.8, 6.5)
           for dx, dy in ((5, -2), (-5, -2), (0, 6), (0, -9), (5, 6), (-5, 6), (5, -9), (-5, -9))]
OFFSETS += [(dx, dy) for dx in (30, 45, 60) for dy in range(-48, 49, 8)]  # a label column beside a cluster
LEADER = 9  # points: a label farther than this from its marker gets a leader line


def _crosses(p1, p2, q1, q2) -> bool:
    """Whether segments p1-p2 and q1-q2 cross."""
    def side(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    return side(q1, q2, p1) * side(q1, q2, p2) < 0 and side(p1, p2, q1) * side(p1, p2, q2) < 0


def _through(segment, box) -> bool:
    """Whether a leader segment runs through a box (sampled along its middle)."""
    (x0, y0), (x1, y1) = segment
    return any(box[0] <= x0 + t * (x1 - x0) <= box[2] and box[1] <= y0 + t * (y1 - y0) <= box[3]
               for t in np.linspace(0.15, 0.85, 15))


def place_labels(ax, pts: pd.DataFrame, n_orders: int = 40, seed: int = 0) -> None:
    """Label every point without collisions (presentation only). A candidate position is scored by its
    overlap with placed labels, other markers and fixed text, by how much of it leaves the plot area
    (outside it, labels collide with tick labels and axis titles), by leader lines that cross each other
    or run through a label or marker, and lightly by distance. Labels are placed greedily in several
    orders (by height, by position, and seeded shuffles) and the order with the lowest total score is
    drawn. A label far from its marker gets a thin leader line."""
    fig = ax.figure
    renderer = fig.canvas.get_renderer()
    px = fig.dpi / 72
    centers = [tuple(ax.transData.transform((p["x"], p["y"]))) for _, p in pts.iterrows()]
    r = 4 * px
    markers = [(cx - r, cy - r, cx + r, cy + r) for cx, cy in centers]
    fixed = [(bb.x0, bb.y0, bb.x1, bb.y1) for bb in (t.get_window_extent(renderer) for t in ax.texts)]
    fb = ax.get_window_extent(renderer)
    frame = (fb.x0, fb.y0, fb.x1, fb.y1)
    labels = [LABEL.get(f, f) for f in pts["form"]]
    sizes = []
    for text in labels:  # measure each label once
        t = ax.text(0, 0, text, fontsize=6)
        bb = t.get_window_extent(renderer)
        sizes.append((bb.width, bb.height))
        t.remove()

    def overlap(a, b) -> float:
        w = min(a[2], b[2]) - max(a[0], b[0])
        h = min(a[3], b[3]) - max(a[1], b[1])
        return w * h if w > 0 and h > 0 else 0.0

    def candidate(i, dx, dy):
        (cx, cy), (w, h) = centers[i], sizes[i]
        x, y = cx + dx * px, cy + dy * px
        x0 = x if dx > 0 else x - w if dx < 0 else x - w / 2
        box = (x0 - 1, y - 1, x0 + w + 1, y + h + 1)
        if abs(dx) <= LEADER and abs(dy) <= LEADER:
            return box, None
        return box, ((cx, cy), (min(max(cx, box[0]), box[2]), min(max(cy, box[1]), box[3])))

    def gap(box, c) -> float:  # distance from a point to a box
        return float(np.hypot(max(box[0] - c[0], 0, c[0] - box[2]), max(box[1] - c[1], 0, c[1] - box[3])))

    def score(i, box, leader, placed, leaders) -> float:
        others = [m for j, m in enumerate(markers) if j != i]
        s = sum(overlap(box, o) for o in placed + others) + 4 * sum(overlap(box, o) for o in fixed)
        if leader is None and any(gap(box, c) < gap(box, centers[i]) + 2 * px
                                  for j, c in enumerate(centers) if j != i):
            s += 250  # a label nearer another point than its own would be read as that point's
        s += 3 * ((box[2] - box[0]) * (box[3] - box[1]) - overlap(box, frame))
        s += 300 * sum(_through(seg, box) for seg in leaders)
        if leader is not None:
            s += 400 * sum(_crosses(*leader, *seg) for seg in leaders)
            s += 300 * sum(_through(leader, b) for b in placed + others)
        return s

    rng = np.random.default_rng(seed)
    orders = [list(np.argsort(-pts["y"].to_numpy(), kind="stable")), list(np.argsort(pts["x"].to_numpy(), kind="stable"))]
    orders += [list(rng.permutation(len(labels))) for _ in range(n_orders)]
    best = None
    for order in orders:
        placed, leaders, total, offsets = list(fixed), [], 0.0, {}
        for i in order:
            s, off, box, leader = min(((score(i, *candidate(i, dx, dy), placed, leaders) + 0.4 * np.hypot(dx, dy) * px,
                                        (dx, dy), *candidate(i, dx, dy)) for dx, dy in OFFSETS), key=lambda c: c[0])
            total += s
            placed.append(box)
            if leader is not None:
                leaders.append(leader)
            offsets[i] = off
        if best is None or total < best[0]:
            best = (total, offsets)
    for i, (dx, dy) in best[1].items():
        p = pts.iloc[i]
        far = abs(dx) > LEADER or abs(dy) > LEADER
        ax.annotate(labels[i], (p["x"], p["y"]), xytext=(dx, dy), textcoords="offset points", fontsize=6, color=INK,
                    ha="left" if dx > 0 else "right" if dx < 0 else "center", va="bottom", zorder=4,
                    arrowprops={"arrowstyle": "-", "color": INK_MUTED, "linewidth": 0.4, "shrinkA": 0, "shrinkB": 3}
                    if far else None)


def ceiling_note(ax, pts: pd.DataFrame) -> None:
    """When every point in a panel sits at 100% on the y axis, say so in the panel: the points then lie
    on the top edge and only their x positions differ."""
    if len(pts) and np.allclose(pts["y"].to_numpy(dtype=float), 1.0):
        ax.text(0.5, 0.45, "Every point is at 100%\non the y axis", transform=ax.transAxes, fontsize=6,
                color=INK_MUTED, ha="center", va="center", style="italic")


def _upper(values: pd.Series) -> float:
    """Axis maximum: the next 25% step above the data, at least 50%, at most 100%."""
    top = np.nanmax(values.to_numpy(dtype=float)) if len(values) else 1.0
    return float(min(1.0, max(0.5, np.ceil((top + 0.02) * 4) / 4)))


def draw(ax, pts: pd.DataFrame, title: str | None = None, xmax: float = 1.0, ymax: float = 1.0) -> None:
    ax.set_facecolor(SURFACE)
    for _, p in pts.iterrows():
        family = FAMILY.get(p["form"], "structured")
        color, marker = STYLE[family]
        ax.errorbar(
            p["x"], p["y"],
            xerr=[[p["x"] - p["x_lo"]], [p["x_hi"] - p["x"]]],
            yerr=[[p["y"] - p["y_lo"]], [p["y_hi"] - p["y"]]],
            fmt="none", ecolor=color, elinewidth=0.6, alpha=0.55, capsize=0, zorder=2,
        )
        ax.scatter(p["x"], p["y"], s=26, marker=marker, color=color,
                   edgecolors=SURFACE, linewidths=0.8, zorder=3)  # surface ring on overlaps
    ax.set_xlim(0, xmax)
    ax.set_ylim(0, ymax)
    ax.set_xticks(xt := np.arange(0, xmax + 1e-9, 0.25), [f"{t:.0%}" for t in xt])
    ax.set_yticks(yt := np.arange(0, ymax + 1e-9, 0.25), [f"{t:.0%}" for t in yt])
    ax.grid(color=GRID, linewidth=0.5)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(INK_MUTED)
        ax.spines[side].set_linewidth(0.6)
    ax.tick_params(colors=INK_MUTED, labelsize=6.5, width=0.6, length=2.5)
    ax.text(0.03, 0.97, "better", transform=ax.transAxes, fontsize=6, color=INK_MUTED, va="top")
    if title:
        ax.set_title(title, fontsize=7.5, color=INK, loc="left")


def legend(fig, present: set[str], ncol: int | None = None) -> None:
    handles = [
        plt.Line2D([], [], linestyle="none", marker=STYLE[f][1], color=STYLE[f][0],
                   markeredgecolor=SURFACE, markersize=5, label=f)
        for f in ("structured", "natural language", "combined", "no signal") if f in present
    ]
    fig.legend(handles=handles, loc="upper center", ncol=ncol or len(handles), frameon=False,
               fontsize=6.5, handletextpad=0.3, columnspacing=1.0, bbox_to_anchor=(0.5, 1.0))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("scored_csv")
    parser.add_argument("--out", required=True, help="output path without extension; writes .pdf and .png")
    parser.add_argument("--facet-models", action="store_true")
    parser.add_argument("--models", help="comma-separated panel order for --facet-models (default: alphabetical)")
    parser.add_argument("--width", type=float, default=3.33,
                        help="inches; ACM single column is 3.33. With --facet-models, the width of three panels: "
                             "each panel is a third of it, so one or two models print at the same size as three")
    parser.add_argument("--n-boot", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)

    plt.rcParams.update({"font.family": "sans-serif", "font.size": 7, "pdf.fonttype": 42})
    df = pd.read_csv(args.scored_csv)
    present = {FAMILY.get(f, "structured") for f in df["signal_form"].unique()}

    panels: list[tuple] = []
    if args.facet_models:
        present_models = set(df["model"].unique())
        models = ([m for m in args.models.split(",") if m in present_models] if args.models
                  else sorted(present_models))
        ncol = min(3, len(models))
        nrow = int(np.ceil(len(models) / ncol))
        panel = args.width / 3
        fig, axes = plt.subplots(nrow, ncol, figsize=(panel * ncol, panel * nrow + 0.4),
                                 sharex=True, sharey=True, squeeze=False)
        all_pts = [points(df[df["model"] == m], args.n_boot, args.seed) for m in models]
        xmax = _upper(pd.concat([p["x_hi"] for p in all_pts]))
        ymax = _upper(pd.concat([p["y_hi"] for p in all_pts]))
        for ax, model, pts in zip(axes.flat, models, all_pts, strict=False):
            draw(ax, pts, title=MODEL_NAMES.get(model, model), xmax=xmax, ymax=ymax)
            ceiling_note(ax, pts)
            panels.append((ax, pts))
        for ax in axes.flat[len(models):]:
            ax.set_visible(False)
    else:
        fig, ax = plt.subplots(figsize=(args.width, args.width))
        pts = points(df, args.n_boot, args.seed)
        draw(ax, pts, xmax=_upper(pts["x_hi"]), ymax=_upper(pts["y_hi"]))
        ceiling_note(ax, pts)
        panels.append((ax, pts))

    fig.supxlabel(_masks(df[df["arm"] == "core"])[2], fontsize=7, color=INK)
    fig.supylabel("Fetched more when the task needed all pages", fontsize=7, color=INK)
    narrow = fig.get_figwidth() < 3.0  # one facet panel: the legend wraps to two rows
    legend(fig, present, ncol=2 if narrow else None)
    fig.patch.set_facecolor(SURFACE)
    fig.tight_layout(rect=(0, 0, 1, 0.88 if narrow else 0.94))
    for ax, pts in panels:
        place_labels(ax, pts)
    for ext in ("pdf", "png"):
        fig.savefig(f"{args.out}.{ext}", dpi=300, facecolor=SURFACE)
    print(f"wrote {args.out}.pdf and {args.out}.png")


if __name__ == "__main__":
    main()
