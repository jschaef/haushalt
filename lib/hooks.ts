"use client";

import { useCallback, useEffect, useRef, useState } from "react";

// Loads data on mount and whenever `key` changes; reload() refetches.
// Answers of outdated requests are dropped.
export function useData<T>(load: () => Promise<T>, key: string) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(true);
  const generation = useRef(0);
  const loadRef = useRef(load);
  useEffect(() => {
    loadRef.current = load;
  });

  const reload = useCallback(async () => {
    const mine = ++generation.current;
    setLoading(true);
    try {
      const result = await loadRef.current();
      if (mine === generation.current) {
        setData(result);
        setError(null);
      }
    } catch (err) {
      if (mine === generation.current) setError(err as Error);
    } finally {
      if (mine === generation.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- fetch on key change
    void reload();
  }, [key, reload]);

  return { data, error, loading, reload, setData };
}

// short vibration on supporting phones (Android); a no-op elsewhere
export function haptic(pattern: number | number[] = 12) {
  if (typeof navigator !== "undefined" && "vibrate" in navigator) navigator.vibrate(pattern);
}
