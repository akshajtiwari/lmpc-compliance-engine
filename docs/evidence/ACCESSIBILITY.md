# Workbench accessibility evidence

Status: automated WCAG 2.1 A/AA critical-path audit passed; manual review remains.

## Automated scope

The existing Chromium inspection E2E test runs axe-core 4.12.1 with the `wcag2a`,
`wcag2aa`, `wcag21a`, and `wcag21aa` rule tags at these populated application states:

1. unauthenticated login;
2. authenticated enforcement dashboard;
3. e-commerce scan detail with extracted declarations, findings and finalisation controls;
4. the per-finding rule explanation drawer.

The browser test still completes its functional path after the audits: create and analyse
an inspection, confirm the e-commerce rule subset, finalise a report and verify the PDF
download. A violation fails the same CI job. Axe result attachments, Playwright HTML and
failure diagnostics are uploaded as the `workbench-e2e-<run id>` artifact for 30 days.

## Findings and remediations — 2026-09-11

The first scan-detail audit found two violations:

| Finding | Remediation | Result |
|---|---|---|
| Extracted-declaration edit inputs had no programmatic labels | Bound each field name to its input with `label[for]` / `id`, and associated panel-confidence metadata with `aria-describedby` | Passed |
| `INCOMPLETE EVIDENCE` foreground contrast was 4.13:1 | Darkened the shared warning token from `#a56812` to `#925a0e`, producing approximately 5.14:1 on `#fff2dc` | Passed |

After remediation, all four audited states reported zero WCAG 2.1 A/AA violations. The
Workbench lint, TypeScript and production Next.js build also passed.

## What this does not prove

Automated analysis cannot establish complete WCAG conformance. Before pilot acceptance,
run keyboard-only navigation, visible-focus, zoom/reflow and screen-reader drills with the
real officer workflow. The rulepack approval screen named by Part 22 component 7 does not
exist yet, so it cannot be audited or accepted. Native Field app accessibility is a
separate device-test gate.
