import * as WebBrowser from 'expo-web-browser';
import { ArrowSquareOutIcon } from 'phosphor-react-native';
import { Pressable, StyleSheet, View } from 'react-native';

import { Txt } from '@/components/ui';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import type { Source } from '@/report/schema';

export function SourcesList({ sources }: { sources: Source[] }) {
  const theme = useTheme();
  return (
    <View style={styles.list}>
      {sources.map((s) => {
        const meta = [s.publisher, s.publication_date].filter(Boolean).join(', ');
        return (
          <View key={s.source_id} style={styles.item}>
            <Txt variant="strong">{s.title ?? s.source_id}</Txt>
            {s.in_corpus ? (
              meta ? <Txt variant="small" muted>{meta}</Txt> : null
            ) : (
              <Txt variant="small" tone="attention">
                Not in the evidence corpus ({s.source_id})
              </Txt>
            )}
            {s.url && (
              <Pressable accessibilityRole="link" onPress={() => WebBrowser.openBrowserAsync(s.url!)} style={styles.link}>
                <Txt variant="small" style={{ color: theme.accent, fontWeight: '600' }}>
                  Open source
                </Txt>
                <ArrowSquareOutIcon size={14} color={theme.accent} weight="bold" />
              </Pressable>
            )}
          </View>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  list: { gap: Spacing.four },
  item: { gap: 2 },
  link: { flexDirection: 'row', alignItems: 'center', gap: Spacing.one, alignSelf: 'flex-start', minHeight: 28 },
});
