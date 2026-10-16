import { router } from 'expo-router';
import { CameraIcon, ImageSquareIcon, MagnifyingGlassIcon } from 'phosphor-react-native';
import { useCallback, useState } from 'react';
import { Platform, StyleSheet, TextInput, View } from 'react-native';

import { BarcodeCamera } from '@/components/barcode-camera';
import { Button, Radius, Screen, Section, Txt } from '@/components/ui';
import { Spacing, Type } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import type { ScanInput } from '@/scan/client';
import { gtinProblem } from '@/scan/gtin';
import { pickImage } from '@/scan/pick-image';
import { useScan } from '@/scan/scan-context';

export default function ScanScreen() {
  const theme = useTheme();
  const { start } = useScan();
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
      <View style={styles.intro}>
        <Txt variant="title" accessibilityRole="header">
          Check a cosmetic product
        </Txt>
        <Txt muted>Scan the barcode. If its ingredients aren’t online, you’ll photograph the label instead.</Txt>
      </View>

      {Platform.OS !== 'web' && <BarcodeCamera onScanned={(code) => begin({ barcode: code })} />}

      <Section title={Platform.OS === 'web' ? 'Use a photo' : 'Or use a photo'}>
        <Txt muted>A clear photo of the barcode or of the ingredient list both work.</Txt>
        <View style={styles.row}>
          <Button label="Take photo" icon={CameraIcon} onPress={() => choosePhoto('camera')} style={styles.grow} />
          <Button label="Upload photo" icon={ImageSquareIcon} kind="secondary" onPress={() => choosePhoto('library')} style={styles.grow} />
        </View>
        {photoError && (
          <Txt variant="small" tone="prohibited" accessibilityRole="alert">
            {photoError}
          </Txt>
        )}
      </Section>

      <Section title="Or type the barcode number">
        <View style={styles.field}>
          <Txt variant="strong" nativeID="barcode-label">
            Barcode number
          </Txt>
          <TextInput
            accessibilityLabelledBy="barcode-label"
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
        <Button label="Check product" icon={MagnifyingGlassIcon} onPress={submitBarcode} disabled={!barcode.trim()} />
      </Section>
    </Screen>
  );
}

const styles = StyleSheet.create({
  intro: { gap: Spacing.two },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: Spacing.three },
  grow: { flexGrow: 1, flexBasis: 200 },
  field: { gap: Spacing.two },
  input: { minHeight: 48, borderWidth: 1, borderRadius: Radius.control, paddingHorizontal: Spacing.four, letterSpacing: 1 },
});
