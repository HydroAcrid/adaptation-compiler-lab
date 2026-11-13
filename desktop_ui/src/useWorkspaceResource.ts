import { useCallback, useRef, useState } from "react";

import { normalizeEngineFailure, type EngineClientFailure } from "./engine";

interface ResourceState<T> {
  data: T | null;
  error: EngineClientFailure | null;
  loading: boolean;
}

export function useWorkspaceResource<T>(load: () => Promise<T>) {
  const request = useRef(0);
  const [state, setState] = useState<ResourceState<T>>({
    data: null,
    error: null,
    loading: false,
  });

  const read = useCallback(
    async (loader = load) => {
      const id = ++request.current;
      setState((current) => ({ ...current, loading: true }));
      try {
        const data = await loader();
        if (id === request.current) {
          setState({ data, error: null, loading: false });
        }
      } catch (error) {
        if (id === request.current) {
          setState((current) => ({
            ...current,
            error: normalizeEngineFailure(error),
            loading: false,
          }));
        }
        throw error;
      }
    },
    [load],
  );

  return { ...state, read };
}
