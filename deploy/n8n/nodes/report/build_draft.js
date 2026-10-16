// n8n node "Live - Build draft" (Code, run once for all items). Owner: Omar.
// Merges the regulatory, toxicology and ethics outputs into the report the app shows.
// Deterministic: no LLM. Installed into the workflow by scripts/install_report_nodes.py.

const e = JSON.parse(JSON.stringify($input.first().json));
const pack = e.evidence_pack;
const sources = new Map(pack.sources.map((s) => [s.evidence_id, s]));
const unique = (xs) => [...new Set(xs)];

// A citation counts as coverage only if it exists, is about this ingredient and is the right kind.
const cites = (ids, ingredientId, kind) =>
  Array.isArray(ids) &&
  ids.some((id) => {
    const s = sources.get(id);
    return s && s.kind === kind && s.ingredient_ids.includes(ingredientId);
  });

const regById = new Map(e.regulatory.findings.map((f) => [f.ingredient_id, f]));
const toxById = new Map(e.toxicology.findings.map((f) => [f.ingredient_id, f]));

const ingredients = e.ingredients.map((ing, index) => {
  const reg = regById.get(ing.ingredient_id) || {};
  const tox = toxById.get(ing.ingredient_id) || {};
  const hazards = Array.isArray(tox.hazards) ? tox.hazards : [];
  const regEvidence = Array.isArray(reg.evidence_ids) ? reg.evidence_ids : [];
  const toxEvidence = unique(hazards.flatMap((h) => h.evidence_ids || []));
  const rules = pack.rules.filter((r) => r.ingredient_id === ing.ingredient_id);
  const regulatoryCovered = cites(regEvidence, ing.ingredient_id, 'regulation');
  const toxicologyCovered = hazards.some((h) => cites(h.evidence_ids, ing.ingredient_id, 'toxicology'));
  const concentrationNeeded = rules.some((r) => r.concentration_required) && ing.concentration_percent == null;

  return {
    position: index + 1,
    ingredient_id: ing.ingredient_id,
    name: ing.name,
    concentration_percent: ing.concentration_percent ?? null,
    covered: regulatoryCovered || toxicologyCovered,
    regulatory: {
      status: reg.regulatory_status || 'not_assessed',
      condition_result: reg.condition_result || 'not_assessed',
      explanation: reg.explanation || 'Not covered by the current corpus.',
      evidence_ids: regEvidence,
    },
    toxicology: {
      hazards: hazards.map((h) => ({ label: h.label, evidence_ids: h.evidence_ids || [] })),
      consumer_risk: tox.consumer_risk || 'not_assessable',
      explanation: tox.explanation || 'Not covered by the current corpus.',
    },
    missing_information: unique([
      ...(reg.missing_information || []),
      ...(concentrationNeeded ? ['concentration'] : []),
    ]),
    evidence_ids: unique([...regEvidence, ...toxEvidence]),
  };
});

const ethics = e.ethics || {};
const ethicsEvidence = Array.isArray(ethics.evidence_ids) ? ethics.evidence_ids : [];
const covered = ingredients.filter((i) => i.covered).length;
const cited = unique([...ingredients.flatMap((i) => i.evidence_ids), ...ethicsEvidence]);
const count = (pred) => ingredients.filter(pred).length;

e.draft = {
  report_version: '0.2',
  request_id: e.request_id,
  assessment_date: e.input.assessment_date,
  corpus_version: pack.corpus_version,
  input_source: e.ocr ? 'label_photo' : 'barcode',
  product: {
    name: (e.product && e.product.name) || '',
    brand: (e.product && e.product.brand) || '',
    barcode: e.input.barcode || null,
  },
  overview: {
    total_ingredients: ingredients.length,
    prohibited: count((i) => i.regulatory.status === 'prohibited'),
    conditional: count((i) => i.regulatory.status === 'conditional'),
    conflicting: count((i) => i.regulatory.status === 'conflicting'),
    concentration_unknown: count((i) => i.missing_information.includes('concentration')),
    hazard_classified: count((i) => i.toxicology.hazards.length > 0),
    not_covered: ingredients.length - covered,
  },
  ingredients,
  cruelty_free: {
    status: ethics.status || 'not_verified',
    scope: ethics.scope || 'unknown',
    explanation: ethics.explanation || 'No cruelty-free evidence was assessed.',
    evidence_ids: ethicsEvidence,
    checked_at: ethics.checked_at || null,
  },
  evidence_coverage: {
    covered,
    total: ingredients.length,
    percent: Math.round((100 * covered) / Math.max(ingredients.length, 1)),
    definition:
      'Ingredients with at least one cited regulatory or toxicology source about that ingredient, divided by all listed ingredients. It measures how much evidence was found, not how safe the product is.',
  },
  sources: cited
    .filter((id) => sources.has(id))
    .map((id) => {
      const s = sources.get(id);
      return {
        evidence_id: id,
        kind: s.kind,
        source_url: s.source_url,
        source_version: s.source_version,
        retrieved_at: s.retrieved_at,
        excerpt: s.excerpt,
      };
    }),
  limitations: [
    'Ingredient concentrations are not on the label, so conditions that depend on concentration cannot be checked.',
    'A hazard classification describes the substance; consumer risk also depends on concentration and exposure.',
    'This report does not state that the product is safe, unsafe, legal or illegal, and is not medical advice.',
    'Only ingredients covered by the current corpus are assessed; others are marked as not covered.',
    'Brand claims and independent certifications are reported as separate kinds of evidence.',
  ],
};
return [{ json: e }];
