"""LaTeX tables of Appendix C.6 from the completed B5 design.

Writes the bodies that are pasted into 09_appendix.tex and 05_results.tex, so
that every number in the sensitivity subsection is traceable to
resultados_B5/{brasil,chile}/ without being retyped.

Usage:
    python make_sensitivity_tables_b5.py --results ../../resultados_B5 \
        --out generated/b5_tables.tex
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

FACTORS = ["m_bar", "sigma", "f_min", "alpha_get", "pi_star", "theta",
           "lifetime", "discount", "trans_cost", "capex_res",
           "demand_growth", "hydro_inflow"]

FACTOR_TEX = {
    "m_bar": r"Desired availability margin $\bar m$",
    "sigma": r"Grid security margin $\sigma$",
    "f_min": r"Minimum grid increment $F_{\min}$",
    "alpha_get": r"Allowed GET share $\alpha_i$",
    "pi_star": r"Profitability threshold $\Pi^{*}$",
    "theta": r"Logit scale $\theta$",
    "lifetime": r"Technical lifetime $L_g$",
    "discount": r"Discount rate $r$",
    "trans_cost": r"Transmission cost",
    "capex_res": r"CAPEX PV, wind, BESS",
    "demand_growth": r"Demand growth",
    "hydro_inflow": r"Hydrological inflows",
}

OUT_ORDER = ["Total Generation Capacity", "Total Transmission",
             "Capacity Margin[f0]", "Total System Cost",
             "Total Interconnection Capacity",
             "Aggregated Generation Tariff[f0]",
             "Congestion Tariff[f0]", "Total New Investment"]

# Unit strings are the ones declared in the Vensim equations, not re-scaled here.
OUT_TEX = {
    "Total Generation Capacity": ("Installed generation capacity", "GW"),
    "Total Transmission": ("Transmission line length", "km"),
    "Capacity Margin[f0]": ("Capacity margin", "---"),
    "Total System Cost": ("Total system cost", "MMUSD"),
    "Total Interconnection Capacity": ("Interconnection capacity", "MW"),
    "Aggregated Generation Tariff[f0]": ("Generation tariff, zonal sum", "USD/MWh"),
    "Congestion Tariff[f0]": ("Congestion charge", "USD/MWh"),
    "Total New Investment": ("New investment decisions", "MW"),
}

SHORT = {
    "Total Generation Capacity": "Gen.~cap.",
    "Total Transmission": "Transm.",
    "Capacity Margin[f0]": "Margin",
    "Total System Cost": "Cost",
    "Total Interconnection Capacity": "Intercon.",
    "Aggregated Generation Tariff[f0]": "Gen.~tariff",
    "Congestion Tariff[f0]": "Congest.",
    "Total New Investment": "Investm.",
}


def num(x: float, digits: int = 3) -> str:
    return f"{x:+.{digits}f}".replace("-", "$-$")


def sig(x: float) -> str:
    """Three significant figures in fixed notation, thin space as separator."""
    if x == 0:
        return "0"
    mag = int(np.floor(np.log10(abs(x))))
    return f"{x:,.{max(0, 2 - mag)}f}".replace(",", r"\,")


def src_matrix(indices: pd.DataFrame, outputs: list[str]) -> str:
    """Full standardised-regression matrix: 12 factors by the available outputs."""
    present = [o for o in outputs if o in set(indices["output"])]
    head = " & ".join(SHORT[o] for o in present)
    # the factor column takes whatever the numeric columns leave
    width = 0.27 if len(present) <= 7 else 0.24
    rows = [r"\begin{tabular}{@{}p{" + f"{width}" + r"\textwidth}" + "r" * len(present) + "@{}}",
            r"\toprule",
            r"Factor & " + head + r"\\",
            r"\midrule"]
    for f in FACTORS:
        cells = []
        for o in present:
            sub = indices[(indices["output"] == o) & (indices["factor"] == f)]
            cells.append(num(float(sub["src"].iloc[0]), 2) if len(sub) else "---")
        rows.append(FACTOR_TEX[f] + " & " + " & ".join(cells) + r"\\")
    rows.append(r"\midrule")
    r2 = []
    for o in present:
        sub = indices[indices["output"] == o]
        r2.append(f"{float(sub['r2'].iloc[0]):.2f}")
    rows.append(r"\textit{Linear fit} $R^{2}$ & " + " & ".join(r2) + r"\\")
    rows += [r"\bottomrule", r"\end{tabular}"]
    return "\n".join(rows)


def spread_table(res: dict[str, pd.DataFrame]) -> str:
    rows = [r"\begin{tabular}{@{}p{0.25\textwidth}p{0.11\textwidth}rrrrrr@{}}",
            r"\toprule",
            r" & & \multicolumn{3}{c}{Brazil} & \multicolumn{3}{c}{Chile}\\",
            r"\cmidrule(lr){3-5}\cmidrule(lr){6-8}",
            r"Output & Unit & $P_{5}$ & median & $P_{95}$ & $P_{5}$ & median & $P_{95}$\\",
            r"\midrule"]
    for o in OUT_ORDER:
        label, unit = OUT_TEX[o]
        cells = []
        for country in ("Brazil", "Chile"):
            v = res[country][o].values
            cells += [sig(np.percentile(v, 5)), sig(np.median(v)), sig(np.percentile(v, 95))]
        rows.append(f"{label} & {unit} & " + " & ".join(f"${c}$" for c in cells) + r"\\")
    rows += [r"\bottomrule", r"\end{tabular}"]
    return "\n".join(rows)


def leading_table(idx: dict[str, pd.DataFrame]) -> str:
    """The compact summary of Section 5.9: leading factor per output and country."""
    rows = [r"\begin{tabular}{@{}llp{0.20\textwidth}rrl@{}}",
            r"\toprule",
            r"Country & Output & Leading factor & index & $R^{2}$ & Ranked by\\",
            r"\midrule"]
    for country in ("Brazil", "Chile"):
        frame = idx[country]
        first = True
        for o in OUT_ORDER:
            sub = frame[frame["output"] == o]
            name = OUT_TEX[o][0]
            if sub.empty:
                rows.append((country if first else "") +
                            f" & {name} & " + r"\multicolumn{4}{@{}l}{constant across the design}\\")
                first = False
                continue
            method = sub["ranked_by"].iloc[0]
            key = "src" if method == "src" else "spearman"
            top = sub.reindex(sub[key].abs().sort_values(ascending=False).index).iloc[0]
            rows.append(
                (country if first else "") + f" & {name} & {FACTOR_TEX[top['factor']]} & "
                f"{num(float(top[key]), 2)} & {float(sub['r2'].iloc[0]):.2f} & "
                + ("SRC" if method == "src" else "Spearman") + r"\\")
            first = False
        if country == "Brazil":
            rows.append(r"\addlinespace")
    rows += [r"\bottomrule", r"\end{tabular}"]
    return "\n".join(rows)


# --------------------------------------------------------------------------- #
# The paired country contrast
# --------------------------------------------------------------------------- #

# Each entry is a dimensionally coherent ratio, so that the two systems can be
# compared without their difference in size doing the work.
CONTRASTS = [
    ("Capacity margin",
     "---",
     lambda d: d["Capacity Margin[f0]"]),
    ("Transmission length per GW installed",
     "km/GW",
     lambda d: d["Total Transmission"] / d["Total Generation Capacity"]),
    ("Interconnection capacity per GW installed",
     "MW/GW",
     lambda d: d["Total Interconnection Capacity"] / d["Total Generation Capacity"]),
    ("Interconnection capacity per 1\\,000\\,km of line",
     "MW/1\\,000\\,km",
     lambda d: 1000 * d["Total Interconnection Capacity"] / d["Total Transmission"]),
    ("System cost per GW installed",
     "MMUSD/GW",
     lambda d: d["Total System Cost"] / d["Total Generation Capacity"]),
]


def contrast_table(res: dict[str, pd.DataFrame]) -> str:
    """How often the country ordering of an indicator survives a common draw.

    The design is paired: sample k carries the same factor values in the two
    countries, so the ordering can be counted sample by sample rather than
    compared distribution against distribution.
    """
    n = len(res["Brazil"])
    rows = [r"\begin{tabular}{@{}p{0.32\textwidth}p{0.15\textwidth}rrr@{}}",
            r"\toprule",
            r" & & \multicolumn{2}{c}{Median over the design} & Ordering holds\\",
            r"\cmidrule(lr){3-4}",
            r"Indicator & Unit & Brazil & Chile & in $k$ of " + str(n) + r" draws\\",
            r"\midrule"]
    for label, unit, fun in CONTRASTS:
        vb, vc = fun(res["Brazil"]).values, fun(res["Chile"]).values
        mb, mc = float(np.median(vb)), float(np.median(vc))
        holds = int((vc > vb).sum()) if mc > mb else int((vb > vc).sum())
        rows.append(f"{label} & {unit} & ${sig(mb)}$ & ${sig(mc)}$ & "
                    f"{holds}/{n}\\\\")
    rows += [r"\bottomrule", r"\end{tabular}"]
    return "\n".join(rows)


def agreement_note(idx: dict[str, pd.DataFrame], threshold: float = 0.05) -> str:
    """Sign agreement of the material coefficients, on the identified outputs."""
    identified = ["Total Generation Capacity", "Total Transmission",
                  "Capacity Margin[f0]", "Total System Cost"]
    agree = total = 0
    for o in identified:
        b = idx["Brazil"]
        c = idx["Chile"]
        b = b[b["output"] == o].set_index("factor")["src"]
        c = c[c["output"] == o].set_index("factor")["src"]
        common = b.index.intersection(c.index)
        mask = (b[common].abs() > threshold) & (c[common].abs() > threshold)
        total += int(mask.sum())
        agree += int((np.sign(b[common][mask]) == np.sign(c[common][mask])).sum())
    return (f"% sign agreement on the four identified outputs, |SRC| > {threshold}: "
            f"{agree}/{total}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="../results/B5_latin_hypercube", type=Path)
    ap.add_argument("--out", default=Path("generated/b5_tables.tex"), type=Path)
    args = ap.parse_args()

    idx = {"Brazil": pd.read_csv(args.results / "brazil" / "sensitivity_indices.csv"),
           "Chile": pd.read_csv(args.results / "chile" / "sensitivity_indices.csv")}
    res = {"Brazil": pd.read_csv(args.results / "brazil" / "results.csv"),
           "Chile": pd.read_csv(args.results / "chile" / "results.csv")}

    args.out.parent.mkdir(parents=True, exist_ok=True)
    blocks = [
        ("% ---- Section 5.9, tab:sensitivity ----", leading_table(idx)),
        ("% ---- Appendix C.6, tab:appC6src-brazil ----", src_matrix(idx["Brazil"], OUT_ORDER)),
        ("% ---- Appendix C.6, tab:appC6src-chile ----", src_matrix(idx["Chile"], OUT_ORDER)),
        ("% ---- Appendix C.6, tab:appC6spread ----", spread_table(res)),
        ("% ---- Appendix C.6, tab:appC6contrast ----", contrast_table(res)),
        ("% ---- Appendix C.6, sign agreement ----", agreement_note(idx)),
    ]
    args.out.write_text(
        "\n\n".join(f"{head}\n{body}" for head, body in blocks) + "\n",
        encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
