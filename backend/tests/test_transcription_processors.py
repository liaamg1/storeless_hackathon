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
        assert kwargs['language'] == 'en'
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
    assert calls[0][1]['cpu_threads'] == 2
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


def test_full_file_is_transcribed_once_untouched_with_pinned_language(monkeypatch, tmp_path):
    path = tmp_path / 'full.wav'
    with wave.open(str(path), 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b'\x00\x00' * 16000 * 130)
    calls, progress = [], []
    def transcribe(audio, **kwargs):
        calls.append((audio, kwargs))
        rows = [(0.5, 1.0, 'First'), (70.0, 71.0, 'After a minute'), (125.0, 129.0, 'Last')]
        return iter(SimpleNamespace(start=s, end=e, text=t) for s, e, t in rows), SimpleNamespace(language='en')
    monkeypatch.setattr(speech_recognizer, 'load_model', lambda *args: SimpleNamespace(transcribe=transcribe))
    result = speech_recognizer.transcribe_audio(path, download_root='/unused',
                                                on_progress=lambda done, total: progress.append((done, total)))
    assert len(calls) == 1
    audio, kwargs = calls[0]
    assert audio == str(path)  # the file itself, never a sliced or converted buffer
    assert kwargs['language'] == 'en'
    assert kwargs['vad_filter'] is True
    assert kwargs['condition_on_previous_text'] is False
    assert [(s.start_ms, s.end_ms, s.text) for s in result.segments] == [
        (500, 1000, 'First'), (70000, 71000, 'After a minute'), (125000, 129000, 'Last'),
    ]
    assert all(s.speaker == 'Speaker' for s in result.segments)
    assert progress[-1] == (130000, 130000)
    assert [done for done, _ in progress] == sorted(done for done, _ in progress)


def test_speaker_assignment_never_changes_text_or_timestamps(tmp_path):
    from app.processors.speaker_diarizer import assign_speakers
    tones = [110, 400] * 6
    path = tmp_path / 'voices.wav'
    _voice_wav(path, tones)
    original = speech_recognizer.TranscriptionResult('en', [
        speech_recognizer.TranscriptSegment(i * 1000, (i + 1) * 1000, f'Words {i}') for i in range(len(tones))
    ])
    before = path.read_bytes()
    labelled = assign_speakers(path, original)
    assert path.read_bytes() == before
    assert labelled.language == 'en'
    assert [(s.start_ms, s.end_ms, s.text) for s in labelled.segments] == [
        (s.start_ms, s.end_ms, s.text) for s in original.segments
    ]


def test_failed_transcription_does_not_report_completed_progress(monkeypatch, wav_audio):
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


@pytest.mark.parametrize('threads', [0, -1])
def test_invalid_inference_resource_settings(monkeypatch, threads):
    from app.core.config import get_transcription_settings
    monkeypatch.setenv('WHISPER_CPU_THREADS', str(threads))
    with pytest.raises(ValueError):
        get_transcription_settings()


def test_default_inference_resource_settings(monkeypatch):
    from app.core.config import get_transcription_settings
    monkeypatch.delenv('WHISPER_CPU_THREADS', raising=False)
    monkeypatch.delenv('WHISPER_LANGUAGE', raising=False)
    settings = get_transcription_settings()
    assert settings.language == 'en'
    assert settings.cpu_threads == 2


def test_auto_language_is_opt_in(monkeypatch):
    from app.core.config import get_transcription_settings
    monkeypatch.setenv('WHISPER_LANGUAGE', 'auto')
    assert get_transcription_settings().language is None


def test_wav_is_passed_through_byte_for_byte(monkeypatch, tmp_path):
    import struct

    path = tmp_path / 'speech.wav'
    with wave.open(str(path), 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(struct.pack('<4h', -32768, 32767, 0, 16384) * 4000)
    def transcribe(audio, **kwargs):
        assert audio == str(path)
        assert path.read_bytes()[44:52] == struct.pack('<4h', -32768, 32767, 0, 16384)
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


def _voice_wav(path, tones):
    """Alternating one-second 'voices' made of different harmonic stacks."""
    import numpy as np
    t = np.arange(16000) / 16000
    chunks = []
    for base in tones:
        wave_ = sum(np.sin(2 * np.pi * base * h * t) / h for h in range(1, 12))
        chunks.append((wave_ / np.abs(wave_).max() * 12000).astype('<i2'))
    with wave.open(str(path), 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b''.join(chunk.tobytes() for chunk in chunks))


def test_speaker_labels_fall_back_on_unreadable_audio(tmp_path):
    from app.processors.speaker_diarizer import label_speakers
    from app.processors.speech_recognizer import TranscriptSegment
    segments = [TranscriptSegment(0, 1000, 'Hello')]
    assert label_speakers(tmp_path / 'missing.wav', segments) == ['Speaker']


def test_speaker_labels_fall_back_for_too_little_audio(wav_audio):
    from app.processors.speaker_diarizer import label_speakers
    from app.processors.speech_recognizer import TranscriptSegment
    segments = [TranscriptSegment(0, 1000, 'Silence'), TranscriptSegment(1000, 2000, 'More silence')]
    assert label_speakers(wav_audio, segments) == ['Speaker', 'Speaker']


def test_speaker_labels_separate_different_voices(tmp_path):
    from app.processors.speaker_diarizer import label_speakers
    from app.processors.speech_recognizer import TranscriptSegment
    tones = [110, 400] * 6
    path = tmp_path / 'voices.wav'
    _voice_wav(path, tones)
    segments = [TranscriptSegment(i * 1000, (i + 1) * 1000, f'Segment {i}') for i in range(len(tones))]
    labels = label_speakers(path, segments)
    assert labels[0::2] == ['Speaker 1'] * 6
    assert labels[1::2] == ['Speaker 2'] * 6


def test_single_voice_stays_generic_speaker(tmp_path):
    from app.processors.speaker_diarizer import label_speakers
    from app.processors.speech_recognizer import TranscriptSegment
    path = tmp_path / 'one_voice.wav'
    _voice_wav(path, [220] * 12)
    segments = [TranscriptSegment(i * 1000, (i + 1) * 1000, f'Segment {i}') for i in range(12)]
    assert label_speakers(path, segments) == ['Speaker'] * 12


def test_short_segments_are_padded_for_embedding_only(tmp_path):
    from app.processors.speaker_diarizer import assign_speakers
    from app.processors.speech_recognizer import TranscriptSegment, TranscriptionResult
    tones = [110, 400] * 6
    path = tmp_path / 'short.wav'
    _voice_wav(path, tones)
    # 300 ms segments centred in each one-second voice block.
    original = TranscriptionResult('en', [
        TranscriptSegment(i * 1000 + 350, i * 1000 + 650, f'Hi {i}') for i in range(len(tones))
    ])
    labelled = assign_speakers(path, original)
    assert [(s.start_ms, s.end_ms, s.text) for s in labelled.segments] == [
        (s.start_ms, s.end_ms, s.text) for s in original.segments
    ]
    assert all(s.speaker.startswith('Speaker') for s in labelled.segments)


def test_stored_segments_without_speaker_default_to_speaker():
    transcript = VideoTranscript(file_id=1, filename='old.mp4', duration_ms=1000, language='en', segments=[
        {'id': 1, 'start_ms': 0, 'end_ms': 500, 'text': 'Old', 'speaker': None},
        {'id': 2, 'start_ms': 500, 'end_ms': 900, 'text': 'Row'},
    ])
    assert [segment.speaker for segment in transcript.segments] == ['Speaker', 'Speaker']
    assert transcript.paragraphs == [[1, 2]]


def test_paragraphs_break_when_speaker_changes():
    transcript = VideoTranscript(file_id=1, filename='talk.mp4', duration_ms=1000, language='en', segments=[
        {'id': 1, 'start_ms': 0, 'end_ms': 500, 'text': 'Hi.', 'speaker': 'Speaker 1'},
        {'id': 2, 'start_ms': 500, 'end_ms': 900, 'text': 'Hello.', 'speaker': 'Speaker 2'},
    ])
    assert transcript.paragraphs == [[1], [2]]


def test_word_timestamps_split_co_presenter_handoff_within_segment():
    words = [
        SimpleNamespace(start=0.0, end=0.5, word=' Hello,'),
        SimpleNamespace(start=0.5, end=2.0, word=" GraalVM's ahead-of-time compilation in production."),
        SimpleNamespace(start=2.1, end=2.3, word=' It'),
        SimpleNamespace(start=2.3, end=2.5, word=' will'),
        SimpleNamespace(start=2.5, end=2.7, word=' be'),
        SimpleNamespace(start=2.7, end=3.1, word=' presented'),
        SimpleNamespace(start=3.1, end=3.3, word=' by'),
        SimpleNamespace(start=3.3, end=3.6, word=' me,'),
        SimpleNamespace(start=3.6, end=4.1, word=' Ahmadiyya'),
        SimpleNamespace(start=4.1, end=4.7, word=' Zambratahani,'),
        SimpleNamespace(start=4.8, end=5.0, word=' and'),
        SimpleNamespace(start=5.0, end=5.3, word=' me,'),
        SimpleNamespace(start=5.3, end=5.8, word=' Tommy'),
        SimpleNamespace(start=5.8, end=6.3, word=' Watson.'),
    ]
    raw_segment = SimpleNamespace(start=0.0, end=6.3, text=' '.join(w.word.strip() for w in words), words=words)
    parts = speech_recognizer._split_segment_words(raw_segment)
    assert [(p.start_ms, p.end_ms, p.text) for p in parts] == [
        (0, 2000, "Hello, GraalVM's ahead-of-time compilation in production."),
        (2100, 4700, 'It will be presented by me, Ahmadiyya Zambratahani,'),
        (4800, 6300, 'and me, Tommy Watson.'),
    ]


def test_speaker_labels_detect_second_speaker_in_short_intro_with_single_turn(tmp_path):
    from app.processors.speaker_diarizer import label_speakers
    from app.processors.speech_recognizer import TranscriptSegment
    path = tmp_path / 'intro.wav'
    _voice_wav(path, [110, 110, 320])
    segments = [
        TranscriptSegment(0, 1000, "Hello, and we can talk about GraalVM's ahead-of-time compilation."),
        TranscriptSegment(1000, 2000, 'It will be presented by me, Ahmadiyya Zambratahani,'),
        TranscriptSegment(2000, 3000, 'and me, Tommy Watson.'),
    ]
    assert label_speakers(path, segments) == ['Speaker 1', 'Speaker 1', 'Speaker 2']
