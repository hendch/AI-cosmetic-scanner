import { router } from 'expo-router';
import { BarcodeIcon, CaretDownIcon, CaretUpIcon, InfoIcon } from 'phosphor-react-native';
import { useMemo, useRef, useState } from 'react';
import { StyleSheet, View, type ScrollViewInstance } from 'react-native';

import { AnnotatedLabel } from '@/components/report/annotated-label';
import { IngredientDetail } from '@/components/report/ingredient-detail';
import { IngredientPills } from '@/components/report/ingredient-pills';
import { Conclusion, ScoreCard, ScoreExplanation, StatTiles } from '@/components/report/score-card';
import { SourcesList } from '@/components/report/sources-list';
import { ValidationBanner } from '@/components/report/validation-banner';
import { Button, Panel, Screen, Section, Txt } from '@/components/ui';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { productScore } from '@/report/score';
import { crueltyFreeLabel } from '@/report/wording';
import { useScan } from '@/scan/scan-context';

const EXPOSURE = { leave_on: 'Leave-on product', rinse_off: 'Rinse-off product' } as const;

export default function ReportScreen() {
  const theme = useTheme();
  const { outcome, reset } = useScan();
  const scrollRef = useRef<ScrollViewInstance>(null);
  const offsets = useRef({ details: 0, section: 0, list: 0, items: {} as Record<string, number> });
  const [open, setOpen] = useState(false);
  const report = outcome?.kind === 'report' ? outcome.report : null;
  const score = useMemo(() => (report ? productScore(report) : null), [report]);

  const scanAnother = () => {
    reset();
    router.dismissTo('/');
  };

  if (outcome?.kind !== 'report' || !score) {
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

  // A pill can be tapped while the full report is closed: open it, then scroll once it is laid out.
  const showIngredient = (ingredient: string) => {
    if (open) return jumpTo(ingredient);
    setOpen(true);
    setTimeout(() => jumpTo(ingredient), 350);
  };

  const jumpTo = (ingredient: string) => {
    const y = offsets.current.items[ingredient];
    if (y === undefined) return;
    const { details, section, list } = offsets.current;
    scrollRef.current?.scrollTo({ y: details + section + list + y - Spacing.four, animated: true });
  };

  return (
    <Screen scrollRef={scrollRef}>
      <View style={styles.block}>
        {r.product.brand ? (
          <Txt variant="caption" muted>
            {r.product.brand}
          </Txt>
        ) : null}
        <Txt variant="heading" accessibilityRole="header">
          {productName}
        </Txt>
        <Txt variant="small" muted>
          {exposure ? `${origin}. ${exposure}.` : `${origin}.`}
        </Txt>
        {r.needs_review && (
          <Txt variant="small" tone="attention">
            Some ingredient names were hard to read. Check the underlined names against your label.
          </Txt>
        )}
      </View>

      <View style={styles.summary}>
        <ScoreCard result={score} needsReview={outcome.status === 'needs_review'} />
        <StatTiles report={r} />
        <IngredientPills ingredients={r.ingredients} onSelect={showIngredient} onMore={() => setOpen(true)} />
      </View>

      <Button
        label={open ? 'Hide full report' : 'Show full report'}
        icon={open ? CaretUpIcon : CaretDownIcon}
        kind="ink"
        onPress={() => setOpen((o) => !o)}
        style={styles.toggle}
      />

      {open && (
        <View onLayout={(e) => (offsets.current.details = e.nativeEvent.layout.y)} style={styles.details}>
          <Section title="In short">
            <Conclusion result={score} />
          </Section>

          <AnnotatedLabel ingredients={r.ingredients} onSelect={jumpTo} />
    
          <ValidationBanner report={r} needsReview={outcome.status === 'needs_review'} />
    
          <View onLayout={(e) => (offsets.current.section = e.nativeEvent.layout.y)} style={styles.sectionGap}>
            <Txt variant="heading" accessibilityRole="header">
              Ingredient details
            </Txt>
            <View onLayout={(e) => (offsets.current.list = e.nativeEvent.layout.y)} style={styles.items}>
              {r.ingredients.map((ing) => (
                <IngredientDetail
                  key={ing.position}
                  ingredient={ing}
                  onLayout={(e) => (offsets.current.items[ing.ingredient_id] = e.nativeEvent.layout.y)}
                />
              ))}
            </View>
          </View>
    
          <Section title="Animal testing">
            <Panel>
              <Txt variant="strong" tone={cf.tone}>
                {cf.title}
              </Txt>
              <Txt>{r.cruelty_free.explanation}</Txt>
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
    
              <Section title="How the score works">
            <ScoreExplanation result={score} />
            <Txt variant="small" muted>
              Evidence found for {r.evidence_coverage.covered} of {r.evidence_coverage.total} ingredients. {r.evidence_coverage.definition}
            </Txt>
          </Section>
        </View>
      )}

      <Button label="Scan another product" icon={BarcodeIcon} kind="secondary" onPress={scanAnother} />
    </Screen>
  );
}

const styles = StyleSheet.create({
  block: { gap: Spacing.one },
  start: { alignSelf: 'flex-start', marginTop: Spacing.three },
  lines: { gap: Spacing.three },
  line: { flexDirection: 'row', alignItems: 'flex-start', gap: Spacing.three },
  flex: { flex: 1 },
  toggle: { alignSelf: 'stretch' },
  summary: { gap: Spacing.three },
  details: { gap: Spacing.six },
  sectionGap: { gap: Spacing.four },
  items: { gap: Spacing.five },
});
