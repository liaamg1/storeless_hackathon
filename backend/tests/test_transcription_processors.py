import json
import math
import subprocess
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.processors import audio_extractor, speech_recognizer
from app.processors.audio_extractor import MediaProcessingError, MediaToolUnavailableError
from app.schemas.transcription import VideoTranscript
from app.services.transcript_export import format_transcript


def test_installed_speech_decoder_can_read_extracted_wav(tmp_path):
    """Catch PyAV/Faster Whisper API incompatibilities without downloading a model."""
    from faster_whisper.audio import decode_audio

    path = tmp_path / 'extracted.wav'
    with wave.open(str(path), 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b'\x00\x00' * 16000)

    decoded = decode_audio(str(path), sampling_rate=16000)
    assert decoded.shape == (16000,)
    assert not decoded.any()


@pytest.fixture
def wav_audio(tmp_path):
    path = tmp_path / 'audio.wav'
    with wave.open(str(path), 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b'\x00\x00' * 16000 * 5)
    return path


@pytest.mark.parametrize('seconds,expected', [(0, 0), (1.234, 1234), (60.5, 60500)])
def test_millisecond_conversion(seconds, expected):
    assert speech_recognizer.seconds_to_milliseconds(seconds) == expected


@pytest.mark.parametrize('seconds', [-1, math.inf, math.nan])
def test_invalid_timestamps(seconds):
    with pytest.raises(ValueError):
        speech_recognizer.seconds_to_milliseconds(seconds)


def test_export_formatting():
    transcript = VideoTranscript(file_id=1, filename='meeting.mp4', duration_ms=5000, language='en', segments=[
        {'id': 1, 'start_ms': 1234, 'end_ms': 4567, 'text': 'Hello meeting.'},
    ])
    assert format_transcript(transcript) == (
        'meeting.mp4\n\nHello meeting.\n'
    )


def test_audio_extraction_command(tmp_path, monkeypatch):
    source = tmp_path / 'video ; unsafe.mp4'
    target = tmp_path / 'audio.wav'
    calls = []
    def run(arguments, **kwargs):
        calls.append((arguments, kwargs))
        target.write_bytes(b'wav' * 50)
        return SimpleNamespace(stdout='')
    monkeypatch.setattr(audio_extractor.subprocess, 'run', run)
    assert audio_extractor.extract_audio(source, target, 'ffmpeg-custom', 30) == target
    arguments, options = calls[0]
    assert arguments == ['ffmpeg-custom', '-nostdin', '-v', 'error', '-y', '-protocol_whitelist', 'file,pipe',
                         '-threads', '1', '-i', str(source), '-map', '0:a:0', '-vn', '-ac', '1', '-ar', '16000',
                         '-c:a', 'pcm_s16le', str(target)]
    assert 'shell' not in options
    assert options['timeout'] == 30
    assert options['check'] is True


def test_split_video_segments_uses_ffmpeg_segment_stream_copy(tmp_path, monkeypatch):
    source = tmp_path / 'large_recording.mp4'
    source.write_bytes(b'mp4')
    seg_dir = tmp_path / 'segments'
    calls = []

    def run(arguments, **kwargs):
        calls.append((arguments, kwargs))
        for idx in range(4):
            (seg_dir / f'segment_{idx:03d}.mp4').write_bytes(b'valid-mp4-segment')
        (seg_dir / 'segments.csv').write_text(
            'segment_000.mp4,0.000000,300.120000\n'
            'segment_001.mp4,300.120000,599.880000\n'
            'segment_002.mp4,599.880000,900.400000\n'
            'segment_003.mp4,900.400000,1200.000000\n',
            encoding='utf-8',
        )
        return SimpleNamespace(stdout='')

    monkeypatch.setattr(audio_extractor.subprocess, 'run', run)
    segments = audio_extractor.split_video_segments(
        source, seg_dir, 1_200_000, parts=4, ffmpeg='ffmpeg-custom', timeout=90
    )
    arguments, options = calls[0]
    assert arguments == [
        'ffmpeg-custom', '-nostdin', '-v', 'error', '-y', '-protocol_whitelist', 'file,pipe',
        '-i', str(source), '-f', 'segment', '-segment_time', '300', '-c', 'copy',
        '-reset_timestamps', '1', '-segment_list', str(seg_dir / 'segments.csv'),
        '-segment_list_type', 'csv', str(seg_dir / 'segment_%03d.mp4'),
    ]
    assert options['timeout'] == 90
    assert [(s.path.name, s.start_ms, s.end_ms) for s in segments] == [
        ('segment_000.mp4', 0, 300120),
        ('segment_001.mp4', 300120, 599880),
        ('segment_002.mp4', 599880, 900400),
        ('segment_003.mp4', 900400, 1200000),
    ]


def test_extract_segmented_audio_concatenates_pcm_and_cleans_segments(tmp_path, monkeypatch):
    source = tmp_path / 'large_recording.mp4'
    source.write_bytes(b'mp4')
    target = tmp_path / 'combined.wav'

    def fake_split(video_path, output_dir, duration_ms, *, parts=4, ffmpeg='ffmpeg', timeout=3600):
        output_dir.mkdir(parents=True, exist_ok=True)
        result = []
        for idx in range(parts):
            seg = output_dir / f'segment_{idx:03d}.mp4'
            seg.write_bytes(b'seg')
            result.append(audio_extractor.VideoSegment(seg, idx * 1000, (idx + 1) * 1000))
        return result

    def fake_extract(video_path, output_path, ffmpeg='ffmpeg', timeout=3600):
        with wave.open(str(output_path), 'wb') as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(16000)
            handle.writeframes(b'\x01\x00' * 1600)
        return output_path

    monkeypatch.setattr(audio_extractor, 'split_video_segments', fake_split)
    monkeypatch.setattr(audio_extractor, 'extract_audio', fake_extract)
    output = audio_extractor.extract_segmented_audio(
        source, target, 'ffmpeg', 60, duration_ms=4000, parts=4
    )
    assert output == target
    assert not (tmp_path / 'mp4_segments').exists()
    with wave.open(str(target), 'rb') as handle:
        assert handle.getnchannels() == 1
        assert handle.getframerate() == 16000
        assert handle.getnframes() == 4 * 1600


@pytest.mark.parametrize('error,expected', [
    (FileNotFoundError(), MediaToolUnavailableError),
    (subprocess.CalledProcessError(1, ['ffmpeg'], stderr='private details'), MediaProcessingError),
    (subprocess.TimeoutExpired(['ffmpeg'], 1), MediaProcessingError),
])
def test_media_tool_failures(monkeypatch, error, expected):
    def run(*args, **kwargs):
        raise error
    monkeypatch.setattr(audio_extractor.subprocess, 'run', run)
    with pytest.raises(expected) as result:
        audio_extractor.run_media_command(['ffmpeg'], 1)
    assert 'private details' not in str(result.value)


@pytest.mark.parametrize('metadata,message', [
    ({'format': {'format_name': 'mov,mp4', 'duration': '2.5'}, 'streams': [{'codec_type': 'video'}]}, 'no audio'),
    ({'format': {'format_name': 'mp3', 'duration': '2.5'}, 'streams': [{'codec_type': 'audio'}]}, 'valid MP4'),
    ({'format': {'format_name': 'mp4', 'duration': 'NaN'}, 'streams': [{'codec_type': 'video'}, {'codec_type': 'audio'}]}, 'duration'),
    ({'format': {}}, 'metadata'),
])
def test_video_metadata_validation(monkeypatch, metadata, message):
    monkeypatch.setattr(audio_extractor, 'run_media_command', lambda *args: json.dumps(metadata))
    with pytest.raises(MediaProcessingError, match=message):
        audio_extractor.validate_video(Path('/tmp/recording.mp4'))


def test_speech_iterator_is_consumed_and_ordered(monkeypatch, wav_audio):
    consumed = []
    def transcribe(path, **kwargs):
        assert kwargs['language'] is None
        assert kwargs['vad_filter'] is True
        def segments():
            consumed.append(1)
            yield SimpleNamespace(start=2.5, end=3.0, text=' Second ')
            consumed.append(2)
            yield SimpleNamespace(start=0.25, end=1.0, text=' First ')
            yield SimpleNamespace(start=1.1, end=1.2, text=' ')
        return segments(), SimpleNamespace(language='en')
    monkeypatch.setattr(speech_recognizer, 'load_model', lambda *args: SimpleNamespace(transcribe=transcribe))
    result = speech_recognizer.transcribe_audio(wav_audio, download_root='/tmp/models')
    assert consumed == [1, 2]
    assert result.language == 'en'
    assert [(segment.start_ms, segment.end_ms, segment.text) for segment in result.segments] == [
        (250, 1000, 'First'), (2500, 3000, 'Second'),
    ]


def test_no_speech_and_explicit_language(monkeypatch, wav_audio):
    def transcribe(path, **kwargs):
        assert kwargs['language'] == 'sv'
        return iter([]), SimpleNamespace(language='sv')
    monkeypatch.setattr(speech_recognizer, 'load_model', lambda *args: SimpleNamespace(transcribe=transcribe))
    assert speech_recognizer.transcribe_audio(wav_audio, language='sv', download_root='/tmp/models').segments == []


def test_iterator_failure_is_not_completed(monkeypatch, wav_audio):
    def transcribe(*args, **kwargs):
        def segments():
            yield SimpleNamespace(start=0, end=1, text='Partial')
            raise RuntimeError('private transcript details')
        return segments(), SimpleNamespace(language='en')
    monkeypatch.setattr(speech_recognizer, 'load_model', lambda *args: SimpleNamespace(transcribe=transcribe))
    with pytest.raises(speech_recognizer.SpeechRecognitionError) as error:
        speech_recognizer.transcribe_audio(wav_audio, download_root='/tmp/models')
    assert 'private transcript details' not in str(error.value)


def test_model_is_reused_and_loading_failure_is_safe(monkeypatch):
    import faster_whisper
    speech_recognizer.load_model.cache_clear()
    calls = []
    def create(*args, **kwargs):
        calls.append((args, kwargs))
        return object()
    monkeypatch.setattr(faster_whisper, 'WhisperModel', create)
    first = speech_recognizer.load_model('tiny', 'cpu', 'int8', '/tmp/cache')
    assert first is speech_recognizer.load_model('tiny', 'cpu', 'int8', '/tmp/cache')
    assert len(calls) == 1
    assert calls[0][1]['device'] == 'cpu'
    assert calls[0][1]['cpu_threads'] == 3
    assert calls[0][1]['num_workers'] == 1
    speech_recognizer.load_model.cache_clear()
    def fail(*args, **kwargs):
        raise RuntimeError('private details')
    monkeypatch.setattr(faster_whisper, 'WhisperModel', fail)
    with pytest.raises(speech_recognizer.SpeechRecognitionError, match='Could not load'):
        speech_recognizer.load_model('tiny', 'cpu', 'int8', '/tmp/cache')
    speech_recognizer.load_model.cache_clear()



def test_readable_paragraphs_preserve_words_and_search_targets():
    transcript = VideoTranscript(file_id=1, filename='Räksmörgås.mp4', duration_ms=10000, language='sv', segments=[
        {'id': 1, 'start_ms': 0, 'end_ms': 1000, 'text': '  Some of the most successful\npeople '},
        {'id': 2, 'start_ms': 1000, 'end_ms': 2000, 'text': " are the ones who've had the most failures.\n\n"},
        {'id': 3, 'start_ms': 5000, 'end_ms': 6000, 'text': 'Försök igen.'},
        {'id': 4, 'start_ms': 6000, 'end_ms': 7000, 'text': '  \n '},
    ])
    assert transcript.paragraphs == [[1, 2], [3]]
    assert transcript.model_dump()['paragraphs'] == [[1, 2], [3]]
    assert format_transcript(transcript) == (
        "Räksmörgås.mp4\n\nSome of the most successful people are the ones who've had the most failures."
        "\n\nFörsök igen.\n"
    )
    # Formatting never rewrites persisted text or removes timestamp metadata.
    assert transcript.segments[1].text.endswith('failures.\n\n')
    assert transcript.segments[2].start_ms == 5000


def test_long_continuous_transcript_is_split_into_readable_paragraphs():
    sentence = 'This sentence should be preserved. '
    segments = [
        {'id': index, 'start_ms': index * 1000, 'end_ms': (index + 1) * 1000, 'text': sentence}
        for index in range(100)
    ]
    transcript = VideoTranscript(file_id=1, filename='long.mp4', duration_ms=100000, language='en', segments=segments)
    assert len(transcript.paragraphs) > 1
    assert [id for paragraph in transcript.paragraphs for id in paragraph] == list(range(100))
    output = format_transcript(transcript)
    assert output.count(sentence.strip()) == 100
    assert len(output.encode('utf-8')) < 5000


@pytest.mark.parametrize('segments', [[], [
    {'id': 1, 'start_ms': 0, 'end_ms': 1000, 'text': ' \n '},
]])
def test_empty_readable_transcript(segments):
    transcript = VideoTranscript(file_id=1, filename='silent.mp4', duration_ms=1000, language=None, segments=segments)
    assert transcript.paragraphs == []
    assert format_transcript(transcript) == 'silent.mp4\n\nNo speech was detected.\n'


def test_multi_hour_audio_uses_bounded_windows_and_releases_them(monkeypatch):
    import weakref
    import numpy as np

    duration = 2 * 3600 + 35 * 60 + 18
    windows = []
    previous = None
    progress = []

    class LongWav:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def getnchannels(self): return 1
        def getsampwidth(self): return 2
        def getframerate(self): return 16000
        def getcomptype(self): return 'NONE'
        def getnframes(self): return duration * 16000
        def setpos(self, frame): self.position = frame
        def readframes(self, frames):
            assert frames <= 64 * 16000, 'Never read the whole multi-hour recording'
            assert self.position + frames <= self.getnframes()
            return b'\x00\x00' * frames

    def transcribe(audio, **kwargs):
        nonlocal previous
        assert isinstance(audio, np.ndarray) and audio.dtype == np.float32
        assert audio.size <= 64 * 16000
        assert previous is None or previous() is None, 'Old windows must be released'
        windows.append(audio.size)
        previous = weakref.ref(audio)
        return iter([]), SimpleNamespace(language='en')

    monkeypatch.setattr(speech_recognizer.wave, 'open', lambda *args: LongWav())
    monkeypatch.setattr(speech_recognizer, 'load_model', lambda *args: SimpleNamespace(transcribe=transcribe))
    result = speech_recognizer.transcribe_audio(
        Path('/virtual/multi-hour.wav'), download_root='/unused',
        on_progress=lambda done, total: progress.append((done, total)),
    )
    assert result.segments == []
    assert len(windows) == math.ceil(duration / 60)
    assert progress[-1] == (duration * 1000, duration * 1000)
    assert all(done <= total for done, total in progress)
    assert [done for done, _ in progress] == sorted(done for done, _ in progress)


def test_chunk_context_is_not_duplicated_and_timestamps_keep_original_offsets(monkeypatch, tmp_path):
    path = tmp_path / 'boundary.wav'
    with wave.open(str(path), 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b'\x00\x00' * 16000 * 5)
    calls = []
    def transcribe(audio, **kwargs):
        calls.append(audio.size)
        # Core windows: [0,2], [2,4], [4,5]. Read starts: 0, 1, 3 seconds.
        rows = [
            [(0.5, 1.0, 'First'), (1.9, 2.3, 'Boundary')],
            [(0.9, 1.3, 'Boundary'), (2.0, 2.5, 'Middle'), (3.1, 3.6, 'Last')],
            [(0.0, 0.5, 'Middle'), (1.1, 1.6, 'Last')],
        ][len(calls) - 1]
        return iter(SimpleNamespace(start=start, end=end, text=text) for start, end, text in rows), SimpleNamespace(language='en')
    monkeypatch.setattr(speech_recognizer, 'load_model', lambda *args: SimpleNamespace(transcribe=transcribe))
    result = speech_recognizer.transcribe_audio(path, chunk_seconds=2, download_root='/unused')
    assert [(s.start_ms, s.end_ms, s.text) for s in result.segments] == [
        (500, 1000, 'First'), (1900, 2300, 'Boundary'),
        (3000, 3500, 'Middle'), (4100, 4600, 'Last'),
    ]
    assert calls == [3 * 16000, 4 * 16000, 2 * 16000]


def test_failed_chunk_does_not_report_completed_progress(monkeypatch, wav_audio):
    progress = []
    def transcribe(audio, **kwargs):
        def fail():
            raise RuntimeError('private data')
            yield
        return fail(), SimpleNamespace(language='en')
    monkeypatch.setattr(speech_recognizer, 'load_model', lambda *args: SimpleNamespace(transcribe=transcribe))
    with pytest.raises(speech_recognizer.SpeechRecognitionError):
        speech_recognizer.transcribe_audio(wav_audio, download_root='/unused', on_progress=lambda *args: progress.append(args))
    assert progress == []


@pytest.mark.parametrize('chunk,threads', [(0, 2), (121, 2), (60, 0)])
def test_invalid_inference_resource_settings(monkeypatch, chunk, threads):
    from app.core.config import get_transcription_settings
    monkeypatch.setenv('WHISPER_CHUNK_SECONDS', str(chunk))
    monkeypatch.setenv('WHISPER_CPU_THREADS', str(threads))
    with pytest.raises(ValueError):
        get_transcription_settings()


def test_default_inference_resource_settings(monkeypatch):
    from app.core.config import get_transcription_settings
    monkeypatch.delenv('WHISPER_CHUNK_SECONDS', raising=False)
    monkeypatch.delenv('WHISPER_CPU_THREADS', raising=False)
    settings = get_transcription_settings()
    assert settings.chunk_seconds == 60
    assert settings.cpu_threads == 3


def test_pcm_samples_are_normalized_without_losing_audio(monkeypatch, tmp_path):
    import struct
    import numpy as np

    path = tmp_path / 'speech.wav'
    with wave.open(str(path), 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(struct.pack('<4h', -32768, 32767, 0, 16384) * 4000)
    def transcribe(audio, **kwargs):
        np.testing.assert_array_equal(audio[:4], np.array([-1, 32767 / 32768, 0, .5], dtype=np.float32))
        return iter([SimpleNamespace(start=0, end=1, text='Spoken content')]), SimpleNamespace(language='en')
    monkeypatch.setattr(speech_recognizer, 'load_model', lambda *args: SimpleNamespace(transcribe=transcribe))
    result = speech_recognizer.transcribe_audio(path, download_root='/unused')
    assert result.segments[0].text == 'Spoken content'


def test_invalid_extracted_format_is_rejected_before_model_loading(monkeypatch, tmp_path):
    path = tmp_path / 'stereo.wav'
    with wave.open(str(path), 'wb') as audio:
        audio.setnchannels(2)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b'\x00' * 64000)
    def unexpected_load(*args):
        raise AssertionError('Must validate extracted format before loading a model')
    monkeypatch.setattr(speech_recognizer, 'load_model', unexpected_load)
    with pytest.raises(speech_recognizer.SpeechRecognitionError, match='mono 16 kHz PCM WAV'):
        speech_recognizer.transcribe_audio(path, download_root='/unused')
