import { describe, expect, it } from 'vitest';

import { summarizeCitations } from '@/report/citations';
import { ReportSchema, type Ingredient, type Report } from '@/report/schema';
import { ingredientTone, overviewLines } from '@/report/wording';
import { gtinProblem } from '@/scan/gtin';

function ingredient(overrides: Partial<Ingredient> = {}): Ingredient {
  return {
    position: 1,
    ingredient: 'phenoxyethanol',
    raw: 'PHENOXYETHANOL',
    matched: true,
    covered: true,
    regulatory_status: 'restricted',
    regulatory_explanation: 'Allowed up to a maximum concentration.',
    annex_entry: 'Annex V/29',
    conditions: ['Maximum 1%'],
    concern_level: 'low',
    hazards: [],
    risk_interpretation: 'Depends on concentration.',
    missing_information: ['concentration'],
    evidence_confidence: 'high',
    sources: ['sccs_phenoxyethanol_2016'],
    ...overrides,
  };
}

function report(overrides: Partial<Report> = {}): Report {
  return {
    report_version: '0.1',
    generated_at: '2026-10-16T12:00:00Z',
    input_source: 'barcode',
    product: { name: 'Face Cream', brand: 'Brand', barcode: '4006381333931', category: 'face cream', exposure_type: 'leave_on', labels: [] },
    needs_review: false,
    overview: { total_ingredients: 1, prohibited: 0, restricted: 1, concentration_unknown: 1, hazard_classified: 0, not_covered: 0, unrecognised: 0 },
    ingredients: [ingredient()],
    cruelty_free: {
      status: 'CLAIMED',
      status_reason: 'Brand claim only.',
      brand_claim_found: true,
      certifications_found: [],
      certifications_checked: ['Leaping Bunny'],
      conflicts: [],
      missing_information: [],
      evidence_confidence: 'medium',
      sources: ['obf_labels'],
    },
    evidence_coverage: { covered: 1, total: 1, percent: 100, definition: 'Evidence presence.' },
    sources: [
      { source_id: 'sccs_phenoxyethanol_2016', in_corpus: true, title: 'SCCS opinion', publisher: 'SCCS', publication_date: '2016-10-06', url: null },
      { source_id: 'obf_labels', in_corpus: true, title: 'Open Beauty Facts product labels', publisher: 'Open Beauty Facts', publication_date: null, url: null },
    ],
    validation: { passed: true, checks: [] },
    prompt_versions: { regulatory: 'v1', toxicology: 'v1', ethics: 'v1' },
    warnings: [],
    limitations: ['Concentrations are unknown.'],
    ...overrides,
  };
}

describe('gtinProblem', () => {
  it('accepts valid EAN-13, EAN-8 and UPC-A numbers', () => {
    expect(gtinProblem('4006381333931')).toBeNull();
    expect(gtinProblem('96385074')).toBeNull();
    expect(gtinProblem('036000291452')).toBeNull();
    expect(gtinProblem('4006 3813 33931')).toBeNull();
  });
  it('rejects wrong lengths, letters and bad check digits', () => {
    expect(gtinProblem('12345')).toMatch(/8, 12 or 13/);
    expect(gtinProblem('40063813339a1')).toMatch(/digits only/);
    expect(gtinProblem('4006381333932')).toMatch(/check digit/);
  });
});

describe('ReportSchema', () => {
  it('accepts a complete report', () => {
    expect(ReportSchema.safeParse(report()).success).toBe(true);
  });
  it('rejects an unknown regulatory status', () => {
    const bad = report({ ingredients: [{ ...ingredient(), regulatory_status: 'banned' as never }] });
    expect(ReportSchema.safeParse(bad).success).toBe(false);
  });
});

describe('summarizeCitations', () => {
  it('counts distinct citations and flags ones outside the corpus', () => {
    const r = report({
      ingredients: [ingredient(), ingredient({ position: 2, ingredient: 'glycerin', sources: ['sccs_phenoxyethanol_2016', 'eu_annex'] })],
      sources: [...report().sources, { source_id: 'eu_annex', in_corpus: false }],
    });
    expect(summarizeCitations(r)).toEqual({ cited: 3, inCorpus: 2, notInCorpus: ['eu_annex'], unlisted: [] });
  });
  it('flags citations missing from the source list', () => {
    const r = report({ ingredients: [ingredient({ sources: ['ghost_source'] })] });
    expect(summarizeCitations(r).unlisted).toEqual(['ghost_source']);
  });
});

describe('ingredientTone', () => {
  it('maps statuses to tones', () => {
    expect(ingredientTone(ingredient({ regulatory_status: 'prohibited' }))).toBe('prohibited');
    expect(ingredientTone(ingredient())).toBe('attention');
    expect(ingredientTone(ingredient({ regulatory_status: 'no_rule_found' }))).toBe('clear');
    expect(ingredientTone(ingredient({ covered: false, regulatory_status: 'not_assessed' }))).toBe('unknown');
    expect(ingredientTone(ingredient({ matched: false }))).toBe('unknown');
  });
});

describe('overviewLines', () => {
  it('states that nothing prohibited was found and lists what is restricted or unknown', () => {
    expect(overviewLines(report()).map((l) => l.text)).toEqual([
      'No prohibited ingredient found',
      '1 ingredient is restricted',
      'Concentration unknown for 1 ingredient',
    ]);
  });
});
