import { Redirect, router } from 'expo-router';
import { ArrowCounterClockwiseIcon, BarcodeIcon, CameraIcon, ImageSquareIcon, WarningCircleIcon } from 'phosphor-react-native';
import { useEffect, useState } from 'react';
import { Image, StyleSheet, View } from 'react-native';

import { StageList } from '@/components/stage-list';
import { Button, Panel, Radius, Screen, Txt } from '@/components/ui';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { SLOW_AFTER_SECONDS, estimatedStage, useElapsedSeconds } from '@/scan/estimate';
import { pickImage } from '@/scan/pick-image';
import { STAGES, stageIndex } from '@/scan/stages';
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
  const seconds = useElapsedSeconds(running);
  const current = stage ?? (running ? estimatedStage(seconds, !!input?.image) : null);

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
      {!running && (
        <Txt variant="title" accessibilityRole="header">
          {outcome ? TITLES[outcome.kind] : 'Analysis stopped'}
        </Txt>
      )}

      <View style={[styles.subject, { backgroundColor: theme.surface }]}>
        {input.image ? (
          <Image source={{ uri: input.image.uri }} style={styles.thumb} accessibilityLabel="Your photo" />
        ) : (
          <View style={[styles.thumb, styles.icon, { backgroundColor: theme.accentSoft }]}>
            <BarcodeIcon size={24} color={theme.accent} weight="bold" />
          </View>
        )}
        <View style={styles.flex}>
          <Txt variant="strong" accessibilityRole="header">
            {running ? 'Checking product' : input.barcode ? 'Barcode' : 'Your photo'}
          </Txt>
          <Txt variant="small" muted>
            {input.barcode ?? 'From your label photo'}
            {input.barcode && input.image ? ', with a label photo' : ''}
          </Txt>
        </View>
        {running && (
          <Txt variant="heading" style={{ color: theme.accent, fontVariant: ['tabular-nums'] }} accessibilityLabel={`${seconds} seconds`}>
            {seconds} s
          </Txt>
        )}
      </View>

      <StageList stage={current} finished={outcome?.kind === 'report'} />

      {running && (
        <View style={styles.actions}>
          <View style={[styles.track, { backgroundColor: theme.line }]}>
            <View style={[styles.fill, { backgroundColor: theme.accent, width: `${Math.round(((stageIndex(current) + 0.5) / STAGES.length) * 100)}%` }]} />
          </View>
          <Txt variant="small" muted>
            {seconds < SLOW_AFTER_SECONDS
              ? 'Usually 10 to 30 seconds.'
              : 'Still working. The service was probably asleep and takes about a minute to wake up.'}
          </Txt>
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
  subject: { flexDirection: 'row', alignItems: 'center', gap: Spacing.three, borderRadius: Radius.panel, padding: Spacing.three },
  thumb: { width: 48, height: 48, borderRadius: Radius.control },
  icon: { alignItems: 'center', justifyContent: 'center' },
  flex: { flex: 1 },
  actions: { gap: Spacing.three },
  track: { height: 6, borderRadius: 3, overflow: 'hidden' },
  fill: { height: 6, borderRadius: 3 },
  titleRow: { flexDirection: 'row', alignItems: 'center', gap: Spacing.two },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: Spacing.three },
  grow: { flexGrow: 1, flexBasis: 200 },
});
