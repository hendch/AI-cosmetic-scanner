// The first ingredients as pills in their status colour (most notable first), and "+N" for the rest.
// Tapping a pill opens the full report at that ingredient; "+N" opens the full report.
import { Pressable, StyleSheet, View } from 'react-native';

import { Panel, Radius, Txt } from '@/components/ui';
import { Spacing, type Tone } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import type { Ingredient } from '@/report/schema';
import { displayName, ingredientTone, toneLegend } from '@/report/wording';

const SHOWN = 6;
const RANK: Record<Tone, number> = { prohibited: 0, attention: 1, clear: 2, unknown: 3 };

export function IngredientPills({ ingredients, onSelect, onMore }: { ingredients: Ingredient[]; onSelect: (id: string) => void; onMore: () => void }) {
  const theme = useTheme();
  const ranked = ingredients
    .map((ing) => ({ ing, tone: ingredientTone(ing) }))
    .sort((a, b) => RANK[a.tone] - RANK[b.tone] || a.ing.position - b.ing.position);
  const rest = ranked.length - SHOWN;
  return (
    <Panel>
      <Txt variant="strong" accessibilityRole="header">
        Ingredients
      </Txt>
      <View style={styles.wrap}>
        {ranked.slice(0, SHOWN).map(({ ing, tone }) => (
          <Pressable
            key={ing.position}
            accessibilityRole="button"
            accessibilityLabel={`${displayName(ing.ingredient_id)}: ${toneLegend[tone]}`}
            accessibilityHint="Shows its details"
            onPress={() => onSelect(ing.ingredient_id)}
            style={({ pressed }) => [styles.pill, { backgroundColor: theme[`${tone}Soft`] }, pressed && styles.pressed]}>
            <Txt variant="caption" tone={tone}>
              {displayName(ing.ingredient_id)}
            </Txt>
          </Pressable>
        ))}
        {rest > 0 && (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={`${rest} more ingredients`}
            onPress={onMore}
            style={({ pressed }) => [styles.pill, { backgroundColor: theme.unknownSoft }, pressed && styles.pressed]}>
            <Txt variant="caption" tone="unknown">
              +{rest}
            </Txt>
          </Pressable>
        )}
      </View>
    </Panel>
  );
}

const styles = StyleSheet.create({
  wrap: { flexDirection: 'row', flexWrap: 'wrap', gap: Spacing.two },
  pill: { borderRadius: Radius.pill, paddingHorizontal: Spacing.three, paddingVertical: 6 },
  pressed: { transform: [{ scale: 0.97 }] },
});
