import type { Report } from './schema';

export type CitationSummary = {
  cited: number; // distinct evidence items cited anywhere in the report
  withText: number; // ... that come with the source text the claim rests on
  notInCorpus: string[]; // cited, but the source is not registered in corpus/sources.csv
  unlisted: string[]; // cited but missing from report.sources (the report is inconsistent)
};

/** Client-side check run before the report is shown, on top of the server's rule checks. */
export function summarizeCitations(report: Report): CitationSummary {
  const listed = new Map(report.sources.map((s) => [s.evidence_id, s]));
  const cited = new Set([
    ...report.ingredients.flatMap((i) => [...i.regulatory.evidence_ids, ...i.toxicology.evidence_ids]),
    ...report.cruelty_free.evidence_ids,
  ]);
  const notInCorpus: string[] = [];
  const unlisted: string[] = [];
  let withText = 0;
  for (const id of cited) {
    const s = listed.get(id);
    if (!s) unlisted.push(id);
    else {
      if (!s.in_corpus) notInCorpus.push(id);
      if (s.excerpt) withText += 1;
    }
  }
  return { cited: cited.size, withText, notInCorpus, unlisted };
}
