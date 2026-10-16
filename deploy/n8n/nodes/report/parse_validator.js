// n8n node "Live - Parse validator" (Code). Owner: Omar.
// Reads the Validator Agent's answer and stores it as e.validator in one shape for both prompt
// versions: { valid, claims[], issues[], unsupported_evidence_ids[] }. v1 returns no claims.

const before = $('Live - Build draft').first().json;
const raw = $input.first().json;
const e = JSON.parse(JSON.stringify(before));

function parse(output) {
  if (output && typeof output === 'object') return output;
  if (typeof output !== 'string') return null;
  // Small models often wrap JSON in ```json fences or add a sentence around it.
  const text = output.replace(/^\s*```(?:json)?\s*/i, '').replace(/\s*```\s*$/, '');
  try {
    return JSON.parse(text);
  } catch (err) {
    const start = text.indexOf('{');
    const end = text.lastIndexOf('}');
    if (start < 0 || end <= start) return null;
    try {
      return JSON.parse(text.slice(start, end + 1));
    } catch (err2) {
      return null;
    }
  }
}

const VERDICTS = ['supported', 'overstated', 'unsupported'];
const obj = parse(raw.output);
const wellFormed =
  obj &&
  typeof obj === 'object' &&
  !Array.isArray(obj) &&
  typeof obj.valid === 'boolean' &&
  Array.isArray(obj.issues) &&
  (obj.claims === undefined ||
    (Array.isArray(obj.claims) && obj.claims.every((c) => c && VERDICTS.includes(c.verdict) && typeof c.claim === 'string')));

if (!wellFormed) {
  e.status = 'needs_review';
  e.error = { code: 'AGENT_JSON', message: 'The validator did not return the expected JSON object.' };
} else {
  e.validator = {
    valid: obj.valid,
    claims: (obj.claims || []).map((c) => ({
      agent: c.agent || null,
      ingredient_id: c.ingredient_id || null,
      claim: c.claim,
      evidence_ids: Array.isArray(c.evidence_ids) ? c.evidence_ids : [],
      verdict: c.verdict,
      reason: typeof c.reason === 'string' ? c.reason : '',
    })),
    issues: obj.issues.filter((i) => typeof i === 'string'),
    unsupported_evidence_ids: Array.isArray(obj.unsupported_evidence_ids) ? obj.unsupported_evidence_ids : [],
  };
  e.agent_trace = e.agent_trace || {};
  e.agent_trace.validator = raw.intermediateSteps || [];
}
return [{ json: e }];
