// n8n node "Live - Public result" (Code). Owner: Omar.
// What the app receives. The report is included only when every error-level check passed.

const e = $input.first().json;
return [
  {
    json: {
      schema_version: '0.1',
      request_id: e.request_id,
      mode: e.mode,
      origin: e.origin || 'manual',
      status: e.status,
      report: e.status === 'completed' ? e.report : null,
      next_action: e.next_action || null,
      error: e.error || null,
      validation: e.validation || null,
    },
  },
];
