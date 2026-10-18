// The product's rating out of 10 and the short conclusion shown above the full report.
// Deterministic and shown in full under "How the score works": it summarises what the report
// found (EU rules, hazard classifications, animal testing), never a safety verdict.
import type { Tone } from '@/constants/theme';

import type { Ingredient, Report } from './schema';
import { crueltyFreeLabel, displayName } from './wording';

export type ScoreFactor = { text: string; points: number };
export type Confidence = 'high' | 'medium' | 'low';
export type ProductScore = {
  score: number; // 0-10, steps of 0.5
  band: { label: string; tone: Tone };
  factors: ScoreFactor[]; // what was deducted, largest first
  assessed: number; // ingredients our sources cover
  total: number;
  confidence: Confidence;
  conclusion: { tone: Tone; text: string }[];
};

const CRUELTY_POINTS: Record<Report['cruelty_free']['status'], number> = {
  verified: 0,
  claimed: 0.25,
  not_verified: 0.5,
  not_assessed: 0.5,
  conflicting: 1,
};

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;
/** "Sodium benzoate", "Sodium benzoate and piroctone olamine", "Sodium benzoate, piroctone olamine and 1 more". */
function names(list: Ingredient[]): string {
  const shown = list.slice(0, 2).map((i, n) => (n === 0 ? displayName(i.ingredient_id) : i.ingredient_id.toLowerCase()));
  if (list.length > 2) return `${shown.join(', ')} and ${list.length - 2} more`;
  return shown.join(' and ');
}

export function productScore(report: Report): ProductScore {
  const ings = report.ingredients;
  const prohibited = ings.filter((i) => i.regulatory.status === 'prohibited');
  const notMet = ings.filter((i) => i.regulatory.status === 'restricted' && i.regulatory.compliance_check === 'not_satisfied');
  const openConditions = ings.filter((i) => i.regulatory.status === 'restricted' && i.regulatory.compliance_check === 'unknown');
  const hazards = ings.filter((i) => i.toxicology.hazards.length > 0);
  const cf = report.cruelty_free;

  const factors: ScoreFactor[] = [];
  if (prohibited.length) factors.push({ text: `${plural(prohibited.length, 'ingredient', 'ingredients')} prohibited in EU cosmetics`, points: 5 * prohibited.length });
  if (notMet.length) factors.push({ text: `${plural(notMet.length, 'ingredient does', 'ingredients do')} not meet an EU condition for this product`, points: 3 * notMet.length });
  if (hazards.length) factors.push({ text: `${plural(hazards.length, 'ingredient has', 'ingredients have')} a hazard classification`, points: Math.min(3, hazards.length) });
  if (openConditions.length)
    factors.push({ text: `${plural(openConditions.length, 'restricted ingredient', 'restricted ingredients')} with a limit that cannot be checked`, points: Math.min(2, 0.5 * openConditions.length) });
  if (CRUELTY_POINTS[cf.status]) factors.push({ text: `Animal testing: ${crueltyFreeLabel[cf.status].title.toLowerCase()}`, points: CRUELTY_POINTS[cf.status] });
  factors.sort((a, b) => b.points - a.points);

  let score = 10 - factors.reduce((sum, f) => sum + f.points, 0);
  if (prohibited.length) score = Math.min(score, 2); // a banned ingredient outweighs everything else
  score = Math.max(0, Math.round(score * 2) / 2);

  const band: ProductScore['band'] =
    score >= 8.5 ? { label: 'Nothing of concern found', tone: 'clear' } : score >= 5 ? { label: 'A few points to check', tone: 'attention' } : { label: 'Significant issues found', tone: 'prohibited' };

  const assessed = ings.filter((i) => i.matched && i.regulatory.status !== 'not_assessed').length;
  const share = ings.length ? assessed / ings.length : 0;
  const confidence: Confidence = share >= 0.7 ? 'high' : share >= 0.4 ? 'medium' : 'low';

  const conclusion: ProductScore['conclusion'] = [];
  conclusion.push(
    prohibited.length
      ? { tone: 'prohibited', text: `Contains ${names(prohibited)}, prohibited in EU cosmetics.` }
      : { tone: 'clear', text: 'No ingredient prohibited in EU cosmetics.' },
  );
  if (notMet.length) conclusion.push({ tone: 'prohibited', text: `${names(notMet)} ${notMet.length === 1 ? 'does' : 'do'} not meet an EU condition for this type of product.` });
  if (openConditions.length)
    conclusion.push({
      tone: 'attention',
      text: `${names(openConditions)} ${openConditions.length === 1 ? 'is' : 'are'} allowed only up to a limit. Labels don't print concentrations, so the limit can't be checked.`,
    });
  if (hazards.length) conclusion.push({ tone: 'attention', text: `${names(hazards)} ${hazards.length === 1 ? 'has' : 'have'} a hazard classification for the pure substance.` });
  conclusion.push({ tone: crueltyFreeLabel[cf.status].tone, text: `Animal testing: ${crueltyFreeLabel[cf.status].title.toLowerCase()}.` });

  return { score, band, factors, assessed, total: ings.length, confidence, conclusion };
}
