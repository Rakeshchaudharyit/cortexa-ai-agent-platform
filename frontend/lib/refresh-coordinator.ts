/**
 * Single-flight refresh coordinator.
 *
 * Refresh-token rotation makes concurrent POSTs to /auth/refresh unsafe:
 * the second request presents an already-rotated token and can revoke the
 * whole family. Bootstrap (Strict Mode double-mount) and API 401 retries
 * must share one in-flight promise.
 */

type RefreshRunner<T> = () => Promise<T>;

let inFlight: Promise<unknown> | null = null;

export async function runSingleFlightRefresh<T>(runner: RefreshRunner<T>): Promise<T> {
  if (inFlight) {
    return inFlight as Promise<T>;
  }
  const pending = runner().finally(() => {
    if (inFlight === pending) {
      inFlight = null;
    }
  });
  inFlight = pending;
  return pending;
}

/** Test-only: clear any stuck in-flight handle between cases. */
export function resetRefreshCoordinatorForTests(): void {
  inFlight = null;
}

export function hasInFlightRefreshForTests(): boolean {
  return inFlight !== null;
}
