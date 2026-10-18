import { Redirect, router } from 'expo-router';
import { ArrowCounterClockwiseIcon, CameraIcon, ImageSquareIcon, WarningCircleIcon } from 'phosphor-react-native';
import { useEffect, useState } from 'react';
import { Image, StyleSheet, View } from 'react-native';

import { StageList } from '@/components/stage-list';
import { Button, Panel, Radius, Screen, Txt } from '@/components/ui';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { pickImage } from '@/scan/pick-image';
import { useScan } from '@/scan/scan-context';

const TITLES = {
  report: 'Report ready',
  needs_input: 'One more photo needed',
  error: 'Analysis stopped',
} as const;

export default function ProgressScreen() {
  const theme = useTheme();
  const { input, running, stage, outcome, start, cancel, reset } = useScan();
  const [photoError, setPhotoError] = useState<string | null>(null);

  useEffect(() => {
    if (outcome?.kind === 'report') router.replace('/report');
  }, [outcome]);

  if (!input) return <Redirect href="/" />;

  const scanAnother = () => {
    reset();
    router.dismissTo('/');
  };

  const addLabelPhoto = async (source: 'camera' | 'library') => {
    setPhotoError(null);
    const result = await pickImage(source);
    if (!result) return;
    if ('problem' in result) setPhotoError(result.problem);
    else start({ barcode: input.barcode, image: result.image });
  };

  return (
    <Screen>
      <View style={styles.header}>
        <Txt variant="title" accessibilityRole="header">
          {running ? 'Analysing the product' : outcome ? TITLES[outcome.kind] : 'Analysis stopped'}
        </Txt>
        <View style={styles.subject}>
          {input.image && <Image source={{ uri: input.image.uri }} style={[styles.thumb, { borderColor: theme.line }]} accessibilityLabel="Your photo" />}
          <Txt muted>
            {input.barcode ? `Barcode ${input.barcode}` : 'From your photo'}
            {input.barcode && input.image ? ' with a label photo' : ''}
          </Txt>
        </View>
      </View>

      <StageList stage={stage} finished={outcome?.kind === 'report'} />

      {running && (
        <View style={styles.actions}>
          {stage === null && <Txt muted>A scan usually takes 10 to 30 seconds, up to a minute more if the service was asleep.</Txt>}
          <Button
            label="Cancel"
            kind="secondary"
            onPress={() => {
              cancel();
              router.back();
            }}
          />
        </View>
      )}

      {outcome?.kind === 'needs_input' && (
        <Panel>
          <Txt variant="strong">Ingredient list needed</Txt>
          <Txt>{outcome.message}</Txt>
          <View style={styles.row}>
            <Button label="Take photo" icon={CameraIcon} onPress={() => addLabelPhoto('camera')} style={styles.grow} />
            <Button label="Upload photo" icon={ImageSquareIcon} kind="secondary" onPress={() => addLabelPhoto('library')} style={styles.grow} />
          </View>
          {photoError && (
            <Txt variant="small" tone="prohibited" accessibilityRole="alert">
              {photoError}
            </Txt>
          )}
          <Button label="Scan another product" kind="secondary" onPress={scanAnother} />
        </Panel>
      )}

      {outcome?.kind === 'error' && (
        <Panel>
          <View style={styles.titleRow}>
            <WarningCircleIcon size={22} color={theme.prohibited} weight="fill" />
            <Txt variant="strong">The analysis didn’t finish</Txt>
          </View>
          <Txt>{outcome.message}</Txt>
          <View style={styles.row}>
            <Button label="Try again" icon={ArrowCounterClockwiseIcon} onPress={() => start(input)} style={styles.grow} />
            <Button label="Scan another product" kind="secondary" onPress={scanAnother} style={styles.grow} />
          </View>
        </Panel>
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  header: { gap: Spacing.three },
  subject: { flexDirection: 'row', alignItems: 'center', gap: Spacing.three },
  thumb: { width: 48, height: 48, borderRadius: Radius.control, borderWidth: 1 },
  actions: { gap: Spacing.three, alignItems: 'flex-start' },
  titleRow: { flexDirection: 'row', alignItems: 'center', gap: Spacing.two },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: Spacing.three },
  grow: { flexGrow: 1, flexBasis: 200 },
});
