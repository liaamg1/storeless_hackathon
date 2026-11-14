import assert from "node:assert/strict";
import test from "node:test";
import {
  duplicateRecommendation,
  presentationRecommendations,
  visualOverview,
} from "../src/utils/recommendations.ts";
import type {
  PresentationComparison,
  PresentationRecord,
  SlideComparison,
} from "../src/types/presentation.ts";
import type { VisualTranscript } from "../src/types/transcription.ts";

const record = (id: number, slides = 2): PresentationRecord => ({
  file_id: id,
  filename: `deck-${id}.pdf`,
  size_bytes: 1000,
  uploaded_at: null,
  job_id: id,
  status: "completed",
  current_step: "completed",
  error_message: null,
  slide_count: slides,
});
function result(
  source: number,
  target: number,
  page: number,
  score = 100,
  classification: "exact" | "similar" = "exact",
): SlideComparison {
  const preview = (file: number) => ({
    id: file * 100 + page,
    file_id: file,
    filename: `deck-${file}.pdf`,
    slide_number: page,
    text: "Text",
    processed_at: "2026-11-13T10:00:00Z",
  });
  return {
    slide: preview(source),
    classification,
    matches: [
      {
        slide: preview(target),
        classification,
        similarity_percent: score,
        hash_distance: 0,
      },
    ],
  };
}
function comparison(
  source: number,
  slides: SlideComparison[],
): PresentationComparison {
  return {
    presentation: record(source, slides.length),
    similarity_threshold: 90,
    summary: {
      presentations_analyzed: 2,
      total_slides_analyzed: 4,
      selected_slide_count: slides.length,
      exact_slides: 0,
      similar_slides: 0,
      unique_slides: 0,
      matching_presentations: 1,
    },
    slides,
  };
}

test("duplicate plan keeps the earliest dated copy and identifies copies by ID without mutating input", () => {
  const files = [
    { id: 3, filename: "same.pdf", size_bytes: 100, uploaded_at: null },
    { id: 2, filename: "same.pdf", size_bytes: 100, uploaded_at: "2026-11-13" },
    {
      id: 1,
      filename: "reference.pdf",
      size_bytes: 100,
      uploaded_at: "2026-11-12",
    },
  ];
  const plan = duplicateRecommendation({
    sha256: "hash",
    file_size_bytes: 100,
    file_count: 3,
    potential_savings_bytes: 200,
    files,
  });
  assert.equal(plan?.keep.id, 1);
  assert.deepEqual(
    plan?.remove.map((file) => file.id),
    [2, 3],
  );
  assert.deepEqual(
    files.map((file) => file.id),
    [3, 2, 1],
  );
});
test("unknown, invalid and equal dates use file ID deterministically", () => {
  const files = [
    { id: 9, filename: "a", size_bytes: 1, uploaded_at: "invalid" },
    { id: 4, filename: "b", size_bytes: 1, uploaded_at: null },
  ];
  assert.equal(
    duplicateRecommendation({
      sha256: "hash",
      file_size_bytes: 1,
      file_count: 2,
      potential_savings_bytes: 1,
      files,
    })?.keep.id,
    4,
  );
});
test("equivalent decks nominate the same keep/remove pair from either direction", () => {
  const records = [record(1), record(2)];
  for (const source of [1, 2]) {
    const target = source === 1 ? 2 : 1;
    const [plan] = presentationRecommendations(
      comparison(source, [
        result(source, target, 1),
        result(source, target, 2),
      ]),
      records,
    );
    assert.equal(plan?.basis, "exact");
    assert.equal(plan?.keep.id, 1);
    assert.equal(plan?.remove?.id, 2);
    assert.equal(plan?.coveragePercent, 100);
  }
});
test("partial matches across different decks cannot be combined into a deletion recommendation", () => {
  const plans = presentationRecommendations(
    comparison(1, [result(1, 2, 1), result(1, 3, 2)]),
    [record(1), record(2, 3), record(3, 3)],
  );
  assert.equal(plans.length, 2);
  assert.ok(
    plans.every(
      (plan) =>
        plan.basis === "partial" &&
        plan.remove === null &&
        plan.coveragePercent === 50,
    ),
  );
});
test("multiple matches for one slide count that source only once", () => {
  const slide = result(1, 2, 1);
  slide.matches.push({
    ...slide.matches[0]!,
    slide: { ...slide.matches[0]!.slide, id: 299, slide_number: 9 },
  });
  const unique: SlideComparison = {
    slide: { ...slide.slide, id: 102, slide_number: 2 },
    classification: "unique",
    matches: [],
  };
  const [plan] = presentationRecommendations(comparison(1, [slide, unique]), [
    record(1),
    record(2, 10),
  ]);
  assert.equal(plan?.matchedSlides, 1);
  assert.equal(plan?.exactSlides, 1);
  assert.equal(plan?.coveragePercent, 50);
  assert.equal(plan?.remove, null);
});
test("95 percent full coverage suggests review, never exact equality", () => {
  const [plan] = presentationRecommendations(
    comparison(2, [
      result(2, 1, 1, 95, "similar"),
      result(2, 1, 2, 95, "similar"),
    ]),
    [record(1), record(2)],
  );
  assert.equal(plan?.basis, "similar");
  assert.equal(plan?.action, "review_removal");
  assert.equal(plan?.averageSimilarity, 95);
});
test("a 100 percent perceptual collision remains a similar review candidate", () => {
  const [plan] = presentationRecommendations(
    comparison(2, [
      result(2, 1, 1, 100, "similar"),
      result(2, 1, 2, 100, "similar"),
    ]),
    [record(1), record(2)],
  );
  assert.equal(plan?.basis, "similar");
  assert.equal(plan?.exactSlides, 0);
});
test("high score on part of a deck and full coverage below 95 percent do not justify removal", () => {
  const partial = comparison(1, [
    result(1, 2, 1, 98, "similar"),
    { ...result(1, 2, 2), classification: "unique", matches: [] },
  ]);
  assert.equal(
    presentationRecommendations(partial, [record(1), record(2, 5)])[0]?.remove,
    null,
  );
  const lower = comparison(1, [
    result(1, 2, 1, 94.99, "similar"),
    result(1, 2, 2, 94.99, "similar"),
  ]);
  assert.equal(
    presentationRecommendations(lower, [record(1), record(2)])[0]?.remove,
    null,
  );
});
test("a subset deck is the removal candidate, retaining the larger deck's unmatched slides", () => {
  const data = comparison(1, [
    result(1, 2, 1),
    { ...result(1, 2, 2), classification: "unique", matches: [] },
  ]);
  const [plan] = presentationRecommendations(data, [record(1), record(2, 1)]);
  assert.equal(plan?.basis, "exact");
  assert.equal(plan?.keep.id, 1);
  assert.equal(plan?.remove?.id, 2);
});
test("empty, unfinished and unmatched presentations have no removal recommendations", () => {
  assert.deepEqual(presentationRecommendations(comparison(1, []), []), []);
  const data = comparison(1, [result(1, 2, 1)]);
  data.presentation.status = "processing";
  assert.deepEqual(presentationRecommendations(data, []), []);
});
test("visual reuse uses the actual image reference rather than perceptual hash equality", () => {
  const visual = (id: number, reference: number) => ({
    id,
    file_id: 1,
    start_ms: id * 1000,
    end_ms: (id + 1) * 1000,
    image_hash: "same hash",
    size_bytes: 20,
    image_reference_id: reference,
  });
  const data: VisualTranscript = {
    file_id: 1,
    filename: "meeting.mp4",
    status: "completed",
    current_step: "completed",
    error_message: null,
    speech_status: "completed",
    sections: [
      {
        visual: visual(1, 1),
        segments: [{ id: 1, start_ms: 0, end_ms: 1000, text: "One" }],
      },
      { visual: visual(2, 1), segments: [] },
      { visual: visual(3, 3), segments: [] },
      {
        visual: null,
        segments: [{ id: 2, start_ms: 9000, end_ms: 10000, text: "Uncovered" }],
      },
    ],
  };
  assert.deepEqual(visualOverview(data), {
    visualSections: 3,
    uniqueImages: 2,
    reusedImages: 1,
    speechSegments: 2,
  });
});

test("recommendations do not remove a proposed retained copy or retain a proposed removal", () => {
  const first = result(2, 1, 1),
    second = result(2, 1, 2);
  first.matches.push(...result(2, 3, 1, 95, "similar").matches);
  second.matches.push(...result(2, 3, 2, 95, "similar").matches);
  const plans = presentationRecommendations(comparison(2, [first, second]), [
    record(1),
    record(2),
    record(3),
  ]);
  assert.equal(plans[0]?.keep.id, 1);
  assert.equal(plans[0]?.remove?.id, 2);
  assert.equal(plans[1]?.action, "review_overlap");
  assert.equal(plans[1]?.remove, null);
});

test("duplicate keeper prefers completed processing over upload age", () => {
  const files = [
    {
      id: 1,
      filename: "older.mp4",
      size_bytes: 50,
      uploaded_at: "2026-11-01",
      completed_operations: [],
    },
    {
      id: 2,
      filename: "ready.mp4",
      size_bytes: 50,
      uploaded_at: "2026-11-02",
      completed_operations: ["video_transcription", "video_visuals"],
    },
  ];
  const result = duplicateRecommendation({
    sha256: "hash",
    file_size_bytes: 50,
    file_count: 2,
    potential_savings_bytes: 50,
    files,
  });
  assert.equal(result?.keep.id, 2);
  assert.deepEqual(
    result?.remove.map((file) => file.id),
    [1],
  );
});

test("cached slide matches cannot recommend a removed presentation", () => {
  const cached = comparison(1, [result(1, 2, 1), result(1, 2, 2)]);
  assert.equal(
    presentationRecommendations(cached, [record(1), record(2)]).length,
    1,
  );
  assert.deepEqual(presentationRecommendations(cached, [record(1)]), []);
  assert.deepEqual(presentationRecommendations(cached, [record(2)]), []);
});
