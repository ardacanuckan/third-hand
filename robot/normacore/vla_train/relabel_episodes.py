"""Write copies of recorded episodes with a corrected task text (needs pyarrow). Originals stay untouched.

    python relabel_episodes.py --task "give me the blue glue stick" --slug blue-glue-stick \
        --out relabeled/ episodes/ep-*.parquet

Only the `task` column changes; schema, metadata, joints and images are copied as they are.
The policy only knows the exact wording it was trained on, so use the same text in the recorder and in
run_policy.py --task.
"""
import argparse
import pathlib
import re

import pyarrow as pa
import pyarrow.parquet as pq


def relabel(src: pathlib.Path, dst: pathlib.Path, task: str) -> tuple[set, int]:
    table = pq.read_table(src)
    old = set(table.column("task").to_pylist())
    i = table.schema.get_field_index("task")
    field = table.schema.field(i)
    new_col = pa.array([task] * table.num_rows, type=field.type)
    table = table.set_column(i, field, new_col)
    meta = pq.read_metadata(src)
    pq.write_table(table, dst, compression="zstd" if "ZSTD" in str(meta.row_group(0).column(0).compression) else "snappy")
    return old, table.num_rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("parquets", nargs="+", type=pathlib.Path)
    ap.add_argument("--task", required=True)
    ap.add_argument("--slug", required=True, help="replaces the old label in file names, e.g. blue-glue-stick")
    ap.add_argument("--out", type=pathlib.Path, required=True)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    for src in sorted(a.parquets):
        m = re.match(r"(ep-\d+)", src.stem)
        dst = a.out / f"{m.group(1) if m else src.stem}-{a.slug}.parquet"
        old, n = relabel(src, dst, a.task)
        print(f"{src.name} -> {dst.name}: {n} frames, task {sorted(old)} -> '{a.task}'")
