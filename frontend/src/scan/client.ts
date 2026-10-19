// Talks to the n8n scan webhook (docs/N8N_SETUP.md). One request, one answer: n8n replies when the
// whole pipeline has run (product lookup or label OCR, three agents, report, validator).
import { ReportSchema, type Report } from '@/report/schema';

export type PickedImage = { uri: string; base64: string; mimeType: string };
export type ScanInput = { barcode?: string; image?: PickedImage };

export type ScanOutcome =
  | { kind: 'report'; report: Report; status: 'completed' | 'needs_review' }
  | { kind: 'needs_input'; message: string }
  | { kind: 'error'; message: string };

/** Called when the scan starts. `stage` is null: n8n does not report individual steps. */
export type ProgressListener = (stage: string | null) => void;

const SCAN_URL = process.env.EXPO_PUBLIC_SCAN_URL ?? '';
const WEBHOOK_KEY = process.env.EXPO_PUBLIC_WEBHOOK_KEY ?? '';
// A sleeping free API on Render needs about a minute to wake up, on top of the scan itself.
const TIMEOUT_MS = 180_000;

const LABEL_PHOTO_MESSAGE =
  'This product has no ingredient list in the product database. Take a photo of the ingredient list on the back of the product.';

type PublicResult = {
  status: string;
  report?: unknown;
  next_action?: { message?: string } | null;
  error?: { code?: string; message?: string } | null;
};

function toOutcome(result: PublicResult): ScanOutcome {
  switch (result.status) {
    case 'completed':
    case 'needs_review': {
      const parsed = ReportSchema.safeParse(result.report);
      if (parsed.success) return { kind: 'report', report: parsed.data, status: result.status };
      const where = parsed.error.issues[0]?.path.join('.') || 'report';
      return { kind: 'error', message: `The report doesn't match the expected format (first problem at "${where}").` };
    }
    case 'needs_input':
      return { kind: 'needs_input', message: result.next_action?.message ?? LABEL_PHOTO_MESSAGE };
    case 'unauthorized':
      return { kind: 'error', message: 'The app is not allowed to use the scanner service (wrong EXPO_PUBLIC_WEBHOOK_KEY).' };
    default:
      return { kind: 'error', message: result.error?.message ?? `The scan stopped with status "${result.status}".` };
  }
}

function dataUri(image: PickedImage): string {
  return `data:${image.mimeType || 'image/jpeg'};base64,${image.base64}`;
}

export async function runScan(input: ScanInput, onProgress: ProgressListener, signal?: AbortSignal): Promise<ScanOutcome> {
  if (!SCAN_URL) return { kind: 'error', message: 'The app is not connected to a scanner service. Set EXPO_PUBLIC_SCAN_URL in frontend/.env.' };
  onProgress(null);

  // A photo may show the barcode or the ingredient list: the API tries the barcode first, then reads the label.
  // Sent once (image_ref), not in both barcode_image_ref and label_image_ref: n8n keeps every copy in memory.
  const photo = input.image ? dataUri(input.image) : null;
  const timeout = AbortSignal.timeout(TIMEOUT_MS);
  const combined = signal ? AbortSignal.any([signal, timeout]) : timeout;

  let response: Response;
  try {
    response = await fetch(SCAN_URL, {
      method: 'POST',
      signal: combined,
      headers: { 'Content-Type': 'application/json', 'X-API-Key': WEBHOOK_KEY },
      body: JSON.stringify({ barcode: input.barcode ?? null, image_ref: photo }),
    });
  } catch (err) {
    if (signal?.aborted) throw err; // the user cancelled
    if (timeout.aborted) return { kind: 'error', message: 'The scanner service took too long to answer. Try again in a minute.' };
    return {
      kind: 'error',
      message: `Couldn't reach the scanner service at ${SCAN_URL}. Check your connection; a local n8n must be on the same network.`,
    };
  }
  if (!response.ok) return { kind: 'error', message: `The scanner service answered with HTTP ${response.status}.` };
  try {
    return toOutcome((await response.json()) as PublicResult);
  } catch {
    return { kind: 'error', message: 'The scanner service sent an answer the app could not read.' };
  }
}
