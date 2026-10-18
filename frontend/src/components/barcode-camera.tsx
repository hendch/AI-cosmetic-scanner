// Live barcode scanning on phones. Not rendered on web (browser barcode support is uneven);
// web users upload a photo or type the number instead.
import { CameraView, useCameraPermissions, type BarcodeScanningResult } from 'expo-camera';
import { useFocusEffect } from 'expo-router';
import { CameraIcon } from 'phosphor-react-native';
import { useCallback, useRef, useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

import { Button, Radius, Txt } from './ui';

export function BarcodeCamera({ onScanned }: { onScanned: (barcode: string) => void }) {
  const theme = useTheme();
  const [permission, requestPermission] = useCameraPermissions();
  const [focused, setFocused] = useState(false);
  const handled = useRef(false);

  // Only one camera preview can run at a time: unmount it while another screen is on top.
  useFocusEffect(
    useCallback(() => {
      handled.current = false;
      setFocused(true);
      return () => setFocused(false);
    }, []),
  );

  const onBarcodeScanned = useCallback(
    (result: BarcodeScanningResult) => {
      if (handled.current) return;
      handled.current = true;
      onScanned(result.data);
    },
    [onScanned],
  );

  const frame = [styles.frame, { backgroundColor: theme.ink }];

  if (!permission) return <View style={frame} accessibilityLabel="Starting the camera" />;

  if (!permission.granted) {
    return (
      <View style={[styles.frame, styles.prompt, { backgroundColor: theme.surface }]}>
        <Txt variant="strong">Allow the camera to scan barcodes</Txt>
        <Txt muted>The camera is only used while this screen is open. You can also type the number below.</Txt>
        <Button
          label={permission.canAskAgain ? 'Allow camera' : 'Camera blocked in settings'}
          icon={CameraIcon}
          onPress={requestPermission}
          disabled={!permission.canAskAgain}
        />
      </View>
    );
  }

  return (
    <View style={frame}>
      {focused && (
        <CameraView
          style={StyleSheet.absoluteFill}
          facing="back"
          barcodeScannerSettings={{ barcodeTypes: ['ean13', 'ean8', 'upc_a'] }}
          onBarcodeScanned={onBarcodeScanned}
        />
      )}
      <View style={[styles.guide, { borderColor: '#FFFFFF' }]} pointerEvents="none">
        <View style={[styles.line, { backgroundColor: theme.accent }]} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  frame: { aspectRatio: 4 / 3, borderRadius: Radius.panel, overflow: 'hidden', justifyContent: 'center' },
  prompt: { padding: Spacing.five, gap: Spacing.three, aspectRatio: undefined },
  guide: { alignSelf: 'center', width: '70%', height: '32%', borderWidth: 2, borderRadius: Radius.tile, opacity: 0.9, justifyContent: 'center' },
  line: { height: 2, marginHorizontal: Spacing.three, opacity: 0.9 },
});
