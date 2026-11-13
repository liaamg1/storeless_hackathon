from app.schemas.transcription import VideoTranscript


def format_timestamp(milliseconds: int) -> str:
    """Keep millisecond precision in readable exported timestamp ranges."""
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02}.{millis:03}"


def format_transcript(transcript: VideoTranscript) -> str:
    """Export persisted text with timestamps; no inference runs during download."""
    lines = [f"File: {transcript.filename}", "Status: Completed", ""]
    for segment in transcript.segments:
        lines.extend([
            f"[{format_timestamp(segment.start_ms)} – {format_timestamp(segment.end_ms)}]",
            segment.text, "",
        ])
    if not transcript.segments:
        lines.append("No speech was detected.")
    return "\n".join(lines) + "\n"
