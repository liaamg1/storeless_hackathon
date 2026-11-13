"""Bounded frame decoding, timestamp matching, and isolated persistence tests."""
import hashlib
import io
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pymupdf
import pytest

from app.processors import video_visuals as processor
from app.processors.speech_recognizer import TranscriptSegment, TranscriptionResult
from app.repositories import transcription_repository as speech, visual_repository as repository
from app.services import visual_service as service


def slide(seed):
    # Distinct high-detail diagrams, with no random motion between samples.
    pixels = np.full((processor.HEIGHT, processor.WIDTH, 3), 245, dtype=np.uint8)
    rng = np.random.default_rng(seed)
    for _ in range(15):
        x = rng.integers(0, processor.WIDTH-300)
        y = rng.integers(0, processor.HEIGHT-120)
        pixels[y:y+120, x:x+300] = rng.integers(0, 200, 3)
    return pixels.tobytes()


class Decoder:
    def __init__(self, frames, returncode=0):
        self.stdout = io.BytesIO(b''.join(frames))
        self.returncode = returncode

    def poll(self):
        return self.returncode

    def wait(self):
        return self.returncode

    def kill(self):
        self.returncode = -9


def decode(monkeypatch, tmp_path, frames, **kwargs):
    monkeypatch.setattr(processor.subprocess, 'Popen', lambda *args, **kw: Decoder(frames))
    return processor.extract_visuals(tmp_path/'source.mp4', tmp_path/'images', max(len(frames), 1)*1000, interval=1, **kwargs)


def test_static_and_near_duplicate_frames_only_save_one(monkeypatch, tmp_path):
    frame = slide(42)
    nearby = bytearray(frame)
    nearby[10000:10003] = b'\x00\x00\x00'  # Mouse-sized change.
    frames = decode(monkeypatch, tmp_path, [frame, bytes(nearby), frame])
    assert len(frames) == 1
    assert (frames[0].start_ms, frames[0].end_ms) == (0, 3000)
    assert frames[0].size_bytes == frames[0].image_path.stat().st_size < processor.FRAME_BYTES
    assert frames[0].image_path.read_bytes().startswith(b'\xff\xd8')


def test_multiple_slides_and_revisited_visual_reuse_image(monkeypatch, tmp_path):
    frames = decode(monkeypatch, tmp_path, [slide(1), slide(2), slide(1)])
    assert [(f.start_ms, f.end_ms) for f in frames] == [(0, 1000), (1000, 2000), (2000, 3000)]
    assert frames[0].image_path == frames[2].image_path
    assert len(list((tmp_path/'images').glob('*.jpg'))) == 2


def test_blank_recording_and_blank_interval(monkeypatch, tmp_path):
    blank = bytes(processor.FRAME_BYTES)
    assert decode(monkeypatch, tmp_path, [blank, blank]) == []
    frames = decode(monkeypatch, tmp_path, [slide(1), blank, slide(1)])
    assert [(f.start_ms, f.end_ms) for f in frames] == [(0, 1000), (2000, 3000)]


def test_cap_limits_persisted_metadata_and_images(monkeypatch, tmp_path):
    frames = decode(monkeypatch, tmp_path, [slide(1), slide(2), slide(3)], max_frames=1)
    assert len(frames) == 1
    assert frames[0].end_ms == 1000
    assert len(list((tmp_path/'images').glob('*'))) == 1


@pytest.mark.parametrize('frames', [[], [b'incomplete']])
def test_empty_or_corrupted_frames_fail(monkeypatch, tmp_path, frames):
    with pytest.raises(processor.VisualExtractionError):
        decode(monkeypatch, tmp_path, frames)


def test_short_pipe_reads_assemble_one_frame():
    class ShortPipe:
        def __init__(self): self.remaining = processor.FRAME_BYTES
        def read(self, count):
            size = min(count, self.remaining, 113)
            self.remaining -= size
            return b'x'*size
    pipe = ShortPipe()
    assert len(processor.read_frame(pipe)) == processor.FRAME_BYTES
    assert processor.read_frame(pipe) == b''


@pytest.mark.parametrize('kwargs', [{'interval':0}, {'distance':65}, {'max_frames':0}, {'timeout':0}])
def test_invalid_settings_fail(tmp_path, kwargs):
    with pytest.raises(processor.VisualExtractionError):
        processor.extract_visuals(tmp_path/'in.mp4', tmp_path/'out', 1000, **kwargs)


def test_alignment_crossings_ties_gaps_and_silence():
    frames = [dict(id=1,start_ms=1000,end_ms=3000,image_path='/private/a'),
              dict(id=2,start_ms=3000,end_ms=6000,image_path='/private/b'),
              dict(id=3,start_ms=7000,end_ms=8000,image_path='/private/c')]
    segments = [dict(id=1,start_ms=0,end_ms=500,text='Uncovered'),
                dict(id=2,start_ms=1500,end_ms=2000,text='Aligned'),
                dict(id=3,start_ms=2500,end_ms=4500,text='Greatest overlap is second'),
                dict(id=4,start_ms=2500,end_ms=3500,text='Tie goes first'),
                dict(id=5,start_ms=6000,end_ms=6500,text='In gap')]
    sections = service.synchronize(list(reversed(frames)), list(reversed(segments)))
    assert [s['visual']['id'] if s['visual'] else None for s in sections] == [None,1,2,None,3]
    assert [s['id'] for s in sections[1]['segments']] == [2,4]
    assert [s['id'] for s in sections[2]['segments']] == [3]
    assert sorted(s['id'] for section in sections for s in section['segments']) == [1,2,3,4,5]
    assert sections[-1]['segments'] == []
    assert 'image_path' not in str(sections)
    assert len(service.synchronize(frames, [])) == 3


def test_real_ffmpeg_multiple_static_screens_and_corrupt_media(tmp_path):
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg: pytest.skip('FFmpeg is required for decoder integration')
    for index, seed in enumerate([1,2]):
        pixmap = pymupdf.Pixmap(pymupdf.csRGB, processor.WIDTH, processor.HEIGHT, slide(seed), False)
        pixmap.save(str(tmp_path/f'slide{index}.png'))
    source = tmp_path/'slides.mp4'
    subprocess.run([ffmpeg,'-v','error','-threads','1','-framerate','1/2','-i',str(tmp_path/'slide%d.png'),
                    '-c:v','libx264','-threads','1','-pix_fmt','yuv420p',str(source)], check=True)
    frames = processor.extract_visuals(source,tmp_path/'images',4000,interval=1,ffmpeg=ffmpeg)
    assert len(frames) == 2
    assert [(f.start_ms, f.end_ms) for f in frames] == [(0,2000),(2000,4000)]
    # Include the first frame even when the whole video is shorter than a sample interval.
    short = processor.extract_visuals(source,tmp_path/'short',4000,interval=5,ffmpeg=ffmpeg)
    assert len(short) == 1 and (short[0].start_ms,short[0].end_ms) == (0,4000)
    assert processor.perceptual_distance(short[0].image_hash,processor.fingerprint(slide(1))[0]) <= 6
    source.write_bytes(b'invalid mp4')
    with pytest.raises(processor.VisualExtractionError):
        processor.extract_visuals(source,tmp_path/'corrupt',1000,ffmpeg=ffmpeg)


@pytest.fixture
def recording(database, uploads):
    uploads.mkdir(parents=True, exist_ok=True)
    path = uploads/'original.mp4'
    path.write_bytes(b'original recording preserved')
    created = speech.create_video_job('meeting.mp4', path.stat().st_size, hashlib.sha256(path.read_bytes()).hexdigest(), path, 10000)
    job = speech.claim_next_job()
    speech.complete_transcription(job, TranscriptionResult('en', [TranscriptSegment(500,1500,'Original speech.')]))
    return created, path


def test_automatic_queue_storage_images_and_refresh(client, database, recording, uploads, monkeypatch):
    created, original = recording
    file_id = created.file_id
    endpoint = f'/videos/{file_id}/visual-transcript'
    assert client.get(endpoint).json()['status'] == 'queued'
    assert client.get(f'/files/{file_id}/storage-savings').json()['status'] == 'processing'
    job = repository.claim()
    assert job and repository.claim() is None
    def extract(path, output, duration_ms, **kwargs):
        output.mkdir(parents=True)
        target = output/'frame.jpg'
        target.write_bytes(b'\xff\xd8jpeg content')
        return [processor.ExtractedFrame(0,5000,target,'0'*16,999),
                processor.ExtractedFrame(6000,10000,target,'0'*16,999)]
    monkeypatch.setattr(service,'extract_visuals',extract)
    service.process_visual_job(job)
    result = client.get(endpoint)
    assert result.status_code == 200
    data = result.json()
    assert data['status'] == 'completed'
    assert 'image_path' not in result.text
    assert data['sections'][0]['segments'][0]['text'] == 'Original speech.'
    frame_id = data['sections'][0]['visual']['id']
    image = client.get(f'/videos/{file_id}/visuals/{frame_id}/image')
    assert image.status_code == 200 and image.content == b'\xff\xd8jpeg content'
    assert client.get(f'/videos/{file_id+1}/visuals/{frame_id}/image').status_code == 404
    assert client.get(endpoint).json() == data
    assert client.post(endpoint).json()['status'] == 'completed'  # Idempotent.
    savings = client.get(f'/files/{file_id}/storage-savings').json()
    text_bytes = client.get(f'/videos/{file_id}/transcript/download').content
    assert savings['optimized_size_bytes'] == len(text_bytes)+len(image.content)
    assert savings['components'][1]['file_count'] == 1  # Shared image measured once, from disk.
    assert original.read_bytes() == b'original recording preserved'
    with database() as connection:
        connection.execute("UPDATE video_frames SET image_path=%s WHERE id=%s", (str(original),frame_id))
    assert client.get(f'/videos/{file_id}/visuals/{frame_id}/image').status_code == 404
    assert client.get(f'/files/{file_id}/storage-savings').json()['status'] == 'unavailable'


def test_failure_cleanup_and_retry_preserve_speech(client, database, recording, monkeypatch, uploads):
    created, original = recording
    def fail(path, output, *args, **kwargs):
        output.mkdir(parents=True)
        (output/'partial.jpg').write_bytes(b'partial')
        raise processor.VisualExtractionError('The recording could not be decoded for visual analysis.')
    monkeypatch.setattr(service,'extract_visuals',fail)
    job = repository.claim()
    service.process_visual_job(job)
    endpoint = f'/videos/{created.file_id}/visual-transcript'
    assert client.get(endpoint).json()['status'] == 'failed'
    assert client.get(f'/videos/{created.file_id}/transcript').json()['segments'][0]['text'] == 'Original speech.'
    assert original.is_file() and not list((uploads/'visuals').rglob('*.jpg'))
    assert client.post(endpoint).json()['status'] == 'queued'
    assert repository.claim() is not None
    assert client.get('/videos/999999/visual-transcript').status_code == 404
    assert client.post('/videos/999999/visual-transcript').status_code == 404


def test_interrupted_visual_job_and_no_speech(client, database, recording):
    created, _ = recording
    repository.claim()
    assert speech.fail_interrupted_jobs() == 1
    assert speech.get_transcript(created.file_id).status == 'completed'
    with database() as connection:
        connection.execute('DELETE FROM transcript_segments WHERE file_id=%s',(created.file_id,))
    assert client.get(f'/videos/{created.file_id}/visual-transcript').json()['sections'] == []


def test_incomplete_speech_is_not_queued_for_visuals(client, database, uploads):
    created = speech.create_video_job('pending.mp4', 1, 'hash', uploads/'pending.mp4', 1000)
    assert client.post(f'/videos/{created.file_id}/visual-transcript').status_code == 409
    assert repository.state(created.file_id) is None
    data = client.get(f'/videos/{created.file_id}/visual-transcript').json()
    assert data['speech_status'] == 'queued' and data['sections'] == []


def test_database_failure_is_atomic_and_retry_cleans_interrupted_images(database, recording, uploads, monkeypatch):
    created, original = recording
    abandoned = uploads/'visuals'/str(created.file_id)/('a'*32)
    abandoned.mkdir(parents=True)
    (abandoned/'partial.jpg').write_bytes(b'interrupted output')
    def invalid_frames(path, output, duration_ms, **kwargs):
        assert not abandoned.exists()
        output.mkdir(parents=True)
        target = output/'frame.jpg'
        target.write_bytes(b'jpeg')
        return [processor.ExtractedFrame(0,1000,target,'0'*16,4),
                processor.ExtractedFrame(1000,500,target,'1'*16,4)]
    monkeypatch.setattr(service,'extract_visuals',invalid_frames)
    service.process_visual_job(repository.claim())
    assert repository.state(created.file_id)['status'] == 'failed'
    assert repository.frames(created.file_id) == []
    assert not list((uploads/'visuals').rglob('*.jpg'))
    assert speech.get_transcript(created.file_id).segments[0].text == 'Original speech.'
    assert original.is_file()
