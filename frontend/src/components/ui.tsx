// Shared primitives. Shape rule: buttons and chips are pills, text fields 14, panels 20, tiles 16.
import type { Icon } from 'phosphor-react-native';
import type { ReactNode, RefObject } from 'react';
import {
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
  type ScrollViewInstance,
  type StyleProp,
  type TextProps,
  type TextStyle,
  type ViewStyle,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { MaxContentWidth, Spacing, Type, type Tone } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

export const Radius = { control: 14, tile: 16, panel: 20, pill: 999, chip: 999 } as const;

export function Screen({ children, scrollRef }: { children: ReactNode; scrollRef?: RefObject<ScrollViewInstance | null> }) {
  const theme = useTheme();
  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: theme.background }} edges={['top', 'left', 'right']}>
      <ScrollView ref={scrollRef} contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
        <View style={styles.column}>{children}</View>
      </ScrollView>
    </SafeAreaView>
  );
}

type TxtProps = TextProps & { variant?: keyof typeof Type; muted?: boolean; tone?: Tone; style?: StyleProp<TextStyle> };

export function Txt({ variant = 'body', muted, tone, style, ...rest }: TxtProps) {
  const theme = useTheme();
  const color = tone ? theme[tone] : muted ? theme.textSecondary : theme.text;
  return <Text style={[Type[variant], { color }, style]} {...rest} />;
}

type ButtonProps = {
  label: string;
  onPress: () => void;
  icon?: Icon;
  kind?: 'primary' | 'secondary' | 'ink';
  disabled?: boolean;
  style?: StyleProp<ViewStyle>;
};

export function Button({ label, onPress, icon: IconComponent, kind = 'primary', disabled, style }: ButtonProps) {
  const theme = useTheme();
  const fg = kind === 'primary' ? theme.onAccent : kind === 'ink' ? theme.onInk : theme.text;
  const look =
    kind === 'primary'
      ? { backgroundColor: theme.accent }
      : kind === 'ink'
        ? { backgroundColor: theme.ink }
        : { borderColor: theme.line, borderWidth: 1, backgroundColor: theme.surface };
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled }}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        look,
        pressed && { transform: [{ scale: 0.98 }] },
        disabled && { opacity: 0.5 },
        style,
      ]}>
      {IconComponent && <IconComponent size={20} color={fg} weight="bold" />}
      <Text style={[Type.strong, { color: fg }]} numberOfLines={1}>
        {label}
      </Text>
    </Pressable>
  );
}

export function Panel({ children, style }: { children: ReactNode; style?: StyleProp<ViewStyle> }) {
  const theme = useTheme();
  return <View style={[styles.panel, { backgroundColor: theme.surface }, style]}>{children}</View>;
}

export function Chip({ label, tone }: { label: string; tone: Tone }) {
  const theme = useTheme();
  return (
    <View style={[styles.chip, { backgroundColor: theme[`${tone}Soft`] }]}>
      <Txt variant="caption" tone={tone}>
        {label}
      </Txt>
    </View>
  );
}

export function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <View style={styles.section}>
      <Txt variant="heading" accessibilityRole="header">
        {title}
      </Txt>
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  scroll: { flexGrow: 1, alignItems: 'center', paddingBottom: Spacing.seven },
  column: { width: '100%', maxWidth: MaxContentWidth, paddingHorizontal: Spacing.four, paddingTop: Spacing.five, gap: Spacing.five },
  button: {
    minHeight: 50,
    paddingHorizontal: Spacing.five,
    borderRadius: Radius.pill,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: Spacing.two,
  },
  panel: { borderRadius: Radius.panel, padding: Spacing.four, gap: Spacing.three },
  chip: { borderRadius: Radius.chip, paddingHorizontal: Spacing.three, paddingVertical: 4, alignSelf: 'flex-start' },
  section: { gap: Spacing.four },
});
