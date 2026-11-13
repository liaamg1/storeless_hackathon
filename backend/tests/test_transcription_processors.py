import json
import math
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.processors import audio_extractor, speech_recognizer
from app.processors.audio_extractor import MediaProcessingError, MediaToolUnavailableError
from app.schemas.transcription import VideoTranscript
from app.services.transcript_export import format_timestamp, format_transcript


@pytest.mark.parametrize('seconds,expected', [(0, 0), (1.234, 1234), (60.5, 60500)])
def test_millisecond_conversion(seconds, expected):
    assert speech_recognizer.seconds_to_milliseconds(seconds) == expected


@pytest.mark.parametrize('seconds', [-1, math.inf, math.nan])
def test_invalid_timestamps(seconds):
    with pytest.raises(ValueError):
        speech_recognizer.seconds_to_milliseconds(seconds)


def test_export_formatting():
    assert format_timestamp(3661234) == '01:01:01.234'
    transcript = VideoTranscript(file_id=1, filename='meeting.mp4', duration_ms=5000, language='en', segments=[
        {'id': 1, 'start_ms': 1234, 'end_ms': 4567, 'text': 'Hello meeting.'},
    ])
    assert format_transcript(transcript) == (
        'File: meeting.mp4\nStatus: Completed\n\n[00:00:01.234 – 00:00:04.567]\nHello meeting.\n\n'
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
                         '-i', str(source), '-map', '0:a:0', '-vn', '-ac', '1', '-ar', '16000',
                         '-c:a', 'pcm_s16le', str(target)]
    assert 'shell' not in options
    assert options['timeout'] == 30
    assert options['check'] is True


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


def test_speech_iterator_is_consumed_and_ordered(monkeypatch):
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
    result = speech_recognizer.transcribe_audio(Path('/tmp/audio.wav'), download_root='/tmp/models')
    assert consumed == [1, 2]
    assert result.language == 'en'
    assert [(segment.start_ms, segment.end_ms, segment.text) for segment in result.segments] == [
        (250, 1000, 'First'), (2500, 3000, 'Second'),
    ]


def test_no_speech_and_explicit_language(monkeypatch):
    def transcribe(path, **kwargs):
        assert kwargs['language'] == 'sv'
        return iter([]), SimpleNamespace(language='sv')
    monkeypatch.setattr(speech_recognizer, 'load_model', lambda *args: SimpleNamespace(transcribe=transcribe))
    assert speech_recognizer.transcribe_audio(Path('/tmp/audio.wav'), language='sv', download_root='/tmp/models').segments == []


def test_iterator_failure_is_not_completed(monkeypatch):
    def transcribe(*args, **kwargs):
        def segments():
            yield SimpleNamespace(start=0, end=1, text='Partial')
            raise RuntimeError('private transcript details')
        return segments(), SimpleNamespace(language='en')
    monkeypatch.setattr(speech_recognizer, 'load_model', lambda *args: SimpleNamespace(transcribe=transcribe))
    with pytest.raises(speech_recognizer.SpeechRecognitionError) as error:
        speech_recognizer.transcribe_audio(Path('/tmp/audio.wav'), download_root='/tmp/models')
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
    speech_recognizer.load_model.cache_clear()
    def fail(*args, **kwargs):
        raise RuntimeError('private details')
    monkeypatch.setattr(faster_whisper, 'WhisperModel', fail)
    with pytest.raises(speech_recognizer.SpeechRecognitionError, match='Could not load'):
        speech_recognizer.load_model('tiny', 'cpu', 'int8', '/tmp/cache')
    speech_recognizer.load_model.cache_clear()
