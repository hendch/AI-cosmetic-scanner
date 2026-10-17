import { router } from 'expo-router';
import { BarcodeIcon, CheckCircleIcon, InfoIcon, QuestionIcon, WarningCircleIcon, XCircleIcon } from 'phosphor-react-native';
import { useRef } from 'react';
import { StyleSheet, View, type ScrollViewInstance } from 'react-native';

import { AnnotatedLabel } from '@/components/report/annotated-label';
import { IngredientDetail } from '@/components/report/ingredient-detail';
import { SourcesList } from '@/components/report/sources-list';
import { ValidationBanner } from '@/components/report/validation-banner';
import { Button, Panel, Screen, Section, Txt } from '@/components/ui';
import { Spacing, type Tone } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { crueltyFreeLabel, overviewLines } from '@/report/wording';
import { useScan } from '@/scan/scan-context';

const TONE_ICON = { clear: CheckCircleIcon, attention: WarningCircleIcon, prohibited: XCircleIcon, unknown: QuestionIcon } as const;

const EXPOSURE = { leave_on: 'Leave-on product', rinse_off: 'Rinse-off product' } as const;

export default function ReportScreen() {
  const theme = useTheme();
  const { outcome, reset } = useScan();
  const scrollRef = useRef<ScrollViewInstance>(null);
  const offsets = useRef({ section: 0, list: 0, items: {} as Record<string, number> });

  const scanAnother = () => {
    reset();
    router.dismissTo('/');
  };

  if (outcome?.kind !== 'completed') {
    return (
      <Screen>
        <View style={styles.block}>
          <Txt variant="title">No report yet</Txt>
          <Txt muted>Scan a product to see its ingredient report here.</Txt>
          <Button label="Scan a product" icon={BarcodeIcon} onPress={scanAnother} style={styles.start} />
        </View>
      </Screen>
    );
  }

  const r = outcome.report;
  const productName = r.product.name || 'Unnamed product';
  const origin = r.input_source === 'ocr' ? 'Ingredients read from your label photo' : `Barcode ${r.product.barcode}`;
  const exposure = r.product.exposure_type ? EXPOSURE[r.product.exposure_type] : null;
  const cf = crueltyFreeLabel[r.cruelty_free.status];

  const jumpTo = (ingredient: string) => {
    const y = offsets.current.items[ingredient];
    if (y === undefined) return;
    scrollRef.current?.scrollTo({ y: offsets.current.section + offsets.current.list + y - Spacing.four, animated: true });
  };

  return (
    <Screen scrollRef={scrollRef}>
      <View style={styles.block}>
        {r.product.brand ? <Txt muted>{r.product.brand}</Txt> : null}
        <Txt variant="title" accessibilityRole="header">
          {productName}
        </Txt>
        <Txt variant="small" muted>
          {exposure ? `${origin}. ${exposure}.` : `${origin}.`}
        </Txt>
      </View>

      <AnnotatedLabel ingredients={r.ingredients} onSelect={jumpTo} />

      <ValidationBanner report={r} />

      <Section title="Overview">
        <View style={styles.lines}>
          {overviewLines(r).map((line) => {
            const Icon = TONE_ICON[line.tone as Tone];
            return (
              <View key={line.text} style={styles.line}>
                <Icon size={20} color={theme[line.tone]} weight="fill" />
                <Txt style={styles.flex}>{line.text}</Txt>
              </View>
            );
          })}
        </View>
        <View style={styles.coverage}>
          <Txt variant="strong">
            Evidence found for {r.evidence_coverage.covered} of {r.evidence_coverage.total} ingredients
          </Txt>
          <Txt variant="small" muted>
            {r.evidence_coverage.definition}
          </Txt>
        </View>
      </Section>

      <View onLayout={(e) => (offsets.current.section = e.nativeEvent.layout.y)} style={styles.sectionGap}>
        <Txt variant="heading" accessibilityRole="header">
          Ingredient details
        </Txt>
        <View onLayout={(e) => (offsets.current.list = e.nativeEvent.layout.y)} style={styles.items}>
          {r.ingredients.map((ing) => (
            <IngredientDetail
              key={ing.position}
              ingredient={ing}
              onLayout={(e) => (offsets.current.items[ing.ingredient] = e.nativeEvent.layout.y)}
            />
          ))}
        </View>
      </View>

      <Section title="Animal testing">
        <Panel>
          <Txt variant="strong" tone={cf.tone}>
            {cf.title}
          </Txt>
          <Txt>{r.cruelty_free.status_reason}</Txt>
          <Txt variant="small" muted>
            Brand claim: {r.cruelty_free.brand_claim_found ? 'found' : 'not found'}. Certifications found:{' '}
            {r.cruelty_free.certifications_found.length ? r.cruelty_free.certifications_found.join(', ') : 'none'}.
          </Txt>
          {r.cruelty_free.certifications_checked.length > 0 && (
            <Txt variant="small" muted>
              Lists checked: {r.cruelty_free.certifications_checked.join(', ')}.
            </Txt>
          )}
          {r.cruelty_free.conflicts.map((c) => (
            <Txt key={c} variant="small" tone="attention">
              {c}
            </Txt>
          ))}
        </Panel>
      </Section>

      <Section title="Sources">
        <SourcesList sources={r.sources} />
      </Section>

      <Section title="What this report can’t tell you">
        <View style={styles.lines}>
          {[...r.warnings, ...r.limitations].map((text) => (
            <View key={text} style={styles.line}>
              <InfoIcon size={18} color={theme.textSecondary} />
              <Txt variant="small" muted style={styles.flex}>
                {text}
              </Txt>
            </View>
          ))}
        </View>
      </Section>

      <Button label="Scan another product" icon={BarcodeIcon} onPress={scanAnother} />
    </Screen>
  );
}

const styles = StyleSheet.create({
  block: { gap: Spacing.two },
  start: { alignSelf: 'flex-start', marginTop: Spacing.three },
  lines: { gap: Spacing.three },
  line: { flexDirection: 'row', alignItems: 'flex-start', gap: Spacing.three },
  flex: { flex: 1 },
  coverage: { gap: Spacing.one },
  sectionGap: { gap: Spacing.four },
  items: { gap: Spacing.five },
});
