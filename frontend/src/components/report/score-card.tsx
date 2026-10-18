// The top of the report, as in the approved sketch: the score ring with its verdict, three
// count tiles, and (inside the full report) the short conclusion and how the score works.
import { CheckCircleIcon, QuestionIcon, WarningCircleIcon, XCircleIcon } from 'phosphor-react-native';
import { StyleSheet, View } from 'react-native';
import Svg, { Circle } from 'react-native-svg';

import { Panel, Radius, Txt } from '@/components/ui';
import { Spacing, type Tone } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import type { Report } from '@/report/schema';
import type { ProductScore } from '@/report/score';

const TONE_ICON = { clear: CheckCircleIcon, attention: WarningCircleIcon, prohibited: XCircleIcon, unknown: QuestionIcon } as const;

const CRUELTY_TILE: Record<Report['cruelty_free']['status'], { value: string; tone: Tone }> = {
  verified: { value: 'Yes', tone: 'clear' },
  claimed: { value: 'Claim', tone: 'attention' },
  conflicting: { value: 'Mixed', tone: 'attention' },
  not_verified: { value: '?', tone: 'unknown' },
  not_assessed: { value: '?', tone: 'unknown' },
};

const SIZE = 92;
const STROKE = 8;
const R = (SIZE - STROKE) / 2;
const CIRCUMFERENCE = 2 * Math.PI * R;

function ScoreRing({ score, tone }: { score: number; tone: Tone }) {
  const theme = useTheme();
  const shown = Number.isInteger(score) ? String(score) : score.toFixed(1);
  return (
    <View style={styles.ring} accessible accessibilityLabel={`Score ${shown} out of 10`}>
      <Svg width={SIZE} height={SIZE}>
        <Circle cx={SIZE / 2} cy={SIZE / 2} r={R} stroke={theme.surfaceAlt} strokeWidth={STROKE} fill="none" />
        <Circle
          cx={SIZE / 2}
          cy={SIZE / 2}
          r={R}
          stroke={theme[tone]}
          strokeWidth={STROKE}
          fill="none"
          strokeLinecap="round"
          strokeDasharray={`${CIRCUMFERENCE} ${CIRCUMFERENCE}`}
          strokeDashoffset={CIRCUMFERENCE * (1 - score / 10)}
          transform={`rotate(-90 ${SIZE / 2} ${SIZE / 2})`}
        />
      </Svg>
      <View style={styles.ringLabel} pointerEvents="none">
        <Txt style={[styles.number, { color: theme.text }]}>{shown}</Txt>
      </View>
    </View>
  );
}

export function ScoreCard({ result, needsReview }: { result: ProductScore; needsReview: boolean }) {
  return (
    <Panel style={styles.card}>
      <ScoreRing score={result.score} tone={result.band.tone} />
      <View style={styles.verdict}>
        <Txt variant="strong" tone={result.band.tone}>
          {result.band.label}
        </Txt>
        <Txt variant="small" muted>
          {result.assessed} of {result.total} ingredients in our sources
        </Txt>
        {needsReview && (
          <Txt variant="small" tone="attention">
            Some checks did not pass. See the full report.
          </Txt>
        )}
      </View>
    </Panel>
  );
}

function Tile({ value, label, tone }: { value: string | number; label: string; tone: Tone }) {
  const theme = useTheme();
  return (
    <View style={[styles.tile, { backgroundColor: theme.surface }]}>
      <Txt variant="heading" tone={tone} style={styles.tileValue}>
        {value}
      </Txt>
      <Txt variant="small" muted>
        {label}
      </Txt>
    </View>
  );
}

export function StatTiles({ report }: { report: Report }) {
  const banned = report.ingredients.filter((i) => i.regulatory.status === 'prohibited').length;
  const limits = report.ingredients.filter((i) => i.regulatory.status === 'restricted').length;
  const cruelty = CRUELTY_TILE[report.cruelty_free.status];
  return (
    <View style={styles.tiles}>
      <Tile value={banned} label="banned" tone={banned ? 'prohibited' : 'clear'} />
      <Tile value={limits} label="limits" tone={limits ? 'attention' : 'clear'} />
      <Tile value={cruelty.value} label="cruelty" tone={cruelty.tone} />
    </View>
  );
}

export function Conclusion({ result }: { result: ProductScore }) {
  const theme = useTheme();
  return (
    <View style={styles.lines}>
      {result.conclusion.map((line) => {
        const Icon = TONE_ICON[line.tone];
        return (
          <View key={line.text} style={styles.line}>
            <Icon size={20} color={theme[line.tone]} weight="fill" />
            <Txt style={styles.flex}>{line.text}</Txt>
          </View>
        );
      })}
    </View>
  );
}

export function ScoreExplanation({ result }: { result: ProductScore }) {
  const theme = useTheme();
  return (
    <View style={styles.lines}>
      {result.factors.length === 0 ? (
        <Txt>Nothing was deducted: no restriction, hazard classification or animal-testing doubt was found.</Txt>
      ) : (
        result.factors.map((f) => (
          <View key={f.text} style={styles.factor}>
            <Txt style={styles.flex}>{f.text}</Txt>
            <Txt variant="strong" style={{ color: theme.textSecondary }}>
              -{f.points}
            </Txt>
          </View>
        ))
      )}
      <Txt variant="small" muted>
        The score starts at 10 and summarises what this report found in the EU cosmetics rules, hazard classifications and
        animal-testing lists. A prohibited ingredient caps it at 2. It is not a safety rating: labels never give
        concentrations, and ingredients our sources do not cover are not counted.
      </Txt>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { flexDirection: 'row', alignItems: 'center', gap: Spacing.four },
  ring: { width: SIZE, height: SIZE, alignItems: 'center', justifyContent: 'center' },
  ringLabel: { position: 'absolute', alignItems: 'center' },
  number: { fontSize: 28, lineHeight: 32, fontWeight: '700', fontVariant: ['tabular-nums'] },
  verdict: { flex: 1, gap: Spacing.one },
  tiles: { flexDirection: 'row', gap: Spacing.two },
  tile: { flex: 1, borderRadius: Radius.tile, paddingVertical: Spacing.three, alignItems: 'center' },
  tileValue: { fontVariant: ['tabular-nums'] },
  lines: { gap: Spacing.three },
  line: { flexDirection: 'row', alignItems: 'flex-start', gap: Spacing.three },
  factor: { flexDirection: 'row', alignItems: 'baseline', gap: Spacing.three },
  flex: { flex: 1 },
});
