// The ingredient list as printed on the back of the product, each name underlined
// in its status colour. Tapping a name jumps to its details.
import { Fragment } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { Panel, Txt } from '@/components/ui';
import { Spacing, Type, type Tone } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import type { Ingredient } from '@/report/schema';
import { ingredientTone, toneLegend } from '@/report/wording';

const TONE_ORDER: Tone[] = ['prohibited', 'attention', 'clear', 'unknown'];

export function AnnotatedLabel({ ingredients, onSelect }: { ingredients: Ingredient[]; onSelect: (ingredient: string) => void }) {
  const theme = useTheme();
  const tones = ingredients.map(ingredientTone);
  const present = TONE_ORDER.filter((t) => tones.includes(t));

  return (
    <Panel>
      <Txt variant="small" muted>
        Ingredients, as listed on the product
      </Txt>
      <Text style={[Type.inci, { color: theme.text }]}>
        {ingredients.map((ing, i) => (
          <Fragment key={ing.position}>
            <Text
              accessibilityRole="link"
              accessibilityHint={`${toneLegend[tones[i]]}. Shows details.`}
              onPress={() => onSelect(ing.ingredient)}
              style={[
                styles.name,
                {
                  color: theme[tones[i]],
                  textDecorationColor: theme[tones[i]],
                  textDecorationStyle: tones[i] === 'unknown' ? 'dotted' : 'solid',
                },
              ]}>
              {ing.raw.toUpperCase()}
            </Text>
            {i < ingredients.length - 1 ? ', ' : '.'}
          </Fragment>
        ))}
      </Text>
      <View style={styles.legend}>
        {present.map((tone) => (
          <View key={tone} style={styles.legendRow}>
            <View style={[styles.swatch, { backgroundColor: theme[tone] }]} />
            <Txt variant="small" muted>
              {toneLegend[tone]}
            </Txt>
          </View>
        ))}
      </View>
    </Panel>
  );
}

const styles = StyleSheet.create({
  name: { textDecorationLine: 'underline' },
  legend: { gap: Spacing.one, paddingTop: Spacing.two },
  legendRow: { flexDirection: 'row', alignItems: 'center', gap: Spacing.two },
  swatch: { width: 14, height: 3, borderRadius: 2 },
});
