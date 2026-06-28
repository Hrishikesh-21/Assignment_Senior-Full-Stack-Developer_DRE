"use client";

import { useEffect, useRef } from "react";

/**
 * Calls `callback` immediately and then on a fixed interval, without
 * a full page reload. Used to satisfy the "auto refresh every 60
 * seconds, no page reload" requirement for both dashboard widgets.
 */
export function useAutoRefresh(callback: () => void, intervalMs: number) {
  const callbackRef = useRef(callback);
  callbackRef.current = callback;

  useEffect(() => {
    callbackRef.current();
    const id = setInterval(() => callbackRef.current(), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);
}
