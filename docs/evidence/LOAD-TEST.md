# Inspection load-test evidence

Status: local smoke and eight-user engineering pilot profiles passed.

## What is exercised

Each virtual user authenticates through a managed local account and repeatedly performs
the real e-commerce inspection path:

1. upload a screenshot and its SHA-256 evidence digest;
2. run OCR, extraction and deterministic rule evaluation;
3. retrieve the resulting scan;
4. find it through repository search; and
5. read the enforcement dashboard summary.

This intentionally uses the PostgreSQL and durable local-filesystem deployment requested
for development. It does not claim S3/MinIO or multi-replica capacity.

## Automated gates

| Metric | Gate | Source |
|---|---:|---|
| Upload p95 | `< 2 s` | Build spec Part 3.3 |
| Upload-to-verdict p95 | `< 15 s` | SC-2 / Part 19.4 |
| Upload-to-verdict p99 | `< 40 s` | Part 19.4 |
| Repository detail/search/dashboard p95 | `< 2 s` | PostgreSQL search escalation threshold |
| HTTP failures | `0` | Reliability guard |
| Functional checks / failed inspection flows | `100%` / `0` | Prevent a fast broken path passing |

The test exits non-zero when any threshold fails. GitHub Actions retains the k6 JSON
summary, console output and API log for 30 days.

## Run locally

Start the local API with `make dev`, then run:

```bash
LMPC_LOAD_BASE_URL=http://127.0.0.1:8000 \
LMPC_LOAD_EMAIL=reviewer@local.invalid \
LMPC_LOAD_PASSWORD='<your local password>' \
make load-smoke
```

The smoke target uses two virtual users and a 15-second hold. For a deliberate larger
run, call k6 directly and set `LMPC_LOAD_VUS`, `LMPC_LOAD_RAMP`, and `LMPC_LOAD_HOLD`.

## Local smoke result — 2026-09-11

The two-VU smoke profile ran against PostgreSQL and the local filesystem object store on
the development machine.

| Result | Measured |
|---|---:|
| Completed inspection flows | 52 |
| Functional checks | 366 / 366 |
| HTTP / business-flow failures | 0 / 0 |
| Upload p95 | 205.73 ms |
| Upload-to-verdict p95 / p99 | 383.04 ms / 709.38 ms |
| Repository p95 | 172.57 ms |

All automated thresholds passed. This is harness validation, not SC-2 sign-off: the
listing screenshot is intentionally small and blank, while its pasted listing text drives
the e-commerce declarations. The physical four-panel workload and pilot concurrency still
require their own measured runs.

## CI pilot profile and limitation

Run the **Pilot Load Test** workflow manually. Its defaults are eight concurrent users,
a 15-second ramp, a 90-second hold and a 15-second ramp-down. Eight users is an explicit
initial engineering assumption because the project brief specifies service replicas but
does not specify simultaneous officers or inspections per minute. Replace it with the
department's observed concurrency/arrival model before pilot sign-off.

A green run proves the configured single-runner local deployment met the thresholds for
that profile. It is not evidence for multi-node, WAN, S3 or production-scale capacity.

## CI engineering-pilot result — 2026-09-11

[GitHub Actions run 34521270930](https://github.com/akshajtiwari/lmpc-compliance-engine/actions/runs/34521270930)
passed on commit `607f087` using the default eight-user profile.

| Result | Measured |
|---|---:|
| Completed inspection flows | 437 |
| HTTP requests | 2,187 |
| Functional checks | 3,061 / 3,061 |
| HTTP / business-flow failures | 0 / 0 |
| Upload p95 | 320.56 ms |
| Upload-to-verdict p95 / p99 | 1.71 s / 1.76 s |
| Repository p95 | 247.16 ms |

All thresholds passed. The workflow retained `summary.json`, the k6 console output and the
API log in artifact `pilot-load-34521270930` for 30 days. This closes implementation and
measurement of the initial e-commerce load profile; the department traffic model and the
four-panel physical-package profile remain required before capacity or SC-2 sign-off.
