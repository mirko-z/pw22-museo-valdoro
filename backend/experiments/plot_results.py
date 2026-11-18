"""Grafico dei risultati dell'esperimento (figura del report).

Legge ``esperimento_sintesi.csv`` e produce ``esperimento_grafico.png`` (300 dpi)
e ``.svg``, con due pannelli affiancati invece di un grafico a doppio asse:
1. posti venduti oltre la capienza (media ± deviazione standard);
2. latenza al 95° percentile (media ± deviazione standard).

Uso:
    docker compose run --rm -v "$PWD/docs/risultati:/app/results" api \\
        python -m experiments.plot_results --dir results
"""

import argparse
import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # nessuna finestra: solo file
import matplotlib.pyplot as plt  # noqa: E402

# Palette categoriale verificata (contrasto e separazione per daltonismo);
# il tratteggio sulla strategia naive la distingue anche in bianco e nero.
STYLE = {
    "locking": {"label": "Con lock (FOR UPDATE)", "color": "#2a78d6", "hatch": ""},
    "naive": {"label": "Senza lock (naive)", "color": "#eb6834", "hatch": "///"},
}
INK, INK_MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"


def load(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def panel(ax, rows, metric: str, title: str, unit: str, ns: list[int]) -> None:  # type: ignore[no-untyped-def]
    width = 0.38
    for i, strategy in enumerate(s for s in STYLE if any(r["strategy"] == s for r in rows)):
        st = STYLE[strategy]
        data = {int(r["n"]): r for r in rows if r["strategy"] == strategy}
        means = [float(data[n][f"{metric}_mean"]) for n in ns]
        stds = [float(data[n][f"{metric}_std"]) for n in ns]
        xs = [k + (i - 0.5) * width for k in range(len(ns))]
        bars = ax.bar(xs, means, width * 0.94, yerr=stds, capsize=3, label=st["label"], color=st["color"],
                      hatch=st["hatch"], edgecolor="white", linewidth=0.8,
                      error_kw={"elinewidth": 1, "ecolor": INK_MUTED})
        for bar, mean, std in zip(bars, means, stds, strict=True):
            ax.annotate(f"{mean:.0f}", (bar.get_x() + bar.get_width() / 2, mean + std),
                        xytext=(0, 3), textcoords="offset points", ha="center", va="bottom",
                        fontsize=8, color=INK)
    ax.set_title(title, fontsize=10, color=INK, loc="left")
    ax.set_xticks(range(len(ns)), [f"N = {n}" for n in ns])
    ax.set_ylabel(unit, fontsize=9, color=INK_MUTED)
    ax.tick_params(colors=INK_MUTED, labelsize=8.5)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(INK_MUTED)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", type=Path, default=Path("results"))
    args = parser.parse_args()
    rows = load(args.dir / "esperimento_sintesi.csv")
    ns = sorted({int(r["n"]) for r in rows})
    seats_left = rows[0]["seats_left"]
    reps = rows[0]["repetitions"]

    fig, (left, right) = plt.subplots(1, 2, figsize=(8, 3.4), dpi=300)
    panel(left, rows, "oversold", "Posti venduti oltre la capienza", "posti", ns)
    panel(right, rows, "latency_p95_ms", "Latenza al 95° percentile", "millisecondi", ns)
    handles, labels = left.get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=2, frameon=False, fontsize=8.5,
               bbox_to_anchor=(0.5, 1.0))
    fig.text(0.5, 0.01, f"N richieste simultanee sugli ultimi {seats_left} posti; media ± dev. standard su "
             f"{reps} ripetizioni", ha="center", fontsize=7.5, color=INK_MUTED)
    fig.tight_layout(rect=(0, 0.04, 1, 0.92))
    for ext in ("png", "svg"):
        fig.savefig(args.dir / f"esperimento_grafico.{ext}", facecolor="white")
    print(f"Grafico scritto in {args.dir}/esperimento_grafico.png e .svg")


if __name__ == "__main__":
    main()
