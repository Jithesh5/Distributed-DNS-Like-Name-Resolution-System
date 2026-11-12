import csv
import statistics
from pathlib import Path
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"

csv_files = sorted(RESULTS.glob("*.csv"))
summaries = []
all_latencies = []
total_records = 0
total_ok = 0
total_not_found = 0

for path in csv_files:
    rows = []

    try:
        with path.open(newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                print(f"Skipping {path.name}: no CSV header")
                continue

            for row in reader:
                # Ignore completely empty rows.
                if not any(str(v or "").strip() for v in row.values()):
                    continue
                rows.append(row)
    except (OSError, csv.Error) as e:
        print(f"Skipping {path.name}: {e}")
        continue

    if not rows:
        print(f"Skipping {path.name}: no data rows")
        continue

    headers = {
        h.strip().lower(): h
        for h in (rows[0].keys() or [])
        if h
    }

    latency_key = next(
        (headers[k] for k in ("latency_ms", "latency", "latency (ms)")
         if k in headers),
        None,
    )
    status_key = next(
        (headers[k] for k in ("status", "result", "lookup_status")
         if k in headers),
        None,
    )
    source_key = next(
        (headers[k] for k in ("source", "server", "lookup_source")
         if k in headers),
        None,
    )

    latencies = []
    for row in rows:
        if latency_key:
            try:
                value = float(row[latency_key])
                if value >= 0:
                    latencies.append(value)
            except (ValueError, TypeError):
                pass

    statuses = {}
    sources = {}

    for row in rows:
        if status_key:
            value = (row.get(status_key) or "").strip().upper()
            if value:
                statuses[value] = statuses.get(value, 0) + 1

        if source_key:
            value = (row.get(source_key) or "").strip()
            if value:
                sources[value] = sources.get(value, 0) + 1

    record = {
        "file": path.name,
        "records": len(rows),
        "latencies": latencies,
        "mean": statistics.mean(latencies) if latencies else None,
        "median": statistics.median(latencies) if latencies else None,
        "minimum": min(latencies) if latencies else None,
        "maximum": max(latencies) if latencies else None,
        "statuses": statuses,
        "sources": sources,
    }
    summaries.append(record)

    total_records += len(rows)
    total_ok += statuses.get("OK", 0)
    total_not_found += statuses.get("NOT_FOUND", 0)
    all_latencies.extend(latencies)

    print(
        f"{path.name}: records={len(rows)}, "
        f"latency_samples={len(latencies)}, "
        f"mean_ms={record['mean'] if record['mean'] is not None else 'N/A'}"
    )

if not summaries:
    raise SystemExit("No usable CSV files found in results/.")

# Plot mean latency per CSV file, using only files with numeric measurements.
plot_data = [s for s in summaries if s["mean"] is not None]

if plot_data:
    labels = [s["file"].removesuffix(".csv") for s in plot_data]
    means = [s["mean"] for s in plot_data]

    fig, ax = plt.subplots(figsize=(11, 6))
    bars = ax.bar(labels, means)
    ax.set_title("Mean Lookup Latency by Test File")
    ax.set_xlabel("Test CSV")
    ax.set_ylabel("Mean latency (ms)")
    ax.tick_params(axis="x", labelrotation=35)
    ax.bar_label(bars, fmt="%.2f ms", padding=3)
    fig.tight_layout()

    graph_path = RESULTS / "latency_by_test.png"
    fig.savefig(graph_path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    print(f"\nGraph saved: {graph_path}")
else:
    print("No valid latency measurements found; graph was not generated.")

def fmt(value):
    return f"{value:.3f}" if value is not None else "N/A"

lines = [
    "# Distributed DNS-Like Name Resolution System — Evaluation",
    "",
    "## Overview",
    "",
    "This report summarizes the CSV measurements currently present in "
    "`results/`. Each CSV represents its own test run or scenario.",
    "",
    "## Results by test file",
    "",
    "| Test file | Records | Latency samples | Mean (ms) | Median (ms) | Min (ms) | Max (ms) |",
    "|---|---:|---:|---:|---:|---:|---:|",
]

for s in summaries:
    lines.append(
        f"| {s['file']} | {s['records']} | {len(s['latencies'])} | "
        f"{fmt(s['mean'])} | {fmt(s['median'])} | "
        f"{fmt(s['minimum'])} | {fmt(s['maximum'])} |"
    )

lines.extend([
    "",
    "## Lookup outcomes",
    "",
    f"- Non-empty CSV records counted: **{total_records}**",
    f"- Records marked `OK`: **{total_ok}**",
    f"- Records marked `NOT_FOUND`: **{total_not_found}**",
    f"- Numeric latency measurements: **{len(all_latencies)}**",
])

if all_latencies:
    lines.extend([
        f"- Mean latency across all available measurements: "
        f"**{statistics.mean(all_latencies):.3f} ms**",
        f"- Median latency across all available measurements: "
        f"**{statistics.median(all_latencies):.3f} ms**",
        f"- Minimum latency: **{min(all_latencies):.3f} ms**",
        f"- Maximum latency: **{max(all_latencies):.3f} ms**",
    ])

lines.extend([
    "",
    "## Interpretation",
    "",
    "- The graph compares mean latency recorded in each CSV file.",
    "- `NOT_FOUND` is a lookup outcome, not automatically a system failure; "
    "check whether the queried name was expected to exist.",
    "- Test files may represent different domains, cache states, server "
    "selections, and network conditions. Their averages are descriptive "
    "and should not be treated as a controlled performance comparison.",
    "- A low latency in a small sample does not establish overall system "
    "performance. Repeat each scenario under consistent conditions for a "
    "stronger comparison.",
    "- CSV measurements alone do not prove automatic failover. Document "
    "the controller logs and successful lookup through the service address "
    "during the server-failure test separately.",
    "",
    "## Suggested further tests",
    "",
    "1. Compare cache miss and cache hit latency using repeated queries.",
    "2. Stop the primary server and verify that requests succeed through "
    "the backup path.",
    "3. Record the time between primary failure and successful backup "
    "resolution.",
    "4. Repeat each scenario several times and report sample counts.",
    "5. Restore the primary and document whether recovery requires manual "
    "intervention.",
    "",
    "## Files",
    "",
    "- `latency_by_test.png`: mean latency chart, when valid measurements "
    "are available.",
    "- Source measurements: the individual CSV files in this directory.",
    "",
])

report_path = RESULTS / "evaluation_summary.md"
report_path.write_text("\n".join(lines), encoding="utf-8")
print(f"Report saved: {report_path}")
