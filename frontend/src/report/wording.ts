// Plain-language labels for the report's machine values, and the tone
// (status colour) used for each ingredient everywhere it appears.
import type { Tone } from '@/constants/theme';

import type { Ingredient, Report } from './schema';

export function ingredientTone(i: Ingredient): Tone {
  if (i.regulatory_status === 'prohibited') return 'prohibited';
  if (!i.matched || !i.covered) return 'unknown';
  if (i.regulatory_status === 'restricted' || i.hazards.length > 0) return 'attention';
  return 'clear';
}

export const toneLegend: Record<Tone, string> = {
  prohibited: 'Not allowed for this product type',
  attention: 'Restricted, or has a hazard classification',
  clear: 'No restriction or hazard found in the evidence',
  unknown: 'Not covered by the current corpus',
};

export const regulatoryLabel: Record<Ingredient['regulatory_status'], string> = {
  prohibited: 'Not allowed',
  restricted: 'Restricted',
  permitted: 'Allowed',
  no_rule_found: 'No restriction found',
  not_assessed: 'Not assessed',
};

export const concernLabel: Record<Ingredient['concern_level'], string> = {
  none_identified: 'No concern identified',
  low: 'Low concern',
  moderate: 'Moderate concern',
  high: 'High concern',
  insufficient_evidence: 'Not enough evidence',
};

export const confidenceLabel = { high: 'High', medium: 'Medium', low: 'Low' } as const;

export const crueltyFreeLabel: Record<Report['cruelty_free']['status'], { title: string; tone: Tone }> = {
  VERIFIED: { title: 'Independently certified', tone: 'clear' },
  CLAIMED: { title: 'Claimed by the brand, not certified', tone: 'attention' },
  CONFLICTING: { title: 'Sources disagree', tone: 'attention' },
  NOT_VERIFIED: { title: 'No verifiable evidence', tone: 'unknown' },
  NOT_ASSESSED: { title: 'Not assessed', tone: 'unknown' },
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
      ? { tone: 'prohibited', text: `${plural(o.prohibited, 'ingredient is', 'ingredients are')} not allowed for this product type` }
      : { tone: 'clear', text: 'No prohibited ingredient found' },
  );
  if (o.restricted) lines.push({ tone: 'attention', text: `${plural(o.restricted, 'ingredient is', 'ingredients are')} restricted` });
  if (o.hazard_classified)
    lines.push({ tone: 'attention', text: `${plural(o.hazard_classified, 'ingredient has', 'ingredients have')} a hazard classification` });
  if (o.concentration_unknown)
    lines.push({ tone: 'unknown', text: `Concentration unknown for ${plural(o.concentration_unknown, 'ingredient', 'ingredients')}` });
  if (o.not_covered)
    lines.push({ tone: 'unknown', text: `${plural(o.not_covered, 'ingredient is', 'ingredients are')} not covered by the current corpus` });
  return lines;
}
