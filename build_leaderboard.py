"""
build_leaderboard.py
====================
Reads all CSV files from submissions/, scores each against the public-test
ground truth, and writes two outputs:

  * leaderboard.json  -- machine-readable, consumed by the web page (index.html)
  * README.md         -- human-readable markdown table (unchanged behaviour)

Each submission CSV has two columns: clip_id, predicted_emotion.
Weighted F1 is computed server-side against the ground truth — no
self-reported scores. Run by GitHub Actions on every push to submissions/.

Environment variables:
  GROUND_TRUTH : path to the public test ground-truth CSV
                 (default: ground_truth/public_test_labels.csv)
"""

import os
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from sklearn.metrics import f1_score


SUBMISSIONS_DIR = Path("submissions")
JSON_OUT        = Path("leaderboard.json")
EMOTIONS        = ["anger", "disgust", "fear", "happy", "neutral", "sad"]
EMOTION_TO_IDX  = {e: i for i, e in enumerate(EMOTIONS)}


def load_ground_truth(gt_path):
    df = pd.read_csv(gt_path).sort_values("clip_id").reset_index(drop=True)
    return df.set_index("clip_id")["emotion"].to_dict()


def load_submissions():
    rows = []
    for csv_file in sorted(SUBMISSIONS_DIR.glob("*.csv")):
        try:
            df = pd.read_csv(csv_file)
            if not {"clip_id", "predicted_emotion"}.issubset(df.columns):
                print(f"  !!  {csv_file.name}: missing required columns")
                continue
            rows.append({
                "team_name": csv_file.stem.replace("_", " "),
                "filename":  csv_file,
                "df":        df,
                "submitted_at": datetime.fromtimestamp(
                    csv_file.stat().st_mtime, tz=timezone.utc
                ).isoformat(),
            })
            print(f"  OK  {csv_file.name}")
        except Exception as e:
            print(f"  !!  {csv_file.name}: {e}")
    return rows


def verify(data, ground_truth):
    """Return weighted F1 of a submission against the ground truth."""
    df   = data["df"].sort_values("clip_id").reset_index(drop=True)
    true = [EMOTION_TO_IDX[ground_truth[c]] for c in df["clip_id"]
            if c in ground_truth]
    pred = [EMOTION_TO_IDX.get(e, -1)
            for c, e in zip(df["clip_id"], df["predicted_emotion"])
            if c in ground_truth]

    if len(true) != len(pred) or len(true) == 0:
        raise ValueError("Prediction count mismatch or no matching clip IDs")

    return f1_score(true, pred, average="weighted")


def get_baseline_f1(rows):
    for row in rows:
        if row["team_name"].lower() == "baseline":
            return row["weighted_f1"]
    raise FileNotFoundError(
        "baseline.csv not found in submissions/. "
        "Run test.py with --team_name baseline and push the CSV first."
    )


def rank_rows(rows, baseline_f1):
    """Sort by F1 (desc) and attach rank, delta-vs-baseline, and flags."""
    ranked = sorted(rows, key=lambda r: r["weighted_f1"], reverse=True)
    out = []
    for i, row in enumerate(ranked):
        f1 = row["weighted_f1"]
        is_baseline = row["team_name"].lower() == "baseline"
        delta_pct = ((f1 - baseline_f1) / baseline_f1 * 100.0) if baseline_f1 else 0.0
        out.append({
            "rank":          i + 1,
            "team_name":     row["team_name"],
            "weighted_f1":   round(f1, 4),
            "delta_pct":     round(delta_pct, 2),
            "beats_baseline": bool(f1 > baseline_f1),
            "is_baseline":   is_baseline,
            "submitted_at":  row.get("submitted_at"),
        })
    return out


def build_markdown(ranked, baseline_f1, generated_at):
    lines = [
        "# Leaderboard — Speech Emotion Recognition Challenge",
        "",
        f"> Last updated: **{generated_at}**  ",
        f"> Baseline weighted F1: **{baseline_f1:.4f}**  ",
        "> Metric: weighted F1-score on the public test set",
        "",
        "---",
        "",
    ]
    if not ranked:
        lines += ["No team submissions yet.", ""]
    else:
        lines += [
            "| Rank | Team Name | Weighted F1 | vs. Baseline | Date and Time |",
            "|------|-----------|-------------|--------------|---------------|",
        ]
        for r in ranked:
            submitted = r.get("submitted_at") or "—"
            try:
                submitted = datetime.fromisoformat(submitted).strftime(
                    "%b %d, %Y  %H:%M UTC")
            except Exception:
                pass
            delta = "—" if r["is_baseline"] else f"{r['delta_pct']:+.2f}%"
            lines.append(
                f"| {r['rank']} | {r['team_name']} | {r['weighted_f1']:.4f} "
                f"| {delta} | {submitted} |")
        lines.append("")
    lines += [
        "---",
        "",
        "*This leaderboard updates automatically when teams push a new "
        "submission CSV to `submissions/`. See the project page for details.*",
        "",
    ]
    return "\n".join(lines)


def main():
    gt_path = os.environ.get("GROUND_TRUTH",
                             "ground_truth/public_test_labels.csv")

    print(f"Ground truth : {gt_path}")
    ground_truth = load_ground_truth(gt_path)
    print(f"Ground truth clips: {len(ground_truth)}")

    print("\nLoading and verifying submissions...")
    raw_rows = load_submissions()
    print(f"Found {len(raw_rows)} submission(s)")

    rows = []
    for data in raw_rows:
        try:
            wf1 = verify(data, ground_truth)
            rows.append({
                "team_name":    data["team_name"],
                "weighted_f1":  round(wf1, 4),
                "submitted_at": data["submitted_at"],
            })
            print(f"  verified  {data['team_name']}: F1={wf1:.4f}")
        except Exception as e:
            print(f"  failed    {data['team_name']}: {e}")

    baseline_f1 = get_baseline_f1(rows)
    print(f"\nBaseline F1  : {baseline_f1:.4f}")

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    ranked = rank_rows(rows, baseline_f1)

    JSON_OUT.write_text(json.dumps({
        "generated_at": generated_at,
        "baseline_f1":  round(baseline_f1, 4),
        "metric":       "weighted F1 (public test set)",
        "team_count":   len(ranked),
        "teams":        ranked,
    }, indent=2))
    print(f"Leaderboard JSON written to {JSON_OUT}")


if __name__ == "__main__":
    main()
