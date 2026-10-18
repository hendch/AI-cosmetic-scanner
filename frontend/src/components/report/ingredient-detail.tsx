import { StyleSheet, View, type LayoutChangeEvent } from 'react-native';

import { Chip, Txt } from '@/components/ui';
import { Spacing, type Tone } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import type { Condition, Ingredient } from '@/report/schema';
import {
  concernLabel,
  conditionLabel,
  conditionTypeLabel,
  confidenceLabel,
  displayName,
  hazardEndpointLabel,
  ingredientTone,
  regulatoryLabel,
} from '@/report/wording';

const CONDITION_TONE: Record<Condition['result'], Tone | undefined> = {
  satisfied: 'clear',
  not_satisfied: 'prohibited',
  unknown: 'unknown',
  not_applicable: undefined,
};

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
  const reg = i.regulatory;
  const tox = i.toxicology;
  const evidence = [...new Set([...reg.evidence_ids, ...tox.evidence_ids])];

  return (
    <View onLayout={onLayout} style={[styles.item, { borderTopColor: theme.line }]}>
      <View style={styles.head}>
        <View style={styles.flex}>
          <Txt variant="heading">{displayName(i.ingredient_id)}</Txt>
          {i.raw.toLowerCase() !== i.ingredient_id.toLowerCase() && (
            <Txt variant="small" muted>
              Printed as {i.raw}
            </Txt>
          )}
        </View>
        <Chip label={i.matched ? regulatoryLabel[reg.status] : 'Not recognised'} tone={tone} />
      </View>

      <Row label={reg.entries.length ? `EU rules, Annex ${reg.entries.join(', ')}` : 'EU rules'}>
        <Txt>{reg.explanation}</Txt>
        {reg.conditions.map((c) => (
          <View key={`${c.entry}-${c.type}-${c.requirement}`} style={styles.condition}>
            <Txt variant="small">
              {conditionTypeLabel[c.type]}: {c.requirement}.{' '}
              <Txt variant="small" tone={CONDITION_TONE[c.result]} muted={!CONDITION_TONE[c.result]} style={styles.bold}>
                {conditionLabel[c.result]}
              </Txt>
            </Txt>
            {c.reason ? (
              <Txt variant="small" muted>
                {c.reason}
              </Txt>
            ) : null}
          </View>
        ))}
        {i.concentration_percent != null && (
          <Txt variant="small" muted>
            Concentration in this product: {i.concentration_percent}%
          </Txt>
        )}
      </Row>

      <Row label={`Hazards, ${concernLabel[tox.concern_level].toLowerCase()}`}>
        {tox.hazards.map((h) => (
          <Txt key={`${h.endpoint}-${h.label}`} variant="small">
            {hazardEndpointLabel[h.endpoint] ?? h.endpoint}: {h.label}
          </Txt>
        ))}
        <Txt>{tox.explanation}</Txt>
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
        {evidence.length > 0 && (
          <Txt variant="small" muted>
            Evidence: {evidence.join(', ')}
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
  condition: { gap: 2 },
  bold: { fontWeight: '600' },
  footer: { gap: 2 },
});
