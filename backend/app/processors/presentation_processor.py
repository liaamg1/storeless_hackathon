"""Validate and render presentations one slide at a time, keeping pixel memory bounded."""
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from collections.abc import Iterator

import pymupdf

from app.processors.slide_hash import hash_rendered_slide

# Fixed across all cached presentations; do not change without reindexing slides.
CANVAS_WIDTH, CANVAS_HEIGHT = 960, 720


class PresentationProcessingError(ValueError):
    pass


@dataclass(frozen=True)
class ExtractedSlide:
    number: int
    text: str
    image_path: Path
    thumbnail_path: Path
    content_hash: str
    perceptual_hash: str


def validate_pptx(path: Path) -> None:
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            names = {entry.filename for entry in entries}
            if not {'[Content_Types].xml', 'ppt/presentation.xml'} <= names:
                raise PresentationProcessingError('The file is not a valid PPTX presentation.')
            if len(entries) > 10000 or sum(entry.file_size for entry in entries) > 512_000_000:
                raise PresentationProcessingError('The presentation contains too much unpacked content.')
            if any(entry.filename.lower().endswith('vbaproject.bin') for entry in entries):
                raise PresentationProcessingError('Macro-enabled presentations are not supported.')
            # Reject encrypted members; LibreOffice should not wait for a password.
            if any(entry.flag_bits & 1 for entry in entries):
                raise PresentationProcessingError('Encrypted presentations are not supported.')
    except (zipfile.BadZipFile, OSError) as exc:
        raise PresentationProcessingError('The PPTX presentation is corrupted or unreadable.') from exc


def convert_pptx(path: Path, output_dir: Path, binary: str, timeout: int) -> Path:
    """An isolated profile avoids shared LibreOffice locks and user configuration."""
    validate_pptx(path)
    profile = (output_dir / 'office-profile').resolve().as_uri()
    try:
        subprocess.run([
            binary, f'-env:UserInstallation={profile}', '--headless', '--nologo',
            '--nodefault', '--norestore', '--nofirststartwizard', '--convert-to',
            'pdf:impress_pdf_Export', '--outdir', str(output_dir), str(path),
        ], capture_output=True, timeout=timeout, check=True)
    except FileNotFoundError as exc:
        raise PresentationProcessingError('LibreOffice Impress is required to process PPTX files.') from exc
    except subprocess.TimeoutExpired as exc:
        raise PresentationProcessingError('Presentation conversion exceeded its time limit.') from exc
    except subprocess.CalledProcessError as exc:
        raise PresentationProcessingError('LibreOffice could not convert this presentation.') from exc
    converted = output_dir / (path.stem + '.pdf')
    if not converted.is_file() or converted.stat().st_size == 0:
        raise PresentationProcessingError('The presentation could not be converted to PDF.')
    return converted


def extract_slides(path: Path, kind: str, output_dir: Path, *, office_binary: str = 'libreoffice',
                   timeout: int = 120, max_slides: int = 500) -> Iterator[ExtractedSlide]:
    """Render cached full images and thumbnails; never change the source file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='restore-presentation-') as temporary:
        pdf = convert_pptx(path, Path(temporary), office_binary, timeout) if kind == 'pptx' else path
        try:
            with pymupdf.open(pdf) as document:
                if not document.is_pdf or document.needs_pass or document.is_repaired:
                    raise PresentationProcessingError('Upload an intact, unencrypted presentation.')
                if not 1 <= document.page_count <= max_slides:
                    raise PresentationProcessingError(f'Presentations must contain 1–{max_slides} slides.')
                for index in range(document.page_count):
                    page = document[index]
                    text = page.get_text('text')
                    # Rasterize the visible page INCLUDING annotations/widgets.
                    # Copying only its PDF content stream would miss annotated numbers.
                    scale = min(CANVAS_WIDTH / page.rect.width, CANVAS_HEIGHT / page.rect.height)
                    rendered = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale),
                                               colorspace=pymupdf.csRGB, alpha=False, annots=True)
                    with pymupdf.open() as normalized:
                        target = normalized.new_page(width=CANVAS_WIDTH, height=CANVAS_HEIGHT)
                        width, height = rendered.width, rendered.height
                        left, top = (CANVAS_WIDTH - width) / 2, (CANVAS_HEIGHT - height) / 2
                        target.insert_image(pymupdf.Rect(left, top, left + width, top + height), pixmap=rendered)
                        full = target.get_pixmap(colorspace=pymupdf.csRGB, alpha=False)
                        gray = target.get_pixmap(matrix=pymupdf.Matrix(32 / CANVAS_WIDTH, 32 / CANVAS_HEIGHT),
                                                 colorspace=pymupdf.csGRAY, alpha=False)
                        exact, perceptual = hash_rendered_slide(full.samples, gray.samples, text)
                        image = output_dir / f'slide-{index + 1:04d}.png'
                        thumbnail = output_dir / f'slide-{index + 1:04d}-thumb.png'
                        full.save(image)
                        target.get_pixmap(matrix=pymupdf.Matrix(.5, .5), colorspace=pymupdf.csRGB,
                                          alpha=False).save(thumbnail)
                    yield ExtractedSlide(index + 1, text, image, thumbnail, exact, perceptual)
        except (pymupdf.FileDataError, pymupdf.EmptyFileError, RuntimeError) as exc:
            raise PresentationProcessingError('The presentation is corrupted or unreadable.') from exc
