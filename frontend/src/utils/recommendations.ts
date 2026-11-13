/** Recommendations use existing evidence; visual scores never prove file equality. */
import type { DuplicateFile, DuplicateGroup } from "../types/duplicate";
import type {
  PresentationComparison,
  PresentationRecord,
  SlideMatch,
} from "../types/presentation";
import type { VisualTranscript } from "../types/transcription";

type FileReference = {
  id: number;
  filename: string;
  uploaded_at: string | null;
};

function orderCopies(a: FileReference, b: FileReference): number {
  const date = (value: string | null) => {
    const parsed = value ? Date.parse(value) : NaN;
    return Number.isFinite(parsed) ? parsed : Infinity;
  };
  return date(a.uploaded_at) - date(b.uploaded_at) || a.id - b.id;
}

export function duplicateRecommendation(
  group: DuplicateGroup,
): { keep: DuplicateFile; remove: DuplicateFile[] } | null {
  const ordered = [...group.files].sort(orderCopies);
  return ordered[0] ? { keep: ordered[0], remove: ordered.slice(1) } : null;
}

export interface PresentationRecommendation {
  candidate: FileReference;
  action: "review_removal" | "review_overlap" | "keep";
  basis: "exact" | "similar" | "partial";
  keep: FileReference;
  remove: FileReference | null;
  matchedSlides: number;
  exactSlides: number;
  totalSlides: number;
  coveragePercent: number;
  averageSimilarity: number;
}

function better(a: SlideMatch, b: SlideMatch | undefined): boolean {
  return (
    !b ||
    (a.classification === "exact" && b.classification !== "exact") ||
    (a.classification === b.classification &&
      a.similarity_percent > b.similarity_percent)
  );
}
const average = (matches: SlideMatch[]) =>
  matches.reduce((sum, item) => sum + item.similarity_percent, 0) /
  matches.length;

export function presentationRecommendations(
  comparison: PresentationComparison,
  records: PresentationRecord[],
): PresentationRecommendation[] {
  const selected: FileReference = {
    id: comparison.presentation.file_id,
    ...comparison.presentation,
  };
  const groups = new Map<
    number,
    {
      candidate: FileReference;
      sources: Map<number, SlideMatch>;
      targets: Map<number, SlideMatch>;
    }
  >();
  for (const result of comparison.slides) {
    for (const match of result.matches) {
      if (match.slide.file_id === selected.id) continue;
      let group = groups.get(match.slide.file_id);
      if (!group) {
        const record = records.find(
          (item) => item.file_id === match.slide.file_id,
        );
        group = {
          candidate: {
            id: match.slide.file_id,
            filename: match.slide.filename,
            uploaded_at: record?.uploaded_at ?? null,
          },
          sources: new Map(),
          targets: new Map(),
        };
        groups.set(match.slide.file_id, group);
      }
      if (better(match, group.sources.get(result.slide.id)))
        group.sources.set(result.slide.id, match);
      if (better(match, group.targets.get(match.slide.id)))
        group.targets.set(match.slide.id, match);
    }
  }
  const total = comparison.slides.length;
  if (!total || comparison.presentation.status !== "completed") return [];
  const results: PresentationRecommendation[] = [...groups.values()]
    .map((group) => {
      const sources = [...group.sources.values()],
        targets = [...group.targets.values()];
      const candidateTotal = records.find(
        (item) =>
          item.file_id === group.candidate.id && item.status === "completed",
      )?.slide_count;
      const sourceExact =
        sources.length === total &&
        sources.every((item) => item.classification === "exact");
      const targetExact =
        !!candidateTotal &&
        targets.length === candidateTotal &&
        targets.every((item) => item.classification === "exact");
      // Coverage is checked against ONE other deck, not a union of unrelated decks.
      const sourceSimilar = sources.length === total && average(sources) >= 95;
      const targetSimilar =
        !!candidateTotal &&
        targets.length === candidateTotal &&
        average(targets) >= 95;
      const exact = sourceExact || targetExact;
      const similar = !exact && (sourceSimilar || targetSimilar);
      let keep = selected,
        remove: FileReference | null = null;
      if (exact || similar) {
        const sourceCovered = exact ? sourceExact : sourceSimilar;
        const targetCovered = exact ? targetExact : targetSimilar;
        if (sourceCovered && targetCovered) {
          // Both decks cover one another: nominate the same retained copy in either view.
          const ordered = [selected, group.candidate].sort(orderCopies);
          keep = ordered[0]!;
          remove = ordered[1]!;
        } else if (sourceCovered) {
          keep = group.candidate;
          remove = selected;
        } else remove = group.candidate;
      }
      return {
        candidate: group.candidate,
        action: remove ? ("review_removal" as const) : ("keep" as const),
        basis: exact
          ? ("exact" as const)
          : similar
            ? ("similar" as const)
            : ("partial" as const),
        keep,
        remove,
        matchedSlides: sources.length,
        exactSlides: sources.filter((item) => item.classification === "exact")
          .length,
        totalSlides: total,
        coveragePercent: (sources.length / total) * 100,
        averageSimilarity:
          remove?.id === group.candidate.id
            ? average(targets)
            : average(sources),
      };
    })
    .sort((a, b) => {
      const rank = { exact: 0, similar: 1, partial: 2 };
      return (
        rank[a.basis] - rank[b.basis] ||
        b.coveragePercent - a.coveragePercent ||
        b.averageSimilarity - a.averageSimilarity ||
        a.candidate.id - b.candidate.id
      );
    });
  const retained = new Set<number>(),
    removed = new Set<number>();
  return results.map((item) => {
    if (item.remove) {
      // Do not recommend removing the copy retained by a stronger match, or
      // retaining a copy already proposed for removal in this same review.
      if (
        retained.has(item.remove.id) ||
        removed.has(item.keep.id) ||
        removed.has(item.remove.id)
      ) {
        item.action = "review_overlap";
        item.remove = null;
      } else {
        retained.add(item.keep.id);
        removed.add(item.remove.id);
      }
    }
    return item;
  });
}

export function visualOverview(transcript: VisualTranscript) {
  const frames = transcript.sections.flatMap((section) =>
    section.visual ? [section.visual] : [],
  );
  const uniqueImages = new Set(
    frames.map((frame) => frame.image_reference_id ?? frame.id),
  ).size;
  return {
    visualSections: frames.length,
    uniqueImages,
    reusedImages: frames.length - uniqueImages,
    speechSegments: transcript.sections.reduce(
      (sum, section) => sum + section.segments.length,
      0,
    ),
  };
}
