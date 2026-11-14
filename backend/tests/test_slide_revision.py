from app.services.slide_revision import compare_text


def test_word_and_number_changes_are_directional():
    result = compare_text('Revenue was 42% in the world', 'Revenue is 43% in the world')
    assert result['removed_words'] == 2 and result['added_words'] == 2
    assert result['selected_numbers'] == ['42%'] and result['compared_numbers'] == ['43%']
    assert result['selected'][1] == {'text': 'was 42%', 'changed': True}
    assert not result['text_equal'] and result['has_text']


def test_whitespace_and_empty_slides():
    assert compare_text('same\n  words', 'same words')['text_equal']
    assert not compare_text('', '')['has_text']
    assert compare_text('', 'new')['added_words'] == 1
    assert compare_text('removed', '')['removed_words'] == 1
    assert compare_text('x ' * 2001, 'x ' * 2001)['truncated']


def test_revision_api_uses_completed_cached_slides(client, database, pdf_bytes):
    from app.repositories import presentation_repository
    from app.services.presentation_service import process_presentation_job

    ids = []
    for text in ('Network budget 42', 'Network budget 43'):
        result = client.post(
            '/presentations/upload', files={'file': ('deck.pdf', pdf_bytes((text,)), 'application/pdf')}
        ).json()
        process_presentation_job(presentation_repository.claim_presentation_job())
        ids.append(
            client.get(f"/presentations/{result['file_id']}/comparison").json()['slides'][0]['slide']['id']
        )
    response = client.get(f'/presentations/slides/{ids[0]}/revisions/{ids[1]}')
    assert response.status_code == 200, response.text
    assert response.json()['selected_numbers'] == ['42'] and response.json()['compared_numbers'] == ['43']
    assert 'image_path' not in response.text
    assert client.get(f'/presentations/slides/{ids[0]}/revisions/9999999').status_code == 404
