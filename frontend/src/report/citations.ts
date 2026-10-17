import type { Report } from './schema';

export type CitationSummary = {
  cited: number; // distinct source_ids cited anywhere in the report
  inCorpus: number;
  notInCorpus: string[]; // cited, listed, but not in corpus/sources.csv
  unlisted: string[]; // cited but missing from report.sources (report is inconsistent)
};

/** Client-side check run before the report is shown, on top of the server's validation. */
export function summarizeCitations(report: Report): CitationSummary {
  const listed = new Map(report.sources.map((s) => [s.source_id, s]));
  const cited = new Set([...report.ingredients.flatMap((i) => i.sources), ...report.cruelty_free.sources]);

  const notInCorpus: string[] = [];
  const unlisted: string[] = [];
  for (const id of cited) {
    const source = listed.get(id);
    if (!source) unlisted.push(id);
    else if (!source.in_corpus) notInCorpus.push(id);
  }
  return { cited: cited.size, inCorpus: cited.size - notInCorpus.length - unlisted.length, notInCorpus, unlisted };
}
