"""Readable, compact UTF-8 exports of persisted transcripts."""
from app.schemas.transcription import VideoTranscript


def format_transcript(transcript: VideoTranscript) -> str:
    """Keep every spoken word in paragraphs, without timestamp or status clutter."""
    segments = {segment.id: " ".join(segment.text.split()) for segment in transcript.segments}
    paragraphs = [" ".join(segments[id] for id in paragraph) for paragraph in transcript.paragraphs]
    title = " ".join(transcript.filename.split())
    return title + "\n\n" + "\n\n".join(paragraphs or ["No speech was detected."]) + "\n"


def encode_transcript(transcript: VideoTranscript) -> bytes:
    """The actual downloadable file bytes, also used for storage measurement."""
    return format_transcript(transcript).encode('utf-8')
