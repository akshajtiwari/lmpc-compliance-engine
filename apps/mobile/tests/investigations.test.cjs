const assert = require("node:assert/strict");
const test = require("node:test");
const {summarise} = require("../.test-dist/investigations.js");

function row(over) {
  return {
    client_uuid: Math.random().toString(36).slice(2), scan_id: "s", captured_at: "2026-09-15",
    category: "FOOD", overall: null, state: "COMPLETE", error: null, draft_json: "{}",
    attempts: 0, next_attempt_at: null, last_attempt_at: null, synced_at: null,
    account_id: "a", server_fingerprint: "f", updated_at: "", investigation_id: "i",
    captured_ts: "2026-09-15T10:00:00Z", result_json: null, result_fetched_at: null,
    remarks: null, ...over,
  };
}
const report = (...checks) => JSON.stringify({
  evaluations: checks.map((check) => ({check, outcome: "FAIL"})),
});

test("an empty folder counts nothing", () => {
  assert.deepEqual(summarise([]), {
    total: 0, compliant: 0, failing: 0, unclear: 0, pending: 0,
    evaluated: 0, withReports: 0, topViolations: [],
  });
});

test("verdicts land in the right bucket", () => {
  const stats = summarise([
    row({overall: "COMPLIANT"}),
    row({overall: "NON_COMPLIANT"}),
    row({overall: "NON_COMPLIANT"}),
    row({overall: "INCOMPLETE_EVIDENCE"}),
    row({overall: "OUT_OF_SCOPE"}),
  ]);
  assert.equal(stats.total, 5);
  assert.equal(stats.compliant, 1);
  assert.equal(stats.failing, 2);
  assert.equal(stats.unclear, 2, "anything not pass/fail is unclear, never silently a pass");
  assert.equal(stats.evaluated, 5);
});

test("a scan still uploading is pending, not evaluated", () => {
  const stats = summarise([row({state: "QUEUED", overall: null}),
                           row({state: "FAILED", overall: null}),
                           row({state: "COMPLETE", overall: "COMPLIANT"})]);
  assert.equal(stats.pending, 2);
  assert.equal(stats.evaluated, 1);
  assert.equal(stats.total, 3);
});

test("violations are ranked, ties broken by name so the order is stable", () => {
  const stats = summarise([
    row({overall: "NON_COMPLIANT", result_json: report("R8-CLEAR-SPACE", "R6-MRP")}),
    row({overall: "NON_COMPLIANT", result_json: report("R8-CLEAR-SPACE", "R6-CARE")}),
    row({overall: "NON_COMPLIANT", result_json: report("R8-CLEAR-SPACE")}),
  ]);
  assert.deepEqual(stats.topViolations, [
    {check: "R8-CLEAR-SPACE", count: 3},
    {check: "R6-CARE", count: 1},
    {check: "R6-MRP", count: 1},
  ]);
});

test("only the top three are reported", () => {
  const stats = summarise([row({
    overall: "NON_COMPLIANT", result_json: report("A", "B", "C", "D", "E"),
  })]);
  assert.equal(stats.topViolations.length, 3);
});

test("passing checks never count as violations", () => {
  const stats = summarise([row({
    overall: "COMPLIANT",
    result_json: JSON.stringify({evaluations: [
      {check: "R6-MRP", outcome: "PASS"},
      {check: "R7-HEIGHT", outcome: "NOT_APPLICABLE"},
      {check: "R8-CLEAR", outcome: "INDETERMINATE"},
    ]}),
  })]);
  assert.deepEqual(stats.topViolations, []);
});

test("the denominator tells the truth about how many reports were read", () => {
  // Under-reporting violations without saying so would be a lie in a legal-evidence app.
  const stats = summarise([
    row({overall: "NON_COMPLIANT", result_json: report("R6-MRP")}),
    row({overall: "NON_COMPLIANT", result_json: null}),
    row({overall: "NON_COMPLIANT", result_json: null}),
  ]);
  assert.equal(stats.failing, 3);
  assert.equal(stats.withReports, 1, "3 failing, but only 1 report was on the phone");
});

test("a truncated cache is skipped, not fatal", () => {
  const stats = summarise([
    row({overall: "NON_COMPLIANT", result_json: '{"evaluations":[{"check":'}),
    row({overall: "NON_COMPLIANT", result_json: report("R6-MRP")}),
  ]);
  assert.equal(stats.withReports, 1);
  assert.deepEqual(stats.topViolations, [{check: "R6-MRP", count: 1}]);
});
