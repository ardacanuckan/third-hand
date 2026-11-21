"""Translate every simulated episode with motion_to_text and score the text against the ground truth.

    python translate_all.py out/            # -> out/texts.jsonl, out/scores.json, prints a table

texts.jsonl, one line per episode: scenario, difficulty, task, the reference narrative (what really
happened), the translation (summary + steps), and per-episode checks. Use the pairs (joints -> reference
text, or translation -> reference) to evaluate or train the LLM side.
"""
import collections, json, multiprocessing as mp, pathlib, sys

import pyarrow.parquet as pq

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import motion_to_text as M  # noqa: E402

BASE_NS = 1_795_000_000_000_000_000
EP_NS = 60_000_000_000


def episodes(shard):
    t = pq.read_table(shard, columns=["episode_start_ns", "timestamp_ns_since_episode_start", "joints"]).to_pydict()
    eps = collections.defaultdict(list)
    for s, ts, js in zip(t["episode_start_ns"], t["timestamp_ns_since_episode_start"], t["joints"]):
        eps[(s - BASE_NS) // EP_NS].append(M.Frame(ts / 1e9, {j: x["position_norm"] for j, x in zip(M.JOINTS, js)},
                                                    {j: x["current_ma"] for j, x in zip(M.JOINTS, js)},
                                                    {j: x["goal_norm"] for j, x in zip(M.JOINTS, js)},
                                                    {j: (x["range_min"], x["range_max"]) for j, x in zip(M.JOINTS, js)}))
    return eps


def check(truth, d):
    ev = truth["events"]
    tg = [e["t"] for e in ev if e["type"] == "grasp"]
    lasting = tg          # every grasp counts, including one that tips out a moment later
    pg = [t for t, e in d.events if e.startswith("grips")]
    matched = sum(any(abs(a - b) <= 1.0 for b in pg) for a in lasting)
    said = " ".join(e for _, e in d.events)
    return {
        "true_grasps": len(lasting), "said_grasps": len(pg), "grasps_matched_1s": matched,
        "grasp_count_right": len(pg) == len(lasting),
        "fault_true": any(e["type"] == "overload" for e in ev), "fault_said": "stops following" in said,
        "miss_true": truth["scenario"] in ("miss_retry", "tip_over"), "miss_said": "missed grasp" in said,
        "delivered_true": truth["success"],
        "delivered_said": any(e.startswith("lets go") for _, e in d.events) and "stops following" not in said,
        "gaps_said": "gap" in d.summary,
        "pull_true": any(e["type"] == "pull_detected" for e in ev), "pull_said": "after a pull" in said,
    }


def work(shard):
    out = []
    for ep_id, frames in episodes(shard).items():
        d = M.describe(sorted(frames, key=lambda f: f.t))
        out.append((ep_id, d.summary, d.text, [(round(t, 2), e) for t, e in d.events]))
    return out


def main(out_dir: pathlib.Path):
    truth = {json.loads(l)["id"]: json.loads(l) for l in (out_dir / "truth.jsonl").read_text().splitlines()}
    shards = sorted(out_dir.glob("episodes-*.parquet"))
    with mp.Pool(7) as pool:
        results = [r for part in pool.map(work, shards) for r in part]
    by_scen = collections.defaultdict(list)
    with open(out_dir / "texts.jsonl", "w") as f:
        for ep_id, summary, steps, events in sorted(results):
            tr = truth[ep_id]
            d = M.Description([], events, steps, summary)
            c = check(tr, d)
            by_scen[tr["scenario"]].append(c)
            f.write(json.dumps({"id": ep_id, "scenario": tr["scenario"], "difficulty": tr["difficulty"], "task": tr["task"],
                                "reference": tr["narrative"], "truth_events": tr["events"], "success": tr["success"],
                                "translation": summary, "steps": steps, "checks": c}) + "\n")
    rows, total = {}, collections.Counter()
    for scen, cs in sorted(by_scen.items()):
        n = len(cs)
        r = {"episodes": n,
             "grasp_count_right_%": round(100 * sum(c["grasp_count_right"] for c in cs) / n),
             "grasp_time_within_1s_%": round(100 * sum(c["grasps_matched_1s"] for c in cs) / max(1, sum(c["true_grasps"] for c in cs))),
             "delivery_right_%": round(100 * sum(c["delivered_said"] == c["delivered_true"] for c in cs) / n),
             "fault_said_%": round(100 * sum(c["fault_said"] for c in cs) / n),
             "miss_said_%": round(100 * sum(c["miss_said"] for c in cs) / n),
             "pull_said_%": round(100 * sum(c["pull_said"] for c in cs) / n),
             "pull_recall_%": round(100 * sum(c["pull_said"] and c["pull_true"] for c in cs) / max(1, sum(c["pull_true"] for c in cs))) if any(c["pull_true"] for c in cs) else None}
        rows[scen] = r
        for k in ("grasp_count_right", "delivered_said"): total[k] += sum(c[k] == (c["delivered_true"] if k == "delivered_said" else True) for c in cs)
        total["n"] += n
    (out_dir / "scores.json").write_text(json.dumps(rows, indent=1))
    print(f"{'scenario':18s} {'eps':>4s} {'grasp#':>7s} {'time±1s':>8s} {'deliver':>8s} {'fault':>6s} {'miss':>5s} {'pull':>5s}")
    for scen, r in rows.items():
        print(f"{scen:18s} {r['episodes']:4d} {r['grasp_count_right_%']:6d}% {r['grasp_time_within_1s_%']:7d}% "
              f"{r['delivery_right_%']:7d}% {r['fault_said_%']:5d}% {r['miss_said_%']:4d}% {r['pull_said_%']:4d}%")
    print(f"overall: grasp count right {100 * total['grasp_count_right'] / total['n']:.1f} %, "
          f"delivery right {100 * total['delivered_said'] / total['n']:.1f} % of {total['n']} episodes")


if __name__ == "__main__":
    main(pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "out")
