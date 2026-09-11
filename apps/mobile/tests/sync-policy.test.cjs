const assert = require("node:assert/strict");
const test = require("node:test");
const {
  RETRY_DELAYS_MS,
  SingleFlight,
  drainSequentially,
  isRetryDue,
  nextRetryAt,
  retryDelayMs,
} = require("../.test-dist/sync-policy.js");

test("retry policy follows the specified schedule and then stays hourly", () => {
  assert.deepEqual(RETRY_DELAYS_MS, [5_000, 15_000, 60_000, 300_000, 1_800_000, 3_600_000]);
  assert.equal(retryDelayMs(1), 5_000);
  assert.equal(retryDelayMs(5), 1_800_000);
  assert.equal(retryDelayMs(6), 3_600_000);
  assert.equal(retryDelayMs(99), 3_600_000);
  assert.equal(nextRetryAt(2, Date.parse("2026-09-11T10:00:00.000Z")), "2026-09-11T10:00:15.000Z");
});

test("retry due check treats missing and corrupt timestamps as recoverable", () => {
  const now = Date.parse("2026-09-11T10:00:00.000Z");
  assert.equal(isRetryDue(null, now), true);
  assert.equal(isRetryDue("not-a-date", now), true);
  assert.equal(isRetryDue("2026-09-11T09:59:59.000Z", now), true);
  assert.equal(isRetryDue("2026-09-11T10:00:01.000Z", now), false);
});

test("sequential drain completes every item and isolates record failures", async () => {
  const seen = [];
  const result = await drainSequentially(
    [1, 2, 3],
    async (item) => {
      seen.push(item);
      if (item === 2) throw new Error("bad record");
      return item * 10;
    },
    () => false,
  );
  assert.deepEqual(seen, [1, 2, 3]);
  assert.deepEqual(result.completed, [10, 30]);
  assert.equal(result.failures.length, 1);
  assert.equal(result.stopped, false);
});

test("sequential drain stops after a connection failure", async () => {
  const seen = [];
  const result = await drainSequentially(
    [1, 2, 3],
    async (item) => {
      seen.push(item);
      if (item === 2) throw new TypeError("network down");
      return item;
    },
    (cause) => cause instanceof TypeError,
  );
  assert.deepEqual(seen, [1, 2]);
  assert.equal(result.stopped, true);
});

test("single-flight callers share one operation and can run again after settlement", async () => {
  const flight = new SingleFlight();
  let calls = 0;
  let release;
  const first = flight.run(() => {
    calls += 1;
    return new Promise((resolve) => { release = resolve; });
  });
  const concurrent = flight.run(async () => 99);
  assert.equal(first, concurrent);
  assert.equal(calls, 1);
  release(42);
  assert.equal(await first, 42);
  assert.equal(await flight.run(async () => { calls += 1; return 7; }), 7);
  assert.equal(calls, 2);
});
