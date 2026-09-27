import { useCallback, useState } from "react";

/**
 * Minimal async-state helper standardizing loading/error handling around a
 * single async call. Keeps UI state (status/error) separate from server data,
 * which callers store themselves. No caching, no library.
 */
export type AsyncStatus = "idle" | "loading" | "success" | "error";

export interface UseAsyncResult {
  status: AsyncStatus;
  error: unknown;
  isLoading: boolean;
  /** Run an async operation, tracking status/error. Returns the result or undefined on failure. */
  run: <T>(operation: () => Promise<T>) => Promise<T | undefined>;
  reset: () => void;
}

export function useAsync(): UseAsyncResult {
  const [status, setStatus] = useState<AsyncStatus>("idle");
  const [error, setError] = useState<unknown>(null);

  const run = useCallback(
    async <T>(operation: () => Promise<T>): Promise<T | undefined> => {
      setStatus("loading");
      setError(null);
      try {
        const result = await operation();
        setStatus("success");
        return result;
      } catch (err) {
        setError(err);
        setStatus("error");
        return undefined;
      }
    },
    [],
  );

  const reset = useCallback(() => {
    setStatus("idle");
    setError(null);
  }, []);

  return { status, error, isLoading: status === "loading", run, reset };
}
