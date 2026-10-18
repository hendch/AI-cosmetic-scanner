// Plain-language labels for the report's machine values, and the tone
// (status colour) used for each ingredient everywhere it appears.
import type { Tone } from '@/constants/theme';

import type { Condition, Ingredient, Report } from './schema';

export function ingredientTone(i: Ingredient): Tone {
  if (i.regulatory.status === 'prohibited') return 'prohibited';
  if (i.regulatory.compliance_check === 'not_satisfied') return 'prohibited';
  if (!i.matched || i.regulatory.status === 'not_assessed') return 'unknown';
  if (i.regulatory.status === 'restricted' || i.toxicology.hazards.length > 0) return 'attention';
  return 'clear';
}

export const toneLegend: Record<Tone, string> = {
  prohibited: 'Prohibited, or a condition is not met for this product',
  attention: 'Restricted, or has a hazard classification',
  clear: 'No restriction found in the regulation checked',
  unknown: 'Not assessed (not recognised or not in our sources yet)',
};

export const regulatoryLabel: Record<Ingredient['regulatory']['status'], string> = {
  prohibited: 'Prohibited',
  restricted: 'Restricted',
  no_restriction_found: 'No restriction found',
  not_assessed: 'Not assessed',
};

export const conditionLabel: Record<Condition['result'], string> = {
  satisfied: 'Met',
  not_satisfied: 'Not met',
  unknown: 'Cannot be checked',
  not_applicable: 'Does not apply',
};

export const conditionTypeLabel: Record<Condition['type'], string> = {
  product_type: 'Product type',
  max_concentration: 'Maximum concentration',
  population: 'Who may use it',
  usage: 'Conditions of use',
  labelling: 'Required label warning',
};

export const concernLabel: Record<Ingredient['toxicology']['concern_level'], string> = {
  none_identified: 'No concern identified',
  low: 'Low concern',
  moderate: 'Moderate concern',
  high: 'High concern',
  insufficient_evidence: 'Not enough evidence',
};

export const confidenceLabel = { high: 'High', medium: 'Medium', low: 'Low' } as const;

export const crueltyFreeLabel: Record<Report['cruelty_free']['status'], { title: string; tone: Tone }> = {
  verified: { title: 'Independently certified', tone: 'clear' },
  claimed: { title: 'Claimed by the brand, not certified', tone: 'attention' },
  conflicting: { title: 'Sources disagree', tone: 'attention' },
  not_verified: { title: 'No verifiable evidence', tone: 'unknown' },
  not_assessed: { title: 'Not assessed', tone: 'unknown' },
};

export const hazardEndpointLabel: Record<string, string> = {
  carcinogenicity: 'Carcinogenicity',
  mutagenicity: 'Mutagenicity',
  reproductive_toxicity: 'Reproductive toxicity',
  sensitisation: 'Skin sensitisation',
  skin_irritation: 'Skin irritation',
  eye_irritation: 'Eye irritation',
  other: 'Other classification',
};

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

/** The overview as short sentences, each with the tone of what it reports. */
export function overviewLines(report: Report): { tone: Tone; text: string }[] {
  const o = report.overview;
  const lines: { tone: Tone; text: string }[] = [];
  lines.push(
    o.prohibited
      ? { tone: 'prohibited', text: `${plural(o.prohibited, 'ingredient is', 'ingredients are')} prohibited in EU cosmetics` }
      : { tone: 'clear', text: 'No prohibited ingredient found' },
  );
  if (o.conditions_not_met)
    lines.push({ tone: 'prohibited', text: `${plural(o.conditions_not_met, 'restricted ingredient does', 'restricted ingredients do')} not meet a condition for this product` });
  if (o.restricted)
    lines.push({ tone: 'attention', text: `${plural(o.restricted, 'ingredient is', 'ingredients are')} allowed only under conditions` });
  if (o.hazard_classified)
    lines.push({ tone: 'attention', text: `${plural(o.hazard_classified, 'ingredient has', 'ingredients have')} a hazard classification` });
  if (o.concentration_unknown)
    lines.push({ tone: 'unknown', text: `Concentration unknown for ${plural(o.concentration_unknown, 'ingredient', 'ingredients')}, so its limit cannot be checked` });
  if (o.not_assessed)
    lines.push({ tone: 'unknown', text: `${plural(o.not_assessed, 'ingredient is', 'ingredients are')} not assessed yet` });
  return lines;
}

export const sourceKindLabel: Record<string, string> = {
  regulation: 'EU regulation',
  coverage_list: 'Regulation coverage list',
  toxicology: 'Toxicology',
  certification: 'Certification list',
  brand_claim: 'Brand claim',
  third_party: 'Third-party source',
  other: 'Other source',
};

/** "SODIUM BENZOATE" or "sodium benzoate" → "Sodium benzoate". */
export function displayName(inci: string): string {
  const lower = inci.toLowerCase();
  return lower.charAt(0).toUpperCase() + lower.slice(1);
}

/** The AI validator's check is advisory; the other checks are the rules the report is held to. */
export const AI_CHECK = 'ai_validator';
