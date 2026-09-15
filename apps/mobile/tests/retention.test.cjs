const assert = require("node:assert/strict");
const test = require("node:test");
const {
  expiredEvidence, expiredReports, orphanedEvidence, referencedUris,
  DEFAULT_RETENTION_DAYS,
} = require("../.test-dist/retention.js");

const DAY = 86_400_000;
const NOW = Date.parse("2026-09-15T12:00:00Z");
const ago = (days) => new Date(NOW - days * DAY).toISOString();

function inspection(over = {}) {
  return {
    state: "COMPLETE", scan_id: "scan-1", synced_at: ago(90),
    draft_json: JSON.stringify({panels: [
      {uri: "file:///evidence/a.jpg", sha256: "aa"},
      {uri: "file:///evidence/b.jpg", sha256: "bb"},
    ]}),
    result_json: JSON.stringify({images: [{sha256: "aa"}, {sha256: "bb"}]}),
    ...over,
  };
}

test("an unsynced inspection is never touched", () => {
  for (const over of [{state: "QUEUED"}, {state: "FAILED"}, {scan_id: null},
                      {synced_at: null}]) {
    assert.deepEqual(expiredEvidence([inspection(over)], {now: NOW}), [],
      `state ${JSON.stringify(over)} must keep its evidence`);
  }
});

test("evidence inside the retention window stays", () => {
  const recent = inspection({synced_at: ago(DEFAULT_RETENTION_DAYS - 1)});
  assert.deepEqual(expiredEvidence([recent], {now: NOW}), []);
});

test("evidence is deleted only once the server confirms the same hashes", () => {
  assert.deepEqual(expiredEvidence([inspection()], {now: NOW}),
                   ["file:///evidence/a.jpg", "file:///evidence/b.jpg"]);

  // No cached result means no proof the server holds it.
  assert.deepEqual(expiredEvidence([inspection({result_json: null})], {now: NOW}), []);

  // The server acknowledged a different panel: keep the one it did not confirm.
  const partial = inspection({result_json: JSON.stringify({images: [{sha256: "aa"}]})});
  assert.deepEqual(expiredEvidence([partial], {now: NOW}), ["file:///evidence/a.jpg"]);
});

test("a truncated draft or result is skipped, never guessed at", () => {
  assert.deepEqual(expiredEvidence([inspection({draft_json: "{oops"})], {now: NOW}), []);
  assert.deepEqual(expiredEvidence([inspection({result_json: "{oops"})], {now: NOW}), []);
});

test("orphans are found by what drafts point at, not by filename", () => {
  // Every photograph is written under a fresh random UUID, so the filename says nothing
  // about which inspection owns it. This is also what catches a retake leak.
  const files = [
    {uri: "file:///evidence/a.jpg", size: 10, modifiedAt: NOW},
    {uri: "file:///evidence/superseded-retake.jpg", size: 10, modifiedAt: NOW},
  ];
  assert.deepEqual(orphanedEvidence(files, [inspection()]),
                   ["file:///evidence/superseded-retake.jpg"]);
});

test("a queued draft's files are never orphans", () => {
  const queued = inspection({state: "QUEUED", scan_id: null, synced_at: null});
  const files = [{uri: "file:///evidence/a.jpg", size: 10, modifiedAt: NOW}];
  assert.deepEqual(orphanedEvidence(files, [queued]), []);
  assert.equal(referencedUris([queued]).size, 2);
});

test("report downloads age out", () => {
  const files = [
    {uri: "r/old.pdf", size: 10, modifiedAt: NOW - 30 * DAY},
    {uri: "r/new.pdf", size: 10, modifiedAt: NOW - 1 * DAY},
  ];
  assert.deepEqual(expiredReports(files, {now: NOW}), ["r/old.pdf"]);
});

test("the report cache is trimmed oldest-first to its size cap", () => {
  const files = [
    {uri: "r/1.pdf", size: 60, modifiedAt: NOW - 3 * DAY},
    {uri: "r/2.pdf", size: 60, modifiedAt: NOW - 2 * DAY},
    {uri: "r/3.pdf", size: 60, modifiedAt: NOW - 1 * DAY},
  ];
  assert.deepEqual(expiredReports(files, {now: NOW, capBytes: 130}), ["r/1.pdf"]);
});

test("nothing to do on an empty phone", () => {
  assert.deepEqual(expiredReports([], {now: NOW}), []);
  assert.deepEqual(orphanedEvidence([], []), []);
  assert.deepEqual(expiredEvidence([], {now: NOW}), []);
});
