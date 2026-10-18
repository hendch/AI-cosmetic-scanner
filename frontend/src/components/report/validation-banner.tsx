// What the report was checked against: the rule checks (they decide whether the report
// needs review) and the AI validator's re-reading of each claim (advisory).
import { CaretDownIcon, CaretUpIcon, ShieldCheckIcon, WarningCircleIcon } from 'phosphor-react-native';
import { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { Panel, Txt } from '@/components/ui';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { summarizeCitations } from '@/report/citations';
import type { Report } from '@/report/schema';
import { AI_CHECK } from '@/report/wording';

export function ValidationBanner({ report, needsReview }: { report: Report; needsReview: boolean }) {
  const theme = useTheme();
  const [open, setOpen] = useState(false);
  const citations = summarizeCitations(report);
  const failed = report.validation.checks.filter((c) => !c.passed);
  const ai = report.validation.checks.find((c) => c.name === AI_CHECK);
  const consistent = citations.unlisted.length === 0;
  const passed = !needsReview && report.validation.passed && consistent;

  const Icon = passed ? ShieldCheckIcon : WarningCircleIcon;
  const tone = passed ? 'clear' : 'attention';

  return (
    <Panel>
      <View style={styles.titleRow}>
        <Icon size={22} color={theme[tone]} weight="fill" />
        <Txt variant="strong" style={styles.flex}>
          {passed ? 'The report passed its checks' : 'This report needs review'}
        </Txt>
      </View>
      <Txt muted>
        {citations.withText} of {citations.cited} cited evidence items come with the source text the finding rests on.
      </Txt>
      {ai && (
        <Txt variant="small" muted>
          {ai.passed
            ? 'AI validator: every claim it checked is supported by its cited text.'
            : `AI validator: ${ai.issues.length || 'some'} ${ai.issues.length === 1 ? 'issue' : 'issues'} flagged. This check is advisory.`}
        </Txt>
      )}
      {citations.notInCorpus.length > 0 && (
        <Txt variant="small" tone="attention">
          Cited but not in the evidence corpus: {citations.notInCorpus.join(', ')}.
        </Txt>
      )}

      {failed.length > 0 && (
        <>
          <Pressable
            accessibilityRole="button"
            accessibilityState={{ expanded: open }}
            onPress={() => setOpen((o) => !o)}
            style={styles.toggle}>
            <Txt variant="strong" style={{ color: theme.accent }}>
              {open ? 'Hide checks' : `Show ${failed.length} failed ${failed.length === 1 ? 'check' : 'checks'}`}
            </Txt>
            {open ? <CaretUpIcon size={16} color={theme.accent} weight="bold" /> : <CaretDownIcon size={16} color={theme.accent} weight="bold" />}
          </Pressable>
          {open &&
            failed.map((check) => (
              <View key={check.name} style={styles.check}>
                <Txt variant="small" style={{ fontWeight: '600' }} tone={check.severity === 'error' ? 'prohibited' : 'attention'}>
                  {check.description}
                  {check.severity === 'warning' ? ' (warning)' : ''}
                </Txt>
                {check.issues.map((issue) => (
                  <Txt key={issue} variant="small" muted>
                    {issue}
                  </Txt>
                ))}
              </View>
            ))}
        </>
      )}
      {!consistent && (
        <Txt variant="small" tone="prohibited">
          The report cites evidence it does not list: {citations.unlisted.join(', ')}.
        </Txt>
      )}
    </Panel>
  );
}

const styles = StyleSheet.create({
  titleRow: { flexDirection: 'row', alignItems: 'center', gap: Spacing.two },
  flex: { flex: 1 },
  toggle: { flexDirection: 'row', alignItems: 'center', gap: Spacing.one, alignSelf: 'flex-start', minHeight: 32 },
  check: { gap: 2 },
});
