import { describe, expect, it } from 'vitest';

import { MAX_PHOTO_SIDE, resizeFor } from '@/scan/photo-size';

describe('resizeFor', () => {
  it('shrinks a landscape photo, keeping the ratio', () => {
    expect(resizeFor(4032, 3024)).toEqual({ width: MAX_PHOTO_SIDE, height: 1500 });
  });

  it('shrinks a portrait photo, keeping the ratio', () => {
    expect(resizeFor(3024, 4032)).toEqual({ width: 1500, height: MAX_PHOTO_SIDE });
  });

  it('shrinks a square photo', () => {
    expect(resizeFor(3000, 3000)).toEqual({ width: MAX_PHOTO_SIDE, height: MAX_PHOTO_SIDE });
  });

  it('always gives both sides as whole numbers', () => {
    const size = resizeFor(4000, 2251)!;
    expect(Number.isInteger(size.width) && Number.isInteger(size.height)).toBe(true);
  });

  it('leaves a photo that is small enough alone', () => {
    expect(resizeFor(1600, 1200)).toBeNull();
    expect(resizeFor(MAX_PHOTO_SIDE, 1000)).toBeNull();
  });
});
