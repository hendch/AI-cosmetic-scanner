// Every evidence item the report cites, with the text the claim rests on.
import * as WebBrowser from 'expo-web-browser';
import { ArrowSquareOutIcon } from 'phosphor-react-native';
import { Pressable, StyleSheet, View } from 'react-native';

import { Txt } from '@/components/ui';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import type { Source } from '@/report/schema';
import { sourceKindLabel } from '@/report/wording';

export function SourcesList({ sources }: { sources: Source[] }) {
  const theme = useTheme();
  if (sources.length === 0) return <Txt muted>The report cites no sources.</Txt>;
  return (
    <View style={styles.list}>
      {sources.map((s) => {
        const meta = [sourceKindLabel[s.kind] ?? s.kind, s.publisher, s.date].filter(Boolean).join(', ');
        return (
          <View key={s.evidence_id} style={styles.item}>
            <Txt variant="strong">{s.title ?? s.source_id}</Txt>
            <Txt variant="small" muted>
              {meta}
            </Txt>
            {s.excerpt ? (
              <Txt variant="small" numberOfLines={4} style={[styles.excerpt, { borderLeftColor: theme.line }]}>
                “{s.excerpt}”
              </Txt>
            ) : (
              <Txt variant="small" tone="attention">
                No source text was given for this evidence.
              </Txt>
            )}
            {!s.in_corpus && (
              <Txt variant="small" tone="attention">
                Not in the project’s evidence corpus ({s.source_id})
              </Txt>
            )}
            <Txt variant="small" muted>
              {s.evidence_id}
            </Txt>
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
  excerpt: { borderLeftWidth: 2, paddingLeft: Spacing.two, marginVertical: Spacing.one },
  link: { flexDirection: 'row', alignItems: 'center', gap: Spacing.one, alignSelf: 'flex-start', minHeight: 28 },
});
