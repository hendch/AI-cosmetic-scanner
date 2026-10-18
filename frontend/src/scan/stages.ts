// The pipeline steps, in the order of the n8n workflow (deploy/n8n/workflows/AI-Cosmetic-Scanner.json).
export const STAGES = [
  { id: 'product', running: 'Reading the ingredient list', done: 'Ingredient list read' },
  { id: 'regulatory', running: 'Checking EU rules', done: 'EU rules checked' },
  { id: 'toxicology', running: 'Reviewing hazard classifications', done: 'Hazards reviewed' },
  { id: 'ethics', running: 'Cruelty-free evidence', done: 'Cruelty-free evidence checked' },
  { id: 'report', running: 'Building your report', done: 'Report built' },
  { id: 'validation', running: 'Double-checking every claim', done: 'Claims double-checked' },
] as const;

export type StageId = (typeof STAGES)[number]['id'];

export function stageIndex(id: string | null | undefined): number {
  return STAGES.findIndex((s) => s.id === id);
}
