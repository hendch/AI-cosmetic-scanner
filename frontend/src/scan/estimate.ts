// n8n answers once, at the end, so the app cannot know which step is running. While the scan runs,
// the step list follows typical timings measured on real scans (eval/scenarios/2026-10-18_1511):
// the product lookup takes 1-2 s from a barcode and about 8 s from a label photo (OCR); the
// regulatory agent most of the rest; the validator the last few seconds. The last step stays
// "running" until the real answer arrives, so the list never claims the scan is done before it is.
import { useEffect, useState } from 'react';

import type { StageId } from './stages';

/** Seconds after the start at which each step typically begins. */
const FROM_BARCODE: [StageId, number][] = [['product', 0], ['regulatory', 2], ['toxicology', 10], ['ethics', 11], ['report', 12], ['validation', 13]];
const FROM_PHOTO: [StageId, number][] = [['product', 0], ['regulatory', 9], ['toxicology', 17], ['ethics', 18], ['report', 19], ['validation', 20]];

/** A free Render service that was asleep needs about a minute to wake up. */
export const SLOW_AFTER_SECONDS = 45;

export function estimatedStage(seconds: number, fromPhoto: boolean): StageId {
  const steps = fromPhoto ? FROM_PHOTO : FROM_BARCODE;
  let current = steps[0][0];
  for (const [id, start] of steps) if (seconds >= start) current = id;
  return current;
}

/** Whole seconds since `running` became true; resets when a new scan starts. */
export function useElapsedSeconds(running: boolean): number {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    if (!running) return;
    const started = Date.now();
    const timer = setInterval(() => setSeconds(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => {
      clearInterval(timer);
      setSeconds(0); // ready for the next scan
    };
  }, [running]);
  return seconds;
}
