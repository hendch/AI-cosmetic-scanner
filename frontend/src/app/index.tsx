import { router } from 'expo-router';
import { ArrowRightIcon, BarcodeIcon, ImageSquareIcon, ScanIcon } from 'phosphor-react-native';
import { useCallback, useState } from 'react';
import { Platform, Pressable, StyleSheet, TextInput, View } from 'react-native';

import { BarcodeCamera } from '@/components/barcode-camera';
import { Button, Radius, Screen, Txt } from '@/components/ui';
import { Spacing, Type } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import type { ScanInput } from '@/scan/client';
import { gtinProblem } from '@/scan/gtin';
import { pickImage } from '@/scan/pick-image';
import { useScan } from '@/scan/scan-context';

/** The dark viewfinder: the live camera on phones; on the web, a tap opens the camera or file picker. */
function Viewfinder({ onPress }: { onPress: () => void }) {
  const theme = useTheme();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel="Take a photo of the barcode"
      onPress={onPress}
      style={({ pressed }) => [styles.viewfinder, { backgroundColor: theme.ink }, pressed && styles.pressed]}>
      <View style={styles.target} />
      <View style={[styles.scanLine, { backgroundColor: theme.accent }]} />
      <Txt variant="small" style={styles.hint}>
        Point at the barcode
      </Txt>
    </Pressable>
  );
}

export default function ScanScreen() {
  const theme = useTheme();
  const { start } = useScan();
  const [manual, setManual] = useState(false);
  const [barcode, setBarcode] = useState('');
  const [barcodeError, setBarcodeError] = useState<string | null>(null);
  const [photoError, setPhotoError] = useState<string | null>(null);

  const begin = useCallback(
    (input: ScanInput) => {
      start(input);
      router.push('/progress');
    },
    [start],
  );

  const submitBarcode = () => {
    const problem = gtinProblem(barcode);
    setBarcodeError(problem);
    if (!problem) begin({ barcode: barcode.replace(/\s/g, '') });
  };

  const choosePhoto = async (source: 'camera' | 'library') => {
    setPhotoError(null);
    const result = await pickImage(source);
    if (!result) return;
    if ('problem' in result) setPhotoError(result.problem);
    else begin({ image: result.image });
  };

  return (
    <Screen>
      <View style={styles.brand}>
        <ScanIcon size={20} color={theme.accent} weight="bold" />
        <Txt variant="strong">Cosmetic Scanner</Txt>
      </View>

      <View style={styles.intro}>
        <Txt variant="display" accessibilityRole="header">
          What’s really in your cosmetics?
        </Txt>
        <Txt muted>Scan a barcode or snap the ingredient list. We check it against EU rules.</Txt>
      </View>

      {Platform.OS !== 'web' ? (
        <BarcodeCamera onScanned={(code) => begin({ barcode: code })} />
      ) : (
        <Viewfinder onPress={() => choosePhoto('camera')} />
      )}

      <View style={styles.actions}>
        <Button label="Scan barcode" icon={BarcodeIcon} onPress={() => choosePhoto('camera')} />
        <Button label="Upload a label photo" icon={ImageSquareIcon} kind="secondary" onPress={() => choosePhoto('library')} />
        {photoError && (
          <Txt variant="small" tone="prohibited" accessibilityRole="alert">
            {photoError}
          </Txt>
        )}

        {!manual ? (
          <Pressable accessibilityRole="button" onPress={() => setManual(true)} style={styles.link}>
            <Txt variant="small" muted>
              or type the number
            </Txt>
          </Pressable>
        ) : (
          <View style={styles.manual}>
            <Txt variant="small" muted nativeID="barcode-label">
              Barcode number
            </Txt>
            <View style={styles.inputRow}>
              <TextInput
                accessibilityLabelledBy="barcode-label"
                autoFocus
                value={barcode}
                onChangeText={(text) => {
                  setBarcode(text);
                  setBarcodeError(null);
                }}
                onSubmitEditing={submitBarcode}
                inputMode="numeric"
                returnKeyType="search"
                maxLength={16}
                style={[
                  styles.input,
                  Type.body,
                  { color: theme.text, backgroundColor: theme.surface, borderColor: barcodeError ? theme.prohibited : theme.line },
                ]}
              />
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="Check product"
                disabled={!barcode.trim()}
                onPress={submitBarcode}
                style={({ pressed }) => [styles.go, { backgroundColor: theme.accent, opacity: barcode.trim() ? 1 : 0.4 }, pressed && styles.pressed]}>
                <ArrowRightIcon size={20} color={theme.onAccent} weight="bold" />
              </Pressable>
            </View>
            {barcodeError ? (
              <Txt variant="small" tone="prohibited" accessibilityRole="alert">
                {barcodeError}
              </Txt>
            ) : (
              <Txt variant="small" muted>
                The 8 to 13 digits printed under the barcode.
              </Txt>
            )}
          </View>
        )}
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  brand: { flexDirection: 'row', alignItems: 'center', gap: Spacing.two },
  intro: { gap: Spacing.three },
  viewfinder: { height: 230, borderRadius: Radius.panel, alignItems: 'center', justifyContent: 'center', overflow: 'hidden' },
  target: { width: '42%', aspectRatio: 1.6, maxWidth: 220, borderWidth: 2, borderColor: '#FFFFFF', borderRadius: Radius.tile, opacity: 0.92 },
  scanLine: { position: 'absolute', left: '14%', right: '14%', height: 2 },
  hint: { position: 'absolute', bottom: Spacing.four, color: '#C9D2CF' },
  pressed: { transform: [{ scale: 0.98 }] },
  actions: { gap: Spacing.three },
  link: { alignSelf: 'center', paddingVertical: Spacing.two, paddingHorizontal: Spacing.four },
  manual: { gap: Spacing.two },
  inputRow: { flexDirection: 'row', gap: Spacing.two },
  input: { flex: 1, minHeight: 50, borderWidth: 1, borderRadius: Radius.control, paddingHorizontal: Spacing.four, letterSpacing: 1 },
  go: { width: 50, height: 50, borderRadius: Radius.pill, alignItems: 'center', justifyContent: 'center' },
});
