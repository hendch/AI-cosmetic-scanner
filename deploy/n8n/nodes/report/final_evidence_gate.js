// n8n node "Live - Final evidence gate" (Code). Owner: Omar.
// Rule-based checks on the agents' outputs plus the AI validator's verdict. Any failed
// error-level check holds the report back (status needs_review); warnings are only shown.

const e = JSON.parse(JSON.stringify($input.first().json));
const pack = e.evidence_pack;
const sources = new Map(pack.sources.map((s) => [s.evidence_id, s]));
const ingredientIds = e.ingredients.map((i) => i.ingredient_id);
const regFindings = (e.regulatory && e.regulatory.findings) || [];
const toxFindings = (e.toxicology && e.toxicology.findings) || [];
const ethics = e.ethics || {};

const REG_STATUSES = ['conditional', 'prohibited', 'no_rule_found_in_snapshot', 'not_assessed', 'conflicting'];
const CONDITION_RESULTS = ['unknown', 'satisfied', 'not_satisfied', 'not_assessed'];
const ETHICS_STATUSES = ['verified', 'claimed', 'not_verified', 'conflicting'];
// Wording the agents must not use: the project reports evidence, never a safety verdict.
const VERDICT_WORDS = /\b(safe|unsafe|dangerous|harmful|toxic|non-toxic|causes? cancer|should be avoided|avoid|illegal)\b/gi;

const checks = [];
function check(name, severity, description, issues) {
  checks.push({ name, severity, description, passed: issues.length === 0, issues: [...new Set(issues)] });
}

// 1. Each ingredient-level agent covers every ingredient exactly once.
const coverage = [];
for (const [agent, findings] of [['regulatory', regFindings], ['toxicology', toxFindings]]) {
  const seen = findings.map((f) => f.ingredient_id);
  for (const id of ingredientIds) {
    const n = seen.filter((x) => x === id).length;
    if (n === 0) coverage.push(`${agent}: no finding for ${id}`);
    if (n > 1) coverage.push(`${agent}: ${id} covered more than once`);
  }
  for (const id of seen) if (!ingredientIds.includes(id)) coverage.push(`${agent}: finding for ${id}, which is not in the ingredient list`);
}
check('agent_coverage', 'error', 'Each agent covers every ingredient exactly once.', coverage);

// 2-3. Citations exist, are about the right ingredient and are the right kind of source.
const known = [];
const subject = [];
function cite(where, ids, ingredientId, kind) {
  if (!Array.isArray(ids)) {
    known.push(`${where}: evidence_ids is missing`);
    return;
  }
  for (const id of ids) {
    const s = sources.get(id);
    if (!s) known.push(`${where} cites ${id}, which is not in the evidence pack`);
    else {
      if (ingredientId && !s.ingredient_ids.includes(ingredientId)) subject.push(`${where} cites ${id}, which is about ${s.ingredient_ids.join(', ')}`);
      if (kind && s.kind !== kind) subject.push(`${where} cites ${id}, a ${s.kind} source, where a ${kind} source is needed`);
    }
  }
}
for (const f of regFindings) cite(`regulatory/${f.ingredient_id}`, f.evidence_ids, f.ingredient_id, 'regulation');
for (const f of toxFindings) for (const h of f.hazards || []) cite(`toxicology/${f.ingredient_id}`, h.evidence_ids, f.ingredient_id, 'toxicology');
cite('ethics', ethics.evidence_ids, null, null);
check('citations_known', 'error', 'Every cited evidence ID exists in the retrieved evidence.', known);
check('citation_subject', 'error', 'Each citation is about the ingredient it supports and is the right kind of source.', subject);

// 4. Regulatory statuses match the exact rules that were looked up.
const rulesIssues = [];
for (const f of regFindings) {
  const where = `regulatory/${f.ingredient_id}`;
  const rules = pack.rules.filter((r) => r.ingredient_id === f.ingredient_id);
  if (!REG_STATUSES.includes(f.regulatory_status)) rulesIssues.push(`${where}: unknown status ${f.regulatory_status}`);
  if (!CONDITION_RESULTS.includes(f.condition_result)) rulesIssues.push(`${where}: unknown condition result ${f.condition_result}`);
  if (['conditional', 'prohibited', 'conflicting'].includes(f.regulatory_status) &&
      !rules.some((r) => r.rule_state === f.regulatory_status && r.evidence_ids.some((id) => (f.evidence_ids || []).includes(id))))
    rulesIssues.push(`${where}: ${f.regulatory_status} without a matching exact rule`);
  if (f.condition_result === 'satisfied' && !rules.some((r) => r.condition_result === 'satisfied'))
    rulesIssues.push(`${where}: conditions marked satisfied, but no exact rule says so`);
  if (f.regulatory_status === 'no_rule_found_in_snapshot' &&
      !pack.lookup_log.some((l) => l.ingredient_id === f.ingredient_id && l.exact_lookup_complete))
    rulesIssues.push(`${where}: "no rule found" without a complete exact lookup`);
}
check('regulatory_rules', 'error', 'Regulatory statuses match the exact rules that were looked up.', rulesIssues);

// 5. Concentration-dependent conditions stay unknown when the concentration is unknown.
const concentration = [];
for (const f of regFindings) {
  const ing = e.ingredients.find((i) => i.ingredient_id === f.ingredient_id);
  const needsIt = pack.rules.some((r) => r.ingredient_id === f.ingredient_id && r.concentration_required);
  if (needsIt && ing && ing.concentration_percent == null && f.condition_result !== 'unknown')
    concentration.push(`regulatory/${f.ingredient_id}: concentration is unknown, so the condition result must be unknown`);
}
check('missing_concentration', 'error', 'Conditions that depend on concentration stay unknown when it is missing.', concentration);

// 6. Every claim is backed by evidence.
const backing = [];
for (const f of regFindings)
  if (!['not_assessed', 'no_rule_found_in_snapshot'].includes(f.regulatory_status) && !(f.evidence_ids || []).length)
    backing.push(`regulatory/${f.ingredient_id}: ${f.regulatory_status} without evidence`);
for (const f of toxFindings)
  for (const h of f.hazards || []) if (!(h.evidence_ids || []).length) backing.push(`toxicology/${f.ingredient_id}: hazard "${h.label}" without evidence`);
if (!ETHICS_STATUSES.includes(ethics.status)) backing.push(`ethics: unknown status ${ethics.status}`);
if (['verified', 'claimed', 'conflicting'].includes(ethics.status) && !(ethics.evidence_ids || []).length)
  backing.push(`ethics: ${ethics.status} without evidence`);
if (ethics.status === 'verified' && !(ethics.evidence_ids || []).some((id) => (sources.get(id) || {}).kind === 'certification'))
  backing.push('ethics: verified needs an independent certification source');
check('claims_have_evidence', 'error', 'Statuses, hazards and cruelty-free claims cite evidence.', backing);

// 7. Hazard is never turned into a consumer-risk conclusion.
check('no_risk_conclusion', 'error', 'Consumer risk is not assessed without concentration and exposure.',
  toxFindings.filter((f) => f.consumer_risk !== 'not_assessable').map((f) => `toxicology/${f.ingredient_id}: consumer_risk must be not_assessable`));

// 8. No safety verdicts in the explanations.
const wording = [];
const texts = [
  ...regFindings.map((f) => [`regulatory/${f.ingredient_id}`, f.explanation]),
  ...toxFindings.map((f) => [`toxicology/${f.ingredient_id}`, f.explanation]),
  ['ethics', ethics.explanation],
];
for (const [where, text] of texts) {
  const words = [...new Set((String(text || '').match(VERDICT_WORDS) || []).map((w) => w.toLowerCase()))];
  if (words.length) wording.push(`${where}: uses verdict wording (${words.join(', ')})`);
}
check('no_safety_verdicts', 'error', 'No "safe", "toxic", "avoid" or "illegal" verdicts in explanations.', wording);

// 9. Only real, marked evidence in live mode.
check('evidence_provenance', 'error', 'No synthetic or unmarked evidence.',
  pack.is_synthetic || pack.sources.some((s) => s.is_synthetic !== false) ? ['Synthetic or unmarked evidence in the evidence pack'] : []);

// 10. The AI validator found every claim supported.
const v = e.validator || { valid: false, claims: [], issues: ['The validator gave no answer'], unsupported_evidence_ids: [] };
const aiIssues = [
  ...v.issues,
  ...v.claims.filter((c) => c.verdict !== 'supported').map((c) => `${c.agent || 'claim'}${c.ingredient_id ? '/' + c.ingredient_id : ''}: ${c.verdict}. ${c.reason}`.trim()),
  ...v.unsupported_evidence_ids.map((id) => `Evidence ${id} does not support what it is cited for`),
];
if (!v.valid && !aiIssues.length) aiIssues.push('The validator rejected the draft without giving a reason');
check('ai_validator', 'error', 'The validator agent found every claim supported by its cited excerpt.', aiIssues);

const failed = checks.filter((c) => !c.passed && c.severity === 'error');
e.validation = {
  passed: failed.length === 0,
  checks,
  issues: failed.flatMap((c) => c.issues),
  semantic_check: 'AI validator (fallible); rule checks above are deterministic.',
};
e.status = failed.length ? 'needs_review' : 'completed';
if (failed.length) {
  delete e.report;
  e.error = e.error || { code: 'VALIDATION', message: 'Some findings could not be backed by the evidence, so the report was held back.' };
} else {
  e.report = { ...e.draft, validation: e.validation, validator_claims: v.claims };
}
return [{ json: e }];
