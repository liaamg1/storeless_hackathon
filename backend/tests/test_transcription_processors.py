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
