import { describe, expect, it } from 'vitest';

import { MAX_PHOTO_SIDE, resizeFor } from '@/scan/photo-size';

describe('resizeFor', () => {
  it('shrinks the width of a landscape photo', () => {
    expect(resizeFor(4032, 3024)).toEqual({ width: MAX_PHOTO_SIDE, height: null });
  });

  it('shrinks the height of a portrait photo', () => {
    expect(resizeFor(3024, 4032)).toEqual({ width: null, height: MAX_PHOTO_SIDE });
  });

  it('shrinks a square photo by its width', () => {
    expect(resizeFor(3000, 3000)).toEqual({ width: MAX_PHOTO_SIDE, height: null });
  });

  it('leaves a photo that is small enough alone', () => {
    expect(resizeFor(1600, 1200)).toBeNull();
    expect(resizeFor(MAX_PHOTO_SIDE, 1000)).toBeNull();
  });
});
