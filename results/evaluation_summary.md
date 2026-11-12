# Distributed DNS-Like Name Resolution System — Evaluation

## Overview

This report summarizes the CSV measurements currently present in `results/`. Each CSV represents its own test run or scenario.

## Results by test file

| Test file | Records | Latency samples | Mean (ms) | Median (ms) | Min (ms) | Max (ms) |
|---|---:|---:|---:|---:|---:|---:|
| backup_test.csv | 3 | 3 | 1.821 | 2.151 | 0.658 | 2.653 |
| direct_test.csv | 3 | 3 | 0.955 | 0.805 | 0.502 | 1.558 |
| final_test.csv | 3 | 3 | 0.762 | 0.627 | 0.000 | 1.659 |
| lookups.csv | 10 | 10 | 410.196 | 1.643 | 0.000 | 2064.924 |
| sdn_test.csv | 1 | 1 | 3.168 | 3.168 | 3.168 | 3.168 |
| stage3_backup_test.csv | 6 | 6 | 1.367 | 1.248 | 0.403 | 2.321 |
| stage3_final_test.csv | 2 | 2 | 1.212 | 1.212 | 0.228 | 2.196 |
| stage3_primary_test.csv | 5 | 5 | 1.086 | 1.112 | 0.048 | 2.201 |
| stage3_test.csv | 2 | 2 | 1.558 | 1.558 | 0.664 | 2.452 |

## Lookup outcomes

- Non-empty CSV records counted: **35**
- Records marked `OK`: **30**
- Records marked `NOT_FOUND`: **5**
- Numeric latency measurements: **35**
- Mean latency across all available measurements: **118.140 ms**
- Median latency across all available measurements: **1.427 ms**
- Minimum latency: **0.000 ms**
- Maximum latency: **2064.924 ms**

## Interpretation

- The graph compares mean latency recorded in each CSV file.
- `NOT_FOUND` is a lookup outcome, not automatically a system failure; check whether the queried name was expected to exist.
- Test files may represent different domains, cache states, server selections, and network conditions. Their averages are descriptive and should not be treated as a controlled performance comparison.
- A low latency in a small sample does not establish overall system performance. Repeat each scenario under consistent conditions for a stronger comparison.
- CSV measurements alone do not prove automatic failover. Document the controller logs and successful lookup through the service address during the server-failure test separately.

## Suggested further tests

1. Compare cache miss and cache hit latency using repeated queries.
2. Stop the primary server and verify that requests succeed through the backup path.
3. Record the time between primary failure and successful backup resolution.
4. Repeat each scenario several times and report sample counts.
5. Restore the primary and document whether recovery requires manual intervention.

## Files

- `latency_by_test.png`: mean latency chart, when valid measurements are available.
- Source measurements: the individual CSV files in this directory.
