// Shared primitives. Corner radius rule: interactive controls 12, panels 16, status chips fully rounded.
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

export const Radius = { control: 12, panel: 16, chip: 999 } as const;

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
  kind?: 'primary' | 'secondary';
  disabled?: boolean;
  style?: StyleProp<ViewStyle>;
};

export function Button({ label, onPress, icon: IconComponent, kind = 'primary', disabled, style }: ButtonProps) {
  const theme = useTheme();
  const primary = kind === 'primary';
  const fg = primary ? theme.onAccent : theme.accent;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled }}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        primary ? { backgroundColor: theme.accent } : { borderColor: theme.line, borderWidth: 1, backgroundColor: theme.surface },
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
  return <View style={[styles.panel, { backgroundColor: theme.surface, borderColor: theme.line }, style]}>{children}</View>;
}

export function Chip({ label, tone }: { label: string; tone: Tone }) {
  const theme = useTheme();
  return (
    <View style={[styles.chip, { borderColor: theme[tone] }]}>
      <Txt variant="small" tone={tone} style={{ fontWeight: '600' }}>
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
  column: { width: '100%', maxWidth: MaxContentWidth, paddingHorizontal: Spacing.four, paddingTop: Spacing.five, gap: Spacing.six },
  button: {
    minHeight: 48,
    paddingHorizontal: Spacing.five,
    borderRadius: Radius.control,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: Spacing.two,
  },
  panel: { borderRadius: Radius.panel, borderWidth: 1, padding: Spacing.four, gap: Spacing.three },
  chip: { borderRadius: Radius.chip, borderWidth: 1, paddingHorizontal: Spacing.three, paddingVertical: 2, alignSelf: 'flex-start' },
  section: { gap: Spacing.four },
});
