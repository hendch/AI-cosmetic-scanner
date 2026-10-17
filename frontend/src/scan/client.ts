import { ReportSchema, type Report } from '@/report/schema';

export type PickedImage = { uri: string; base64: string; mimeType: string };
export type ScanInput = { barcode?: string; image?: PickedImage };

export type ScanOutcome =
  | { kind: 'completed'; report: Report }
  | { kind: 'needs_input'; message: string }
  | { kind: 'needs_review'; message: string; issues: string[] }
  | { kind: 'error'; message: string };

/** Called whenever n8n reports progress. `stage` is null when n8n does not report steps. */
export type ProgressListener = (stage: string | null) => void;

const SCAN_URL = process.env.EXPO_PUBLIC_SCAN_URL ?? '';
const STATUS_URL = process.env.EXPO_PUBLIC_STATUS_URL ?? '';
const API_KEY = process.env.EXPO_PUBLIC_API_KEY ?? '';
const POLL_MS = 1500;

const LABEL_PHOTO_MESSAGE =
  'This barcode has no ingredient list in the product database. Take a photo of the ingredient list on the back of the product.';

// What n8n returns: the final public result, or {request_id, status: "running", stage} while it works.
type PublicResult = {
  request_id?: string;
  status: string;
  stage?: string | null;
  report?: unknown;
  next_action?: { message?: string } | null;
  error?: { code?: string; message?: string } | null;
  validation?: { issues?: string[]; checks?: { passed: boolean; issues: string[] }[] } | null;
};

class ServiceError extends Error {}

function sleep(ms: number, signal?: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const timer = setTimeout(resolve, ms);
    signal?.addEventListener('abort', () => {
      clearTimeout(timer);
      reject(new DOMException('Scan cancelled', 'AbortError'));
    });
  });
}

async function call(url: string, init: RequestInit): Promise<PublicResult> {
  let response: Response;
  try {
    response = await fetch(url, { ...init, headers: { 'Content-Type': 'application/json', 'X-API-Key': API_KEY } });
  } catch (err) {
    if ((err as Error).name === 'AbortError') throw err;
    throw new ServiceError(
      `Couldn't reach the scanner service at ${url}. Check that n8n is running and that this device is on the same network.`,
    );
  }
  if (!response.ok) throw new ServiceError(`The scanner service answered with HTTP ${response.status}.`);
  return (await response.json()) as PublicResult;
}

function toOutcome(result: PublicResult): ScanOutcome {
  switch (result.status) {
    case 'completed': {
      const parsed = ReportSchema.safeParse(result.report);
      if (parsed.success) return { kind: 'completed', report: parsed.data };
      const where = parsed.error.issues[0]?.path.join('.') || 'report';
      return { kind: 'error', message: `The report doesn't match the expected format (first problem at "${where}").` };
    }
    case 'needs_input':
      return { kind: 'needs_input', message: result.next_action?.message ?? LABEL_PHOTO_MESSAGE };
    case 'needs_review': {
      const v = result.validation;
      const issues = v?.issues ?? v?.checks?.filter((c) => !c.passed).flatMap((c) => c.issues) ?? [];
      return {
        kind: 'needs_review',
        message: result.error?.message ?? 'Some findings could not be backed by the evidence, so the report was held back.',
        issues,
      };
    }
    default:
      return { kind: 'error', message: result.error?.message ?? `The scan stopped with status "${result.status}".` };
  }
}

export async function runScan(input: ScanInput, onProgress: ProgressListener, signal?: AbortSignal): Promise<ScanOutcome> {
  if (!SCAN_URL) return { kind: 'error', message: 'The app is not connected to a scanner service. Set EXPO_PUBLIC_SCAN_URL in frontend/.env.' };

  try {
    onProgress(null);
    let result = await call(SCAN_URL, {
      method: 'POST',
      signal,
      body: JSON.stringify({
        barcode: input.barcode ?? null,
        label_image_base64: input.image?.base64 ?? null,
        label_image_mime: input.image?.mimeType ?? null,
        market: 'EU',
        assessment_date: new Date().toISOString().slice(0, 10),
      }),
    });

    // Asynchronous mode: n8n answered straight away and keeps working; follow its progress.
    while (result.status === 'running') {
      onProgress(result.stage ?? null);
      if (!STATUS_URL || !result.request_id) {
        return { kind: 'error', message: 'The scan started, but the app has no EXPO_PUBLIC_STATUS_URL to follow it.' };
      }
      await sleep(POLL_MS, signal);
      result = await call(`${STATUS_URL}?request_id=${encodeURIComponent(result.request_id)}`, { method: 'GET', signal });
    }
    return toOutcome(result);
  } catch (err) {
    if (err instanceof ServiceError) return { kind: 'error', message: err.message };
    throw err;
  }
}
