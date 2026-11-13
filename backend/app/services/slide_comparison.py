"""Compare cached slide hashes across presentations, excluding the selected file."""
from app.processors.slide_hash import perceptual_distance
from app.schemas.presentation import (
    PresentationComparison, PresentationRecord, SlideComparison, SlideMatch, SlidePreview, SlideSummary,
)


def compare_slides(presentation: PresentationRecord, cached: list[dict], threshold: float) -> PresentationComparison:
    selected = [row for row in cached if row['file_id'] == presentation.file_id]
    candidates = [row for row in cached if row['file_id'] != presentation.file_id]
    results = []
    matched_files = set()
    for slide in selected:
        matches = []
        for other in candidates:
            distance = perceptual_distance(slide['perceptual_hash'], other['perceptual_hash'])
            # SHA-256 includes full normalized rendered pixels AND extracted text.
            # pHash equality alone may hide changed numbers or diagram details.
            exact = slide['content_hash'] == other['content_hash']
            score = 100.0 if exact else (1 - distance / 64) * 100
            if exact or score >= threshold:
                matches.append(SlideMatch(slide=SlidePreview(**other), classification='exact' if exact else 'similar',
                                          similarity_percent=round(score, 2), hash_distance=distance))
                matched_files.add(other['file_id'])
        matches.sort(key=lambda match: (match.classification != 'exact', -match.similarity_percent, match.slide.file_id, match.slide.slide_number))
        classification = 'exact' if any(match.classification == 'exact' for match in matches) else 'similar' if matches else 'unique'
        results.append(SlideComparison(slide=SlidePreview(**slide), classification=classification, matches=matches))
    return PresentationComparison(
        presentation=presentation, similarity_threshold=threshold, slides=results,
        summary=SlideSummary(
            presentations_analyzed=len({row['file_id'] for row in cached}), total_slides_analyzed=len(cached),
            selected_slide_count=len(results), exact_slides=sum(r.classification == 'exact' for r in results),
            similar_slides=sum(r.classification == 'similar' for r in results),
            unique_slides=sum(r.classification == 'unique' for r in results), matching_presentations=len(matched_files),
        ),
    )
