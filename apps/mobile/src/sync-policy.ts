export const RETRY_DELAYS_MS = [
  5_000,
  15_000,
  60_000,
  5 * 60_000,
  30 * 60_000,
  60 * 60_000,
] as const;

export function retryDelayMs(completedAttempts: number) {
  const index = Math.max(0, Math.min(Math.trunc(completedAttempts) - 1, RETRY_DELAYS_MS.length - 1));
  return RETRY_DELAYS_MS[index];
}

export function nextRetryAt(completedAttempts: number, fromMs = Date.now()) {
  return new Date(fromMs + retryDelayMs(completedAttempts)).toISOString();
}

export function isRetryDue(nextAttemptAt: string | null, nowMs = Date.now()) {
  if (!nextAttemptAt) return true;
  const timestamp = Date.parse(nextAttemptAt);
  return Number.isNaN(timestamp) || timestamp <= nowMs;
}

export class SingleFlight<TResult> {
  private active: Promise<TResult> | null = null;

  run(work: () => Promise<TResult>) {
    if (this.active) return this.active;
    const operation = work();
    this.active = operation;
    const clear = () => {
      if (this.active === operation) this.active = null;
    };
    operation.then(clear, clear);
    return operation;
  }
}

export type SequentialDrain<TResult> = {
  completed: TResult[];
  failures: unknown[];
  stopped: boolean;
};

export async function drainSequentially<TItem, TResult>(
  items: TItem[],
  worker: (item: TItem) => Promise<TResult>,
  stopAfterFailure: (cause: unknown) => boolean,
): Promise<SequentialDrain<TResult>> {
  const completed: TResult[] = [];
  const failures: unknown[] = [];
  for (const item of items) {
    try {
      completed.push(await worker(item));
    } catch (cause) {
      failures.push(cause);
      if (stopAfterFailure(cause)) return {completed, failures, stopped: true};
    }
  }
  return {completed, failures, stopped: false};
}
