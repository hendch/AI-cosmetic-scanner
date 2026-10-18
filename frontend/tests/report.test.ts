import { describe, expect, it } from 'vitest';

import { summarizeCitations } from '@/report/citations';
import { ReportSchema, type Ingredient, type Report } from '@/report/schema';
import { displayName, ingredientTone, overviewLines } from '@/report/wording';
import { productScore } from '@/report/score';
import { estimatedStage } from '@/scan/estimate';
import { gtinProblem } from '@/scan/gtin';

// A real report from the API: Balea barcode 4066447870213 through /ingestion/scan, the three
// agents (regulatory rules only) and /report/build. If the API's Report changes, regenerate it.
import balea from './fixtures/report-balea.json';

const real = ReportSchema.parse(balea);

function ingredient(overrides: Partial<Ingredient> = {}): Ingredient {
  return {
    position: 1,
    ingredient_id: 'PHENOXYETHANOL',
    raw: 'Phenoxyethanol',
    matched: true,
    concentration_percent: null,
    covered: true,
    regulatory: {
      status: 'restricted',
      compliance_check: 'unknown',
      entries: ['V/29'],
      conditions: [
        { entry: 'V/29', type: 'max_concentration', requirement: 'At most 1%', result: 'unknown', reason: 'Concentration not on the label.' },
      ],
      explanation: 'Allowed as a preservative up to 1%.',
      evidence_ids: ['eu_1223_2009_annex_v#29'],
    },
    toxicology: { concern_level: 'none_identified', hazards: [], explanation: 'No classification found.', evidence_ids: [] },
    missing_information: ['concentration'],
    evidence_confidence: 'high',
    ...overrides,
  };
}

function report(overrides: Partial<Report> = {}): Report {
  return { ...real, ingredients: [ingredient()], ...overrides };
}

const annexSource = {
  evidence_id: 'eu_1223_2009_annex_v#29',
  source_id: 'eu_1223_2009_annex_v',
  kind: 'regulation',
  excerpt: 'Phenoxyethanol, 1 %',
  in_corpus: true,
};

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
  it('accepts a real report from the API', () => {
    expect(real.report_version).toBe('1.0');
    expect(real.ingredients.length).toBe(real.overview.total_ingredients);
  });
  it('rejects an unknown regulatory status', () => {
    const bad = { ...balea, ingredients: [{ ...balea.ingredients[0], regulatory: { ...balea.ingredients[0].regulatory, status: 'banned' } }] };
    expect(ReportSchema.safeParse(bad).success).toBe(false);
  });
  it('rejects the old report format', () => {
    expect(ReportSchema.safeParse({ ...balea, report_version: '0.1' }).success).toBe(false);
  });
});

describe('summarizeCitations', () => {
  it('finds every cited evidence item of the real report in its source list', () => {
    expect(summarizeCitations(real).unlisted).toEqual([]);
  });
  it('counts distinct citations, missing text and sources outside the corpus', () => {
    const r = report({
      ingredients: [
        ingredient(),
        ingredient({
          position: 2,
          ingredient_id: 'GLYCERIN',
          regulatory: { ...ingredient().regulatory, evidence_ids: ['eu_1223_2009_annex_v#29', 'blog#1'] },
        }),
      ],
      cruelty_free: { ...real.cruelty_free, evidence_ids: [] },
      sources: [annexSource, { evidence_id: 'blog#1', source_id: 'blog', kind: 'other', excerpt: '', in_corpus: false }],
    });
    expect(summarizeCitations(r)).toEqual({ cited: 2, withText: 1, notInCorpus: ['blog#1'], unlisted: [] });
  });
  it('flags citations missing from the source list', () => {
    const r = report({
      cruelty_free: { ...real.cruelty_free, evidence_ids: [] },
      sources: [],
    });
    expect(summarizeCitations(r).unlisted).toEqual(['eu_1223_2009_annex_v#29']);
  });
});

describe('ingredientTone', () => {
  const reg = ingredient().regulatory;
  it('maps statuses to tones', () => {
    expect(ingredientTone(ingredient({ regulatory: { ...reg, status: 'prohibited' } }))).toBe('prohibited');
    expect(ingredientTone(ingredient({ regulatory: { ...reg, compliance_check: 'not_satisfied' } }))).toBe('prohibited');
    expect(ingredientTone(ingredient())).toBe('attention');
    expect(ingredientTone(ingredient({ regulatory: { ...reg, status: 'no_restriction_found' } }))).toBe('clear');
    expect(ingredientTone(ingredient({ regulatory: { ...reg, status: 'not_assessed' } }))).toBe('unknown');
    expect(ingredientTone(ingredient({ matched: false }))).toBe('unknown');
  });
  it('marks a hazard classification as attention', () => {
    const hazard = { endpoint: 'sensitisation', label: 'Skin Sens. 1 (H317)', evidence_ids: [] };
    const tox = { ...ingredient().toxicology, hazards: [hazard] };
    expect(ingredientTone(ingredient({ regulatory: { ...reg, status: 'no_restriction_found' }, toxicology: tox }))).toBe('attention');
  });
});

describe('overviewLines', () => {
  it('describes the real report in plain sentences', () => {
    const o = real.overview;
    const texts = overviewLines(real).map((l) => l.text);
    expect(texts[0]).toEqual(o.prohibited ? expect.stringContaining('prohibited') : 'No prohibited ingredient found');
    if (o.restricted) expect(texts).toContain(`${o.restricted} ingredients are allowed only under conditions`);
  });
  it('reports conditions not met as prohibited-tone lines', () => {
    const r = report({ overview: { ...real.overview, prohibited: 0, conditions_not_met: 1 } });
    expect(overviewLines(r)).toContainEqual({ tone: 'prohibited', text: '1 restricted ingredient does not meet a condition for this product' });
  });
});

describe('displayName', () => {
  it('turns INCI names into sentence case', () => {
    expect(displayName('SODIUM BENZOATE')).toBe('Sodium benzoate');
    expect(displayName('aqua')).toBe('Aqua');
  });
});

describe('estimatedStage', () => {
  it('follows typical timings and holds the last step until the answer arrives', () => {
    expect(estimatedStage(0, false)).toBe('product');
    expect(estimatedStage(5, false)).toBe('regulatory');
    expect(estimatedStage(5, true)).toBe('product'); // a label photo is read by OCR first
    expect(estimatedStage(300, false)).toBe('validation');
  });
});

describe('productScore', () => {
  it('scores the real Balea report and explains every deduction', () => {
    const s = productScore(real);
    const deducted = s.factors.reduce((sum, f) => sum + f.points, 0);
    expect(s.score).toBe(Math.max(0, Math.round((10 - deducted) * 2) / 2));
    expect(s.conclusion[0].text).toBe('No ingredient prohibited in EU cosmetics.');
    expect(s.total).toBe(real.ingredients.length);
  });
  it('caps the score when an ingredient is prohibited', () => {
    const reg = ingredient().regulatory;
    const r = report({ ingredients: [ingredient({ regulatory: { ...reg, status: 'prohibited', compliance_check: 'not_applicable' } })] });
    const s = productScore(r);
    expect(s.score).toBeLessThanOrEqual(2);
    expect(s.band.tone).toBe('prohibited');
    expect(s.conclusion[0].tone).toBe('prohibited');
  });
  it('gives a high score when nothing is restricted and animal testing is verified', () => {
    const reg = ingredient().regulatory;
    const r = report({
      ingredients: [ingredient({ regulatory: { ...reg, status: 'no_restriction_found', compliance_check: 'not_applicable', conditions: [] } })],
      cruelty_free: { ...real.cruelty_free, status: 'verified' },
    });
    expect(productScore(r)).toMatchObject({ score: 10, band: { tone: 'clear' }, confidence: 'high' });
  });
});
