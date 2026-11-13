"""Offline HTML export preserves image bytes, speech and timestamp preferences."""
import base64
from html.parser import HTMLParser
from pathlib import Path

import pytest

from app.processors.video_visuals import ExtractedFrame
from app.repositories import transcription_repository as speech, visual_repository as visuals
from app.processors.speech_recognizer import TranscriptSegment, TranscriptionResult
from app.services.visual_export import render_document


class Document(HTMLParser):
    def __init__(self, content):
        super().__init__()
        self.images, self.times, self.tags, self.text = [], 0, [], []
        self.feed(content)

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        if tag == 'img':
            self.images.append(dict(attrs)['src'])
        if tag == 'time':
            self.times += 1

    def handle_data(self, data):
        self.text.append(data)


def sample_document():
    return {
        'filename': 'Möte <script>alert("title")</script>.mp4',
        'sections': [
            {'visual': {'id': 1, 'start_ms': 2000, 'end_ms': 5000},
             'segments': [{'start_ms': 2200, 'text': 'Hello <img src=x onerror=alert(1)> & 世界.'}]},
            {'visual': None, 'segments': [{'start_ms': 6000, 'text': 'Uncovered speech.'}]},
            {'visual': {'id': 2, 'start_ms': 7000, 'end_ms': 8000}, 'segments': []},
        ],
    }


@pytest.mark.parametrize('timestamps', [False, True])
def test_offline_document_embeds_exact_images_and_escapes_text(tmp_path, timestamps):
    image = tmp_path/'image.jpg'
    # Cross several encoder chunk boundaries, including a final partial triple.
    data = bytes(range(256))*1001
    image.write_bytes(data)
    chunks = list(render_document(sample_document(), {1: image, 2: image}, timestamps))
    assert max(map(len, chunks)) <= 64*1024
    output = b''.join(chunks).decode('utf-8')
    document = Document(output)
    assert len(document.images) == 2
    assert all(base64.b64decode(src.split(',', 1)[1], validate=True) == data for src in document.images)
    assert document.times == (4 if timestamps else 0)
    assert ('00:00:02.000' in output) is timestamps
    assert 'script' not in document.tags and 'iframe' not in document.tags
    text = ''.join(document.text)
    assert 'Hello <img src=x onerror=alert(1)> & 世界.' in text
    assert text.count('Uncovered speech.') == 1
    assert 'No speech during this visual.' in text
    assert str(tmp_path) not in output and 'http://' not in output and 'https://' not in output


def test_empty_document():
    output = b''.join(render_document({'filename':'empty.mp4', 'sections':[]}, {}, False))
    assert b'No speech or distinct visual content was detected.' in output
    assert output.endswith(b'</html>')


@pytest.fixture
def recording(database, uploads):
    uploads.mkdir(parents=True)
    original = uploads/'original.mp4'
    original.write_bytes(b'original remains untouched')
    result = speech.create_video_job('Möte.mp4', original.stat().st_size, 'hash', original, 10000)
    speech.complete_transcription(speech.claim_next_job(), TranscriptionResult('en', [
        TranscriptSegment(2200, 3000, 'Hello world.'),
    ]))
    return result, original


def complete(recording, uploads):
    result, _ = recording
    target = uploads/'visuals'/str(result.file_id)/'frame.jpg'
    target.parent.mkdir(parents=True)
    target.write_bytes(b'\xff\xd8jpeg bytes')
    visuals.complete(visuals.claim(), [ExtractedFrame(2000, 5000, target, '0'*16, target.stat().st_size)])
    return target


def test_download_api_respects_timestamp_query_and_preserves_images(client, database, recording, uploads):
    result, original = recording
    image = complete(recording, uploads)
    endpoint = f'/videos/{result.file_id}/visual-transcript/download'
    plain = client.get(endpoint)
    assert plain.status_code == 200
    assert plain.headers['content-type'].startswith('text/html')
    assert 'attachment;' in plain.headers['content-disposition']
    assert "M%C3%B6te-visual-transcript.html" in plain.headers['content-disposition']
    assert plain.headers['x-content-type-options'] == 'nosniff'
    document = Document(plain.text)
    assert document.times == 0
    assert 'Hello world.' in plain.text
    assert base64.b64decode(document.images[0].split(',',1)[1]) == image.read_bytes()
    timed = client.get(endpoint+'?timestamps=true')
    assert timed.status_code == 200 and Document(timed.text).times == 2
    assert '00:00:02.000' in timed.text and '00:00:02.200' in timed.text
    assert client.get(endpoint+'?timestamps=false').text == plain.text
    assert client.get(endpoint+'?timestamps=invalid').status_code == 422
    assert original.read_bytes() == b'original remains untouched'


@pytest.mark.parametrize('status', ['queued','processing','failed'])
def test_download_waits_for_completed_visuals(client, database, recording, status):
    result, _ = recording
    if status in ('processing','failed'):
        job = visuals.claim()
        if status == 'failed': speech.fail_job(job['job_id'], 'Failed visuals.')
    response = client.get(f'/videos/{result.file_id}/visual-transcript/download')
    assert response.status_code == 409
    assert response.json()['detail']['status'] == status


def test_download_missing_or_unsafe_images_returns_error_before_streaming(client, database, recording, uploads):
    result, original = recording
    image = complete(recording, uploads)
    endpoint = f'/videos/{result.file_id}/visual-transcript/download'
    image.unlink()
    assert client.get(endpoint).status_code == 404
    # Even a valid existing upload cannot be served as an embedded visual.
    with database() as connection:
        connection.execute('UPDATE video_frames SET image_path=%s WHERE file_id=%s', (str(original), result.file_id))
    response = client.get(endpoint)
    assert response.status_code == 404
    assert str(original) not in response.text
    assert client.get('/videos/999999/visual-transcript/download').status_code == 404


def test_recording_without_visuals_downloads_speech_normally(client, database, recording):
    result, _ = recording
    visuals.complete(visuals.claim(), [])
    response = client.get(f'/videos/{result.file_id}/visual-transcript/download')
    assert response.status_code == 200
    assert 'Hello world.' in response.text and Document(response.text).images == []
