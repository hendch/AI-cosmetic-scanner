// Mirrors app/report/schemas.py (Report, report_version 1.0) and the n8n answer
// (docs/N8N_SETUP.md). Keep them in sync: tests/report.test.ts parses a full report.
import { z } from 'zod';

const Confidence = z.enum(['high', 'medium', 'low']);

export const RegulatoryStatus = z.enum(['prohibited', 'restricted', 'no_restriction_found', 'not_assessed']);
export const ComplianceCheck = z.enum(['satisfied', 'not_satisfied', 'unknown', 'not_applicable']);
export const ConcernLevel = z.enum(['none_identified', 'low', 'moderate', 'high', 'insufficient_evidence']);
export const CrueltyFreeStatus = z.enum(['verified', 'claimed', 'conflicting', 'not_verified', 'not_assessed']);

const ConditionSchema = z.object({
  entry: z.string(),
  type: z.enum(['product_type', 'max_concentration', 'population', 'usage', 'labelling']),
  requirement: z.string(),
  result: ComplianceCheck,
  reason: z.string(),
});

const IngredientReport = z.object({
  position: z.number().int(),
  ingredient_id: z.string(),
  raw: z.string(),
  matched: z.boolean(),
  concentration_percent: z.number().nullable().optional(),
  covered: z.boolean(),
  regulatory: z.object({
    status: RegulatoryStatus,
    compliance_check: ComplianceCheck,
    entries: z.array(z.string()),
    conditions: z.array(ConditionSchema),
    explanation: z.string(),
    evidence_ids: z.array(z.string()),
  }),
  toxicology: z.object({
    concern_level: ConcernLevel,
    hazards: z.array(z.object({ endpoint: z.string(), label: z.string(), evidence_ids: z.array(z.string()) })),
    explanation: z.string(),
    evidence_ids: z.array(z.string()),
  }),
  missing_information: z.array(z.string()),
  evidence_confidence: Confidence,
});

const ValidationCheck = z.object({
  name: z.string(),
  severity: z.enum(['error', 'warning']),
  passed: z.boolean(),
  description: z.string(),
  issues: z.array(z.string()),
});

export const ReportSchema = z.object({
  report_version: z.literal('1.0'),
  generated_at: z.string(),
  input_source: z.enum(['barcode', 'ocr']).nullable(),
  product: z.object({
    name: z.string(),
    brand: z.string(),
    barcode: z.string(),
    category: z.string().nullable().optional(),
    exposure_type: z.enum(['leave_on', 'rinse_off']).nullable().optional(),
  }),
  needs_review: z.boolean(),
  overview: z.object({
    total_ingredients: z.number().int(),
    prohibited: z.number().int(),
    restricted: z.number().int(),
    conditions_not_met: z.number().int(),
    conditions_unknown: z.number().int(),
    concentration_unknown: z.number().int(),
    hazard_classified: z.number().int(),
    not_assessed: z.number().int(),
  }),
  ingredients: z.array(IngredientReport),
  cruelty_free: z.object({
    status: CrueltyFreeStatus,
    explanation: z.string(),
    brand_claim_found: z.boolean(),
    certifications_found: z.array(z.string()),
    certifications_checked: z.array(z.string()),
    conflicts: z.array(z.string()),
    evidence_ids: z.array(z.string()),
    evidence_confidence: Confidence,
  }),
  evidence_coverage: z.object({
    covered: z.number().int(),
    total: z.number().int(),
    percent: z.number().int(),
    definition: z.string(),
  }),
  sources: z.array(
    z.object({
      evidence_id: z.string(),
      source_id: z.string(),
      kind: z.string(),
      excerpt: z.string(),
      title: z.string().nullable().optional(),
      publisher: z.string().nullable().optional(),
      date: z.string().nullable().optional(),
      url: z.string().nullable().optional(),
      in_corpus: z.boolean(),
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
export type Condition = z.infer<typeof ConditionSchema>;
