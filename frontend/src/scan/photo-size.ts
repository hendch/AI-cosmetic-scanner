// A full-resolution phone photo is 3-5 MB (4-7 MB once base64-encoded) and made n8n on Render run out of memory.
// 2000 px on the longest side still reads barcodes and ingredient lists, and is about 0.5 MB as a JPEG.
export const MAX_PHOTO_SIDE = 2000;
export const JPEG_QUALITY = 0.7;

export type ResizeTarget = { width: number | null; height: number | null };

/** The resize that brings the longest side down to MAX_PHOTO_SIDE (the other side follows the ratio),
 *  or null when the photo is already small enough. */
export function resizeFor(width: number, height: number): ResizeTarget | null {
  if (Math.max(width, height) <= MAX_PHOTO_SIDE) return null;
  return width >= height ? { width: MAX_PHOTO_SIDE, height: null } : { width: null, height: MAX_PHOTO_SIDE };
}
