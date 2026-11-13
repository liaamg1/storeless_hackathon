"""Offline visual documents, streamed with embedded JPEGs and no extra dependencies."""
import base64
from collections.abc import Iterator
from html import escape
from pathlib import Path

from app.repositories import visual_repository
from app.repositories.transcription_repository import TranscriptNotReadyError
from app.services import visual_service

DOCUMENT_STYLE = """
body{margin:0;background:#f4f7fb;color:#192e4b;font-family:system-ui,sans-serif}
main{max-width:860px;margin:32px auto;padding:clamp(20px,5vw,48px);background:white;border-radius:12px}
h1{overflow-wrap:anywhere;font-size:1.8rem}header{border-bottom:1px solid #dce2e9;margin-bottom:28px}
section{margin:24px 0;border-bottom:1px solid #e1e7ef;padding-bottom:20px}
img{display:block;max-width:100%;height:auto;border:1px solid #dce2e9;border-radius:8px}
p{line-height:1.85;overflow-wrap:anywhere}time,.muted{color:#53677f;font-size:.85rem}
time{font-variant-numeric:tabular-nums}p time{display:block}
@media print{body{background:white}main{margin:0;padding:0}img{break-inside:avoid}}
"""


def timestamp(milliseconds: int) -> str:
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1000)
    return f'{hours:02}:{minutes:02}:{seconds:02}.{millis:03}'


def render_document(transcript: dict, images: dict[int, Path], timestamps: bool) -> Iterator[bytes]:
    """Escape all uploaded text; encode one image chunk at a time, never the MP4."""
    title = escape(transcript['filename'])
    yield (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" '
        'content="default-src \'none\'; img-src data:; style-src \'unsafe-inline\'">'
        f'<title>{title} — Visual Transcript</title><style>{DOCUMENT_STYLE}</style>'
        f'</head><body><main><header><h1>{title}</h1><p>Visual Transcript</p></header>'
    ).encode('utf-8')
    if not transcript['sections']:
        yield b'<p>No speech or distinct visual content was detected.</p>'
    for index, section in enumerate(transcript['sections'], start=1):
        yield b'<section>'
        visual = section['visual']
        if visual:
            if timestamps:
                yield (f'<p><time>{timestamp(visual["start_ms"])} &ndash; '
                       f'{timestamp(visual["end_ms"])}</time></p>').encode()
            yield f'<img alt="Extracted visual {index}" src="data:image/jpeg;base64,'.encode()
            # A multiple of three keeps independently encoded chunks valid base64.
            with images[visual['id']].open('rb') as image:
                while chunk := image.read(48 * 1024):
                    yield base64.b64encode(chunk)
            yield b'">'
        segments = section['segments']
        if timestamps:
            for segment in segments:
                text = escape(' '.join(segment['text'].split()))
                yield f'<p><time>{timestamp(segment["start_ms"])}</time>{text}</p>'.encode('utf-8')
        elif segments:
            text = escape(' '.join(' '.join(segment['text'].split()) for segment in segments))
            yield f'<p>{text}</p>'.encode('utf-8')
        if visual and not segments:
            yield b'<p class="muted">No speech during this visual.</p>'
        yield b'</section>'
    yield b'</main></body></html>'


def prepare_download(file_id: int, timestamps: bool = False) -> tuple[str, Iterator[bytes]]:
    transcript = visual_service.get_visual_transcript(file_id)
    if transcript['status'] != 'completed' or transcript['speech_status'] != 'completed':
        raise TranscriptNotReadyError(
            transcript['status'], transcript['current_step'] or 'queued', transcript['error_message'],
        )
    # Validate all images before sending headers, so missing/unsafe files return
    # a clear HTTP error rather than a silently incomplete downloadable document.
    images = {
        frame['id']: visual_service.resolve_image_path(frame['image_path'])
        for frame in visual_repository.frames(file_id)
    }
    return transcript['filename'], render_document(transcript, images, timestamps)
