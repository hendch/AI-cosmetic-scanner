import * as ImagePicker from 'expo-image-picker';
import { Platform } from 'react-native';

import type { PickedImage } from './client';

export type PickResult = { image: PickedImage } | { problem: string } | null; // null: user cancelled

const OPTIONS: ImagePicker.ImagePickerOptions = { mediaTypes: ['images'], quality: 0.7, base64: true };

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
  // On web the uri is already a data URI; native gives base64 separately.
  const base64 = asset.base64 ?? asset.uri.match(/^data:[^;]+;base64,(.*)$/)?.[1];
  if (!base64) return { problem: "That photo couldn't be read. Try another one." };
  return { image: { uri: asset.uri, base64, mimeType: asset.mimeType ?? 'image/jpeg' } };
}
