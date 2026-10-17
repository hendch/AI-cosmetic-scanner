import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from 'react';

import { runScan, type ScanInput, type ScanOutcome } from './client';

type ScanState = {
  input: ScanInput | null;
  running: boolean;
  stage: string | null; // last step n8n reported, null if none
  outcome: ScanOutcome | null;
};

type ScanContextValue = ScanState & {
  start: (input: ScanInput) => void;
  cancel: () => void;
  reset: () => void;
};

const EMPTY: ScanState = { input: null, running: false, stage: null, outcome: null };
const ScanContext = createContext<ScanContextValue | null>(null);

export function ScanProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<ScanState>(EMPTY);
  const controller = useRef<AbortController | null>(null);

  const start = useCallback((input: ScanInput) => {
    controller.current?.abort();
    const abort = new AbortController();
    controller.current = abort;
    setState({ input, running: true, stage: null, outcome: null });

    runScan(input, (stage) => setState((s) => ({ ...s, stage })), abort.signal)
      .then((outcome) => setState((s) => ({ ...s, running: false, outcome })))
      .catch((err: Error) => {
        if (err.name === 'AbortError') return;
        setState((s) => ({ ...s, running: false, outcome: { kind: 'error', message: err.message } }));
      });
  }, []);

  const cancel = useCallback(() => {
    controller.current?.abort();
    setState((s) => ({ ...s, running: false }));
  }, []);

  const reset = useCallback(() => {
    controller.current?.abort();
    setState(EMPTY);
  }, []);

  return <ScanContext.Provider value={{ ...state, start, cancel, reset }}>{children}</ScanContext.Provider>;
}

export function useScan() {
  const value = useContext(ScanContext);
  if (!value) throw new Error('useScan must be used inside ScanProvider');
  return value;
}
