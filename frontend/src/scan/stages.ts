// The pipeline steps in n8n's order. n8n reports the step it is on by its id.
export const STAGES = [
  { id: 'product', running: 'Identifying the product', done: 'Product identified' },
  { id: 'ingredients', running: 'Reading the ingredient list', done: 'Ingredient list read' },
  { id: 'normalize', running: 'Matching ingredient names', done: 'Ingredient names matched' },
  { id: 'evidence', running: 'Retrieving regulatory and scientific evidence', done: 'Evidence retrieved' },
  { id: 'regulatory', running: 'Checking EU cosmetics rules', done: 'EU rules checked' },
  { id: 'toxicology', running: 'Reviewing hazard classifications', done: 'Hazard classifications reviewed' },
  { id: 'ethics', running: 'Looking for cruelty-free evidence', done: 'Cruelty-free evidence checked' },
  { id: 'validation', running: 'Checking every citation', done: 'Citations checked' },
] as const;

export type StageId = (typeof STAGES)[number]['id'];

export function stageIndex(id: string | null | undefined): number {
  return STAGES.findIndex((s) => s.id === id);
}
