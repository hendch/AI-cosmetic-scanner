import { CaretDownIcon, CaretUpIcon, ShieldCheckIcon, WarningCircleIcon } from 'phosphor-react-native';
import { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { Panel, Txt } from '@/components/ui';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { summarizeCitations } from '@/report/citations';
import type { Report } from '@/report/schema';

export function ValidationBanner({ report }: { report: Report }) {
  const theme = useTheme();
  const [open, setOpen] = useState(false);
  const citations = summarizeCitations(report);
  const failed = report.validation.checks.filter((c) => !c.passed);
  const consistent = citations.unlisted.length === 0;
  const passed = report.validation.passed && consistent;

  const Icon = passed ? ShieldCheckIcon : WarningCircleIcon;
  const tone = passed ? 'clear' : 'attention';

  return (
    <Panel>
      <View style={styles.titleRow}>
        <Icon size={22} color={theme[tone]} weight="fill" />
        <Txt variant="strong" style={styles.flex}>
          {passed ? 'Every finding cites a source from the corpus' : 'Some findings could not be verified'}
        </Txt>
      </View>
      <Txt muted>
        {citations.inCorpus} of {citations.cited} cited sources are in the project’s evidence corpus.
      </Txt>

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
          The report cites sources it does not list: {citations.unlisted.join(', ')}.
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
