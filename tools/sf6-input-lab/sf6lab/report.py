"""Turn experiment CSVs into a readable report + JSON for the AC tester."""
from __future__ import annotations

import csv
import glob
import json
import math
import os
from collections import Counter, defaultdict

from .core import DATA_DIR
from . import models

CASE_LABEL = {
    "hado_gap": "波動: 2→3の間（3を長押し）", "hado_btn": "波動: 6→ボタンの間",
    "tatsu_gap": "竜巻: 2→1の間（1を長押し）", "dp_gap": "昇竜: 6→2の間（2を長押し）",
    "dp_btn": "昇竜: 3→ボタンの間", "sa_gap": "真空: 1回目の6→2の間（2を長押し）",
}


def _latest(prefix: str) -> list[dict]:
    rows = []
    for p in sorted(glob.glob(os.path.join(DATA_DIR, f"{prefix}_*.csv"))):
        with open(p, encoding="utf-8") as f:
            rows += list(csv.DictReader(f))
    return rows


def report_A(rows: list[dict]) -> tuple[list[str], dict]:
    by = defaultdict(lambda: [0, 0])
    unread = 0
    for r in rows:
        if not r["seen_seq"]:
            unread += 1
            continue
        d = float(r["diag_ms"])
        by[d][0] += int(r["diag_seen"])
        by[d][1] += 1
    if not by:
        return ["実験Aのデータがありません。"], {}
    preds = {m: {d: models.predict_A(d, m, n=1500) for d in by} for m in models.MODELS}
    ll = {}
    for m in models.MODELS:
        s = 0.0
        for d, (k, n) in by.items():
            p = min(max(preds[m][d], 1e-3), 1 - 1e-3)
            s += k * math.log(p) + (n - k) * math.log(1 - p)
        ll[m] = s
    best = max(ll, key=ll.get)
    lines = ["## 実験A: 短い斜め（3）は入力履歴に残るか", "",
             "| 3の長さ | 実測 | " + " | ".join(models.MODEL_LABEL[m] for m in models.MODELS) + " |",
             "| --- | --- | " + " | ".join("---" for _ in models.MODELS) + " |"]
    for d in sorted(by):
        k, n = by[d]
        lines.append(f"| {d:g}ms | {k / n:.0%}（{k}/{n}） | " + " | ".join(f"{preds[m][d]:.0%}" for m in models.MODELS) + " |")
    lines += ["", "当てはまりの良さ（対数尤度、大きいほど実測に近い）: " +
              " / ".join(f"{models.MODEL_LABEL[m]} {ll[m]:.1f}" for m in models.MODELS),
              "", f"**最も近いモデル: {models.MODEL_LABEL[best]}**"]
    if unread:
        lines.append(f"\n（入力履歴が読めなかった試行: {unread}件。多い場合は setup をやり直してください）")
    return lines, {"model": best, "loglik": ll, "rates": {str(d): by[d][0] / by[d][1] for d in by}}


def report_B(rows: list[dict]) -> list[str]:
    if not rows:
        return ["実験Bのデータがありません。"]
    lines = ["## 実験B: 1フレームの中に 2・3・6 を入れたとき", ""]
    for x in sorted({r["each_ms"] for r in rows}, key=float):
        c = Counter(r["seen_seq"] or "(読めず)" for r in rows if r["each_ms"] == x)
        total = sum(c.values())
        lines.append(f"- 各{x}ms: " + "、".join(f"{k} {v / total:.0%}" for k, v in c.most_common()))
    return lines


def report_C(rows: list[dict]) -> tuple[list[str], dict]:
    if not rows:
        return ["実験Cのデータがありません。"], {}
    by = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for r in rows:
        by[r["case"]][int(r["frames"])][0] += int(r["ok"])
        by[r["case"]][int(r["frames"])][1] += 1
    lines = ["## 実験C: 受付フレーム", "", "各条件で技が出た割合。50%を下回る直前のフレーム数を受付の上限と推定します。", ""]
    est = {}
    for case, rs in by.items():
        gs = sorted(rs)
        cells = " / ".join(f"{g}F {rs[g][0] / rs[g][1]:.0%}" for g in gs)
        ok = [g for g in gs if rs[g][0] / rs[g][1] >= 0.5]
        est[case] = max(ok) if ok else None
        lines.append(f"- {CASE_LABEL.get(case, case)}: {cells} → **推定 {est[case]}F**")
    return lines, est


def build() -> str:
    a_lines, a = report_A(_latest("A"))
    b_lines = report_B(_latest("B"))
    c_lines, c = report_C(_latest("C"))
    md = "\n".join(["# SF6 入力読み取り 実測レポート", ""] + a_lines + [""] + b_lines + [""] + c_lines) + "\n"
    with open(os.path.join(DATA_DIR, "report.md"), "w", encoding="utf-8") as f:
        f.write(md)
    with open(os.path.join(DATA_DIR, "export.json"), "w", encoding="utf-8") as f:
        json.dump({"reading": a, "buffers": c}, f, ensure_ascii=False, indent=2)
    return md
