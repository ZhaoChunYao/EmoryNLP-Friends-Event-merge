import json
import csv
import math
import argparse
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional


DIMENSIONS = ["EXT", "AGR", "CON", "NEU", "OPN"]
LABELS = [-1, 0, 1]


def load_json(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def find_json_files(root: Path) -> List[Path]:
    return sorted(p for p in root.rglob("*.json") if p.is_file())


def rel_key(path: Path, root: Path) -> str:
    return str(path.relative_to(root)).replace("\\", "/")


def safe_get_score(data: Dict[str, Any], dim: str) -> Optional[int]:
    v = data.get(dim, {})
    if isinstance(v, dict):
        score = v.get("score")
        if isinstance(score, int):
            return score
    return None


def safe_get_evidence(data: Dict[str, Any], dim: str) -> str:
    v = data.get(dim, {})
    if isinstance(v, dict):
        evidence = v.get("evidence")
        if isinstance(evidence, str):
            return evidence
    return ""


def parse_rel_parts(relpath: str) -> Tuple[str, str, str]:
    parts = relpath.split("/")
    if len(parts) != 3:
        return "", "", relpath
    return parts[0], parts[1], parts[2]


def mean(xs: List[float]) -> float:
    if not xs:
        return 0.0
    return sum(xs) / len(xs)


def variance(xs: List[float]) -> float:
    if not xs:
        return 0.0
    m = mean(xs)
    return sum((x - m) ** 2 for x in xs) / len(xs)


def covariance(xs: List[float], ys: List[float]) -> float:
    if not xs or not ys or len(xs) != len(ys):
        return 0.0
    mx = mean(xs)
    my = mean(ys)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / len(xs)


def pearson_corr(xs: List[float], ys: List[float]) -> Optional[float]:
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    vx = variance(xs)
    vy = variance(ys)
    if vx == 0 or vy == 0:
        return None
    return covariance(xs, ys) / math.sqrt(vx * vy)


def rankdata(values: List[float]) -> List[float]:
    """
    Average rank for ties, 1-based ranks.
    """
    indexed = sorted(enumerate(values), key=lambda t: t[1])
    ranks = [0.0] * len(values)

    i = 0
    while i < len(indexed):
        j = i
        while j + 1 < len(indexed) and indexed[j + 1][1] == indexed[i][1]:
            j += 1

        avg_rank = (i + 1 + j + 1) / 2.0
        for k in range(i, j + 1):
            orig_idx = indexed[k][0]
            ranks[orig_idx] = avg_rank

        i = j + 1

    return ranks


def spearman_corr(xs: List[float], ys: List[float]) -> Optional[float]:
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    rx = rankdata(xs)
    ry = rankdata(ys)
    return pearson_corr(rx, ry)


def mean_absolute_difference(xs: List[int], ys: List[int]) -> Optional[float]:
    if len(xs) != len(ys) or not xs:
        return None
    return sum(abs(x - y) for x, y in zip(xs, ys)) / len(xs)


def cohen_kappa(xs: List[int], ys: List[int], labels: List[int]) -> Optional[float]:
    if len(xs) != len(ys) or not xs:
        return None

    n = len(xs)
    obs = sum(1 for x, y in zip(xs, ys) if x == y) / n

    px = {lab: 0 for lab in labels}
    py = {lab: 0 for lab in labels}

    for x in xs:
        px[x] += 1
    for y in ys:
        py[y] += 1

    exp = 0.0
    for lab in labels:
        exp += (px[lab] / n) * (py[lab] / n)

    if exp == 1.0:
        return None

    return (obs - exp) / (1 - exp)


def confusion_matrix(xs: List[int], ys: List[int], labels: List[int]) -> Dict[Tuple[int, int], int]:
    mat = {(a, b): 0 for a in labels for b in labels}
    for x, y in zip(xs, ys):
        mat[(x, y)] += 1
    return mat


def compare_outputs(event_root: Path, utter_root: Path, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    event_files = find_json_files(event_root)
    utter_files = find_json_files(utter_root)

    event_map = {rel_key(p, event_root): p for p in event_files}
    utter_map = {rel_key(p, utter_root): p for p in utter_files}

    common_keys = sorted(set(event_map) & set(utter_map))
    event_only = sorted(set(event_map) - set(utter_map))
    utter_only = sorted(set(utter_map) - set(event_map))

    difference_rows: List[Dict[str, Any]] = []
    subscene_rows: List[Dict[str, Any]] = []
    dimension_rows: List[Dict[str, Any]] = []
    confusion_rows: List[Dict[str, Any]] = []

    per_dim_event_scores: Dict[str, List[int]] = {d: [] for d in DIMENSIONS}
    per_dim_utter_scores: Dict[str, List[int]] = {d: [] for d in DIMENSIONS}

    total_dimensions = 0
    same_dimensions = 0
    diff_dimensions = 0
    abs_diff_hist = {0: 0, 1: 0, 2: 0, "other": 0}

    subscene_total = 0
    subscene_identical = 0
    subscene_different = 0

    for key in common_keys:
        episode, character, subscene_file = parse_rel_parts(key)

        event_data = load_json(event_map[key])
        utter_data = load_json(utter_map[key])

        subscene_total += 1
        subscene_diff_count = 0
        subscene_diff_dims: List[str] = []

        for dim in DIMENSIONS:
            e_score = safe_get_score(event_data, dim)
            u_score = safe_get_score(utter_data, dim)

            if e_score is None or u_score is None:
                continue

            total_dimensions += 1
            per_dim_event_scores[dim].append(e_score)
            per_dim_utter_scores[dim].append(u_score)

            if e_score == u_score:
                same_dimensions += 1
                abs_diff_hist[0] += 1
            else:
                diff_dimensions += 1
                subscene_diff_count += 1
                subscene_diff_dims.append(dim)

                gap = abs(e_score - u_score)
                if gap in (1, 2):
                    abs_diff_hist[gap] += 1
                else:
                    abs_diff_hist["other"] += 1

                difference_rows.append({
                    "episode": episode,
                    "character": character,
                    "subscene": subscene_file,
                    "dimension": dim,
                    "event_score": e_score,
                    "utterance_score": u_score,
                    "score_gap": abs(e_score - u_score),
                    "event_evidence": safe_get_evidence(event_data, dim),
                    "utterance_evidence": safe_get_evidence(utter_data, dim),
                    "rel_path": key,
                })

        subscene_rows.append({
            "episode": episode,
            "character": character,
            "subscene": subscene_file,
            "diff_dimensions": subscene_diff_count,
            "diff_dimension_names": "|".join(subscene_diff_dims),
            "is_identical": int(subscene_diff_count == 0),
            "rel_path": key,
        })

        if subscene_diff_count == 0:
            subscene_identical += 1
        else:
            subscene_different += 1

    for dim in DIMENSIONS:
        xs = per_dim_event_scores[dim]
        ys = per_dim_utter_scores[dim]

        n = len(xs)
        agree = sum(1 for x, y in zip(xs, ys) if x == y)
        disagree = n - agree

        pearson = pearson_corr(xs, ys)
        spearman = spearman_corr(xs, ys)
        mad = mean_absolute_difference(xs, ys)
        var_event = variance(xs)
        var_utter = variance(ys)
        kappa = cohen_kappa(xs, ys, LABELS)
        cm = confusion_matrix(xs, ys, LABELS)

        dimension_rows.append({
            "dimension": dim,
            "n": n,
            "same": agree,
            "diff": disagree,
            "agreement_rate": agree / n if n else 0.0,
            "pearson_r": pearson,
            "spearman_rho": spearman,
            "mean_absolute_difference": mad,
            "variance_event": var_event,
            "variance_utterance": var_utter,
            "cohen_kappa": kappa,
        })

        for e_lab in LABELS:
            for u_lab in LABELS:
                confusion_rows.append({
                    "dimension": dim,
                    "event_score": e_lab,
                    "utterance_score": u_lab,
                    "count": cm[(e_lab, u_lab)],
                })

    summary = {
        "event_root": str(event_root),
        "utterance_root": str(utter_root),
        "out_dir": str(out_dir),
        "common_file_count": len(common_keys),
        "event_only_file_count": len(event_only),
        "utterance_only_file_count": len(utter_only),
        "event_only_files": event_only,
        "utterance_only_files": utter_only,
        "subscene_total": subscene_total,
        "subscene_identical": subscene_identical,
        "subscene_different": subscene_different,
        "subscene_identical_rate": (
            subscene_identical / subscene_total if subscene_total else 0.0
        ),
        "total_dimensions": total_dimensions,
        "same_dimensions": same_dimensions,
        "diff_dimensions": diff_dimensions,
        "dimension_agreement_rate": (
            same_dimensions / total_dimensions if total_dimensions else 0.0
        ),
        "abs_diff_histogram": abs_diff_hist,
        "difference_record_count": len(difference_rows),
        "dimension_statistics": dimension_rows,
    }

    with open(out_dir / "compare_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    with open(out_dir / "dimension_statistics.csv", "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "dimension",
                "n",
                "same",
                "diff",
                "agreement_rate",
                "pearson_r",
                "spearman_rho",
                "mean_absolute_difference",
                "variance_event",
                "variance_utterance",
                "cohen_kappa",
            ],
        )
        writer.writeheader()
        writer.writerows(dimension_rows)

    with open(out_dir / "confusion_matrices.csv", "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "dimension",
                "event_score",
                "utterance_score",
                "count",
            ],
        )
        writer.writeheader()
        writer.writerows(confusion_rows)

    with open(out_dir / "differences.csv", "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "episode",
                "character",
                "subscene",
                "dimension",
                "event_score",
                "utterance_score",
                "score_gap",
                "event_evidence",
                "utterance_evidence",
                "rel_path",
            ],
        )
        writer.writeheader()
        writer.writerows(difference_rows)

    with open(out_dir / "subscene_summary.csv", "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "episode",
                "character",
                "subscene",
                "diff_dimensions",
                "diff_dimension_names",
                "is_identical",
                "rel_path",
            ],
        )
        writer.writeheader()
        writer.writerows(subscene_rows)

    print(f"Done. Output written to: {out_dir}")
    print(f"Common files: {len(common_keys)}")
    print(f"Subscene identical: {subscene_identical}/{subscene_total}")
    print(f"Dimension agreement: {same_dimensions}/{total_dimensions}")
    print(f"Differences: {len(difference_rows)}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--event_root", default="big_five_output_anon")
    parser.add_argument("--utter_root", default="big_five_output_utterance_anon")
    parser.add_argument("--out_dir", default="analysis/utterance_vs_events")
    args = parser.parse_args()

    compare_outputs(
        event_root=Path(args.event_root),
        utter_root=Path(args.utter_root),
        out_dir=Path(args.out_dir),
    )


if __name__ == "__main__":
    main()
