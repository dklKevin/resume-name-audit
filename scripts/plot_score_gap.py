"""Draw the score gap by group, one panel per model, from a run's metrics.json.

Usage: python scripts/plot_score_gap.py runs/main/metrics.json results/score_gap.svg

Writes a static SVG (no dependencies) that follows the viewer's light or dark mode.
"""

import json
import sys
from pathlib import Path

GROUPS = ["Black F", "Black M", "white F", "white M"]
LABELS = {
    "Black F": "Black women",
    "Black M": "Black men",
    "white F": "white women",
    "white M": "white men",
}
TITLES = {"openai": "GPT-6 Luna", "gemini": "Gemini 3.6 Flash"}
ORDER = ["openai", "gemini"]

WIDTH, PANEL_W, LEFT, TOP, PANEL_GAP = 830, 300, 120, 92, 64
ROW_H, PLOT_H_PAD = 44, 18
X_MIN, X_MAX = -2.0, 2.0


def x_pos(panel_x: float, value: float) -> float:
    return panel_x + (value - X_MIN) / (X_MAX - X_MIN) * PANEL_W


def render(metrics: dict) -> str:
    plot_h = ROW_H * len(GROUPS) + PLOT_H_PAD
    height = TOP + plot_h + 86
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {height}" '
        f'width="{WIDTH}" height="{height}" role="img" '
        'aria-labelledby="title desc" font-family="-apple-system, Segoe UI, Helvetica, Arial, sans-serif">',
        '<title id="title">Score gap by group, one panel per model</title>',
        "<desc id=\"desc\">Each dot is a group's mean score gap against the same resume's "
        "average across groups, with a 95 percent bootstrap interval.</desc>",
        "<style>",
        ":root{--bg:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--grid:#e4e3df;--zero:#9b9a95;--mark:#2a78d6}",
        "@media (prefers-color-scheme: dark){:root{--bg:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;"
        "--grid:#33332f;--zero:#6f6e69;--mark:#3987e5}}",
        ".bg{fill:var(--bg)}.t1{fill:var(--ink)}.t2{fill:var(--ink2)}",
        ".grid{stroke:var(--grid);stroke-width:1}.zero{stroke:var(--zero);stroke-width:1.5}",
        ".ci{stroke:var(--mark);stroke-width:2;stroke-linecap:round}",
        ".dot{fill:var(--mark);stroke:var(--bg);stroke-width:2}",
        "</style>",
        f'<rect class="bg" width="{WIDTH}" height="{height}" rx="8"/>',
        '<text class="t1" x="24" y="36" font-size="18" font-weight="600">'
        "Score gap by group when only the name changes</text>",
        '<text class="t2" x="24" y="60" font-size="13">Points on a 0 to 100 screening score, '
        "against the same resume's average across groups. Bars are 95% intervals.</text>",
    ]
    for p, provider in enumerate(ORDER):
        model = metrics["models"][provider]
        px = LEFT + p * (PANEL_W + PANEL_GAP)
        out.append(
            f'<text class="t1" x="{px + PANEL_W / 2}" y="{TOP - 10}" font-size="14" '
            f'font-weight="600" text-anchor="middle">{TITLES[provider]}</text>'
        )
        for tick in (-2, -1, 0, 1, 2):
            tx = x_pos(px, tick)
            cls = "zero" if tick == 0 else "grid"
            out.append(f'<line class="{cls}" x1="{tx}" y1="{TOP}" x2="{tx}" y2="{TOP + plot_h}"/>')
            label = f"{tick:+d}" if tick else "0"
            out.append(
                f'<text class="t2" x="{tx}" y="{TOP + plot_h + 18}" font-size="12" '
                f'text-anchor="middle">{label}</text>'
            )
        for i, group in enumerate(GROUPS):
            y = TOP + PLOT_H_PAD / 2 + ROW_H * i + ROW_H / 2
            gap = model["score_gap"][group]
            if p == 0:
                out.append(
                    f'<text class="t1" x="{LEFT - 14}" y="{y + 4}" font-size="13" '
                    f'text-anchor="end">{LABELS[group]}</text>'
                )
            lo, hi, est = (x_pos(px, gap[k]) for k in ("low", "high", "estimate"))
            out.append(f'<line class="ci" x1="{lo}" y1="{y}" x2="{hi}" y2="{y}"/>')
            out.append(f'<circle class="dot" cx="{est}" cy="{y}" r="5.5"/>')
            anchor_x = hi + 8 if gap["estimate"] >= 0 else lo - 8
            anchor = "start" if gap["estimate"] >= 0 else "end"
            out.append(
                f'<text class="t2" x="{anchor_x}" y="{y + 4}" font-size="12" '
                f'text-anchor="{anchor}">{gap["estimate"]:+.1f}</text>'
            )
        degree = model["degree_gap"]["estimate"]
        out.append(
            f'<text class="t2" x="{px + PANEL_W / 2}" y="{TOP + plot_h + 40}" font-size="12" '
            f'text-anchor="middle">For scale: the degree swap moved scores {degree:.1f} points</text>'
        )
    out.append(
        f'<text class="t2" x="24" y="{height - 16}" font-size="11">40 resumes, 12 names (3 per '
        "group), 2 repeats. Intervals resample resumes.</text>"
    )
    out.append("</svg>")
    return "\n".join(out) + "\n"


def main() -> None:
    metrics = json.loads(Path(sys.argv[1]).read_text())
    out = Path(sys.argv[2])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(metrics))


if __name__ == "__main__":
    main()
