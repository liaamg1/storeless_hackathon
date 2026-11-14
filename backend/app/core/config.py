"""Environment-based settings, resolved independently of the working directory."""

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BACKEND_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    database_url: str
    upload_dir: Path
    max_upload_bytes: int


def get_settings() -> Settings:
    upload_dir = Path(os.getenv("UPLOAD_DIR", str(BACKEND_DIR / "uploads")))
    if not upload_dir.is_absolute():
        upload_dir = BACKEND_DIR / upload_dir
    max_bytes = int(os.getenv("MAX_UPLOAD_BYTES", "25000000"))
    if max_bytes <= 0:
        raise ValueError("MAX_UPLOAD_BYTES must be positive")
    return Settings(os.getenv("DATABASE_URL", ""), upload_dir.resolve(), max_bytes)


@dataclass(frozen=True)
class TranscriptionSettings:
    max_video_bytes: int
    ffmpeg: str
    ffprobe: str
    media_timeout: int
    model_name: str
    device: str
    compute_type: str
    language: str | None
    download_root: str
    chunk_seconds: int
    cpu_threads: int


def get_transcription_settings() -> TranscriptionSettings:
    max_bytes = int(os.getenv("MAX_VIDEO_UPLOAD_BYTES", "3000000000"))
    timeout = int(os.getenv("MEDIA_TIMEOUT_SECONDS", "3600"))
    if max_bytes <= 0 or timeout <= 0:
        raise ValueError("Video upload limit and media timeout must be positive")
    chunk_seconds = int(os.getenv("WHISPER_CHUNK_SECONDS", "60"))
    cpu_threads = int(os.getenv("WHISPER_CPU_THREADS", "2"))
    if not 1 <= chunk_seconds <= 120 or cpu_threads < 1:
        raise ValueError("WHISPER_CHUNK_SECONDS must be 1–120 and WHISPER_CPU_THREADS must be positive")
    model_dir = Path(os.getenv("WHISPER_DOWNLOAD_ROOT", str(BACKEND_DIR / ".cache/whisper")))
    if not model_dir.is_absolute():
        model_dir = BACKEND_DIR / model_dir
    language = os.getenv("WHISPER_LANGUAGE", "").strip()
    return TranscriptionSettings(
        max_video_bytes=max_bytes,
        ffmpeg=resolve_media_binary("ffmpeg"),
        ffprobe=resolve_media_binary("ffprobe"),
        media_timeout=timeout,
        model_name=os.getenv("WHISPER_MODEL", "small"),
        device=os.getenv("WHISPER_DEVICE", "cpu"),
        compute_type=os.getenv("WHISPER_COMPUTE_TYPE", "int8"),
        language=None if language in ("", "auto") else language,
        download_root=str(model_dir.resolve()),
        chunk_seconds=chunk_seconds,
        cpu_threads=cpu_threads,
    )


def resolve_media_binary(name: str) -> str:
    """Use configured/system tools, then executables installed beside this Python."""
    return (
        os.getenv(f"{name.upper()}_BINARY") or shutil.which(name) or str(Path(sys.executable).with_name(name))
    )


@dataclass(frozen=True)
class WorkerSettings:
    transcription: int
    document: int
    visual: int


def get_worker_settings() -> WorkerSettings:
    def count(name: str, default: int) -> int:
        value = int(os.getenv(name, str(default)))
        if not 1 <= value <= 8:
            raise ValueError(f"{name} must be between 1 and 8")
        return value

    return WorkerSettings(
        count('TRANSCRIPTION_WORKERS', 1), count('DOCUMENT_WORKERS', 2), count('VISUAL_WORKERS', 1)
    )
