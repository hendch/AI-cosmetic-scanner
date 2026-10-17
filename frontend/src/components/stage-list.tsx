import { CheckCircleIcon, CircleIcon, CircleNotchIcon } from 'phosphor-react-native';
import { useEffect, useState } from 'react';
import { AccessibilityInfo, Animated, Easing, StyleSheet, View } from 'react-native';

import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { STAGES, stageIndex } from '@/scan/stages';

import { Txt } from './ui';

function Spinner({ color }: { color: string }) {
  const [turn] = useState(() => new Animated.Value(0));
  useEffect(() => {
    let loop: Animated.CompositeAnimation | null = null;
    AccessibilityInfo.isReduceMotionEnabled().then((reduce) => {
      if (reduce) return;
      loop = Animated.loop(Animated.timing(turn, { toValue: 1, duration: 900, easing: Easing.linear, useNativeDriver: true }));
      loop.start();
    });
    return () => loop?.stop();
  }, [turn]);
  const rotate = turn.interpolate({ inputRange: [0, 1], outputRange: ['0deg', '360deg'] });
  return (
    <Animated.View style={{ transform: [{ rotate }] }}>
      <CircleNotchIcon size={22} color={color} weight="bold" />
    </Animated.View>
  );
}

/**
 * `stage` is the step n8n reported. When n8n reports no steps (null), every step is
 * shown as upcoming rather than guessing which one is running.
 */
export function StageList({ stage, finished }: { stage: string | null; finished: boolean }) {
  const theme = useTheme();
  const current = finished ? STAGES.length : stageIndex(stage);

  return (
    <View style={styles.list} accessibilityRole="list">
      {STAGES.map((s, i) => {
        const done = i < current;
        const running = i === current;
        return (
          <View key={s.id} style={styles.row} accessibilityLabel={`${done ? s.done : s.running}${done ? ', done' : running ? ', in progress' : ''}`}>
            {done ? (
              <CheckCircleIcon size={22} color={theme.clear} weight="fill" />
            ) : running ? (
              <Spinner color={theme.accent} />
            ) : (
              <CircleIcon size={22} color={theme.line} weight="bold" />
            )}
            <Txt variant={running ? 'strong' : 'body'} muted={!done && !running}>
              {done ? s.done : s.running}
            </Txt>
          </View>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  list: { gap: Spacing.three },
  row: { flexDirection: 'row', alignItems: 'center', gap: Spacing.three },
});
