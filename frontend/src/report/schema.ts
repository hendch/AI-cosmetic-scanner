// Mirrors app/report/schemas.py (report_version 0.1). Keep the two in sync:
// tests/report.test.ts checks this schema against a complete report.
import { z } from 'zod';

const Confidence = z.enum(['high', 'medium', 'low']);

export const RegulatoryStatus = z.enum(['prohibited', 'restricted', 'permitted', 'no_rule_found', 'not_assessed']);
export const ConcernLevel = z.enum(['none_identified', 'low', 'moderate', 'high', 'insufficient_evidence']);
export const CrueltyFreeStatus = z.enum(['VERIFIED', 'CLAIMED', 'CONFLICTING', 'NOT_VERIFIED', 'NOT_ASSESSED']);

const Product = z.object({
  name: z.string(),
  brand: z.string(),
  barcode: z.string(),
  category: z.string().nullable().optional(),
  exposure_type: z.enum(['leave_on', 'rinse_off']).nullable().optional(),
  labels: z.array(z.string()),
});

const IngredientCard = z.object({
  position: z.number().int(),
  ingredient: z.string(),
  raw: z.string(),
  matched: z.boolean(),
  covered: z.boolean(),
  regulatory_status: RegulatoryStatus,
  regulatory_explanation: z.string(),
  annex_entry: z.string().nullable().optional(),
  conditions: z.array(z.string()),
  concern_level: ConcernLevel,
  hazards: z.array(z.object({ endpoint: z.string(), classification: z.string(), source_id: z.string() })),
  risk_interpretation: z.string(),
  missing_information: z.array(z.string()),
  evidence_confidence: Confidence,
  sources: z.array(z.string()),
});

const ValidationCheck = z.object({
  name: z.string(),
  severity: z.enum(['error', 'warning']),
  passed: z.boolean(),
  description: z.string(),
  issues: z.array(z.string()),
});

export const ReportSchema = z.object({
  report_version: z.literal('0.1'),
  generated_at: z.string(),
  input_source: z.string(),
  product: Product,
  needs_review: z.boolean(),
  overview: z.object({
    total_ingredients: z.number().int(),
    prohibited: z.number().int(),
    restricted: z.number().int(),
    concentration_unknown: z.number().int(),
    hazard_classified: z.number().int(),
    not_covered: z.number().int(),
    unrecognised: z.number().int(),
  }),
  ingredients: z.array(IngredientCard),
  cruelty_free: z.object({
    status: CrueltyFreeStatus,
    status_reason: z.string(),
    brand_claim_found: z.boolean(),
    certifications_found: z.array(z.string()),
    certifications_checked: z.array(z.string()),
    conflicts: z.array(z.string()),
    missing_information: z.array(z.string()),
    evidence_confidence: Confidence,
    sources: z.array(z.string()),
  }),
  evidence_coverage: z.object({
    covered: z.number().int(),
    total: z.number().int(),
    percent: z.number().int(),
    definition: z.string(),
  }),
  sources: z.array(
    z.object({
      source_id: z.string(),
      in_corpus: z.boolean(),
      title: z.string().nullable().optional(),
      publisher: z.string().nullable().optional(),
      publication_date: z.string().nullable().optional(),
      url: z.string().nullable().optional(),
    }),
  ),
  validation: z.object({ passed: z.boolean(), checks: z.array(ValidationCheck) }),
  prompt_versions: z.record(z.string(), z.string().nullable()),
  warnings: z.array(z.string()),
  limitations: z.array(z.string()),
});

export type Report = z.infer<typeof ReportSchema>;
export type Ingredient = Report['ingredients'][number];
export type Source = Report['sources'][number];
