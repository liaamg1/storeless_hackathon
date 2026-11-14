"""Bounded text comparison between cached slides; never infer chronological versions."""

from difflib import SequenceMatcher
import re

from app.repositories import presentation_repository
from app.services.presentation_service import PresentationNotFoundError

MAX_WORDS = 2000


def compare_text(selected: str, compared: str) -> dict:
    left, right = selected.split(), compared.split()
    truncated = len(left) > MAX_WORDS or len(right) > MAX_WORDS
    left, right = left[:MAX_WORDS], right[:MAX_WORDS]
    selected_parts, compared_parts = [], []
    removed, added = [], []
    for operation, i, j, x, y in SequenceMatcher(None, left, right, autojunk=True).get_opcodes():
        if i != j:
            selected_parts.append({'text': ' '.join(left[i:j]), 'changed': operation != 'equal'})
        if x != y:
            compared_parts.append({'text': ' '.join(right[x:y]), 'changed': operation != 'equal'})
        if operation != 'equal':
            removed.extend(left[i:j])
            added.extend(right[x:y])

    def numbers(words):
        return re.findall(r'(?<!\w)[+-]?\d+(?:[.,]\d+)*(?:%|\b)', ' '.join(words))

    return {
        'selected': selected_parts,
        'compared': compared_parts,
        'removed_words': len(removed),
        'added_words': len(added),
        'selected_numbers': numbers(removed),
        'compared_numbers': numbers(added),
        'truncated': truncated,
        'has_text': bool(left or right),
        'text_equal': left == right and not truncated,
    }


def revision(slide_id: int, other_id: int) -> dict:
    slides = presentation_repository.get_analyzed_slides()
    first = next((slide for slide in slides if slide['id'] == slide_id), None)
    other = next((slide for slide in slides if slide['id'] == other_id), None)
    if first is None or other is None:
        raise PresentationNotFoundError('Completed slide results are not available.')
    return {
        'selected_slide_id': slide_id,
        'compared_slide_id': other_id,
        **compare_text(first['text'], other['text']),
    }
