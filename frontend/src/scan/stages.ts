// The pipeline steps, in the order of the n8n workflow (deploy/n8n/workflows/AI-Cosmetic-Scanner.json).
export const STAGES = [
  { id: 'product', running: 'Reading the product and its ingredient list', done: 'Ingredient list read' },
  { id: 'regulatory', running: 'Checking EU cosmetics rules', done: 'EU rules checked' },
  { id: 'toxicology', running: 'Reviewing hazard classifications', done: 'Hazard classifications reviewed' },
  { id: 'ethics', running: 'Looking for cruelty-free evidence', done: 'Cruelty-free evidence checked' },
  { id: 'report', running: 'Building the report and checking its sources', done: 'Report built and checked' },
  { id: 'validation', running: 'Re-reading each claim against its source', done: 'Claims re-read' },
] as const;

export type StageId = (typeof STAGES)[number]['id'];

export function stageIndex(id: string | null | undefined): number {
  return STAGES.findIndex((s) => s.id === id);
}
