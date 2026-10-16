import { StyleSheet, View, type LayoutChangeEvent } from 'react-native';

import { Chip, Txt } from '@/components/ui';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import type { Ingredient } from '@/report/schema';
import { concernLabel, confidenceLabel, hazardEndpointLabel, ingredientTone, regulatoryLabel } from '@/report/wording';

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <View style={styles.rowBlock}>
      <Txt variant="small" muted>
        {label}
      </Txt>
      <View style={styles.rowBody}>{children}</View>
    </View>
  );
}

export function IngredientDetail({ ingredient: i, onLayout }: { ingredient: Ingredient; onLayout?: (e: LayoutChangeEvent) => void }) {
  const theme = useTheme();
  const tone = ingredientTone(i);
  const name = i.ingredient.charAt(0).toUpperCase() + i.ingredient.slice(1);

  return (
    <View onLayout={onLayout} style={[styles.item, { borderTopColor: theme.line }]}>
      <View style={styles.head}>
        <View style={styles.flex}>
          <Txt variant="heading">{name}</Txt>
          {i.raw.toLowerCase() !== i.ingredient && (
            <Txt variant="small" muted>
              Printed as {i.raw}
            </Txt>
          )}
        </View>
        <Chip label={regulatoryLabel[i.regulatory_status]} tone={tone} />
      </View>

      <Row label={i.annex_entry ? `EU rules, ${i.annex_entry}` : 'EU rules'}>
        <Txt>{i.regulatory_explanation}</Txt>
        {i.conditions.map((c) => (
          <Txt key={c} variant="small">
            {c}
          </Txt>
        ))}
      </Row>

      <Row label={`Hazards, ${concernLabel[i.concern_level].toLowerCase()}`}>
        {i.hazards.map((h) => (
          <Txt key={`${h.endpoint}-${h.classification}`} variant="small">
            {hazardEndpointLabel[h.endpoint] ?? h.endpoint}: {h.classification}
          </Txt>
        ))}
        <Txt>{i.risk_interpretation}</Txt>
      </Row>

      {i.missing_information.length > 0 && (
        <Row label="Not known">
          <Txt tone="unknown">{i.missing_information.join('; ')}</Txt>
        </Row>
      )}

      <View style={styles.footer}>
        <Txt variant="small" muted>
          Evidence confidence: {confidenceLabel[i.evidence_confidence]}
        </Txt>
        {i.sources.length > 0 && (
          <Txt variant="small" muted>
            Sources: {i.sources.join(', ')}
          </Txt>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  item: { borderTopWidth: 1, paddingTop: Spacing.four, gap: Spacing.three },
  head: { flexDirection: 'row', alignItems: 'flex-start', gap: Spacing.three },
  flex: { flex: 1 },
  rowBlock: { gap: 2 },
  rowBody: { gap: Spacing.one },
  footer: { gap: 2 },
});
