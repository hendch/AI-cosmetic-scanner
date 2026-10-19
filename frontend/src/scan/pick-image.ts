import { ImageManipulator, SaveFormat } from 'expo-image-manipulator';
import * as ImagePicker from 'expo-image-picker';
import { Platform } from 'react-native';

import type { PickedImage } from './client';
import { JPEG_QUALITY, resizeFor, type ResizeTarget } from './photo-size';

export type PickResult = { image: PickedImage } | { problem: string } | null; // null: user cancelled

// No base64 from the picker: the photo is shrunk first, then encoded once (see photo-size.ts).
const OPTIONS: ImagePicker.ImagePickerOptions = { mediaTypes: ['images'], quality: 1 };

/** Must be called straight from a button press, or browsers block it. */
export async function pickImage(source: 'camera' | 'library'): Promise<PickResult> {
  if (source === 'camera' && Platform.OS !== 'web') {
    const permission = await ImagePicker.requestCameraPermissionsAsync();
    if (!permission.granted) return { problem: 'Camera access is off. Allow it in your phone settings, or upload a photo instead.' };
  }
  const result =
    source === 'camera' ? await ImagePicker.launchCameraAsync(OPTIONS) : await ImagePicker.launchImageLibraryAsync(OPTIONS);
  if (result.canceled || !result.assets?.length) return null;

  const asset = result.assets[0];
  try {
    const base64 = await shrink(asset);
    if (!base64) return { problem: "That photo couldn't be read. Try another one." };
    return { image: { uri: asset.uri, base64, mimeType: 'image/jpeg' } };
  } catch {
    return { problem: "That photo couldn't be read. Try another one." };
  }
}

/** Longest side down to MAX_PHOTO_SIDE, saved as JPEG; returns raw base64 (no data: prefix). */
async function shrink(asset: ImagePicker.ImagePickerAsset): Promise<string | undefined> {
  const context = ImageManipulator.manipulate(asset.uri);
  let size: ResizeTarget | null;
  if (asset.width > 0 && asset.height > 0) {
    size = resizeFor(asset.width, asset.height);
  } else {
    // Some web browsers do not report the size: read it from the decoded image.
    const decoded = await context.renderAsync();
    size = resizeFor(decoded.width, decoded.height);
  }
  if (size) context.resize(size);
  const image = await context.renderAsync();
  const saved = await image.saveAsync({ format: SaveFormat.JPEG, compress: JPEG_QUALITY, base64: true });
  return saved.base64;
}
