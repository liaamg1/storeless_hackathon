"""Lightweight, fully local speaker labelling for transcript segments.

Strictly read-only on audio and text: it only reads slices of the finished WAV
using the transcriber's timestamps and returns labels. It is never an input to
the transcriber.

No new dependencies or model downloads (NumPy already ships with faster-whisper):
each segment's audio becomes a duration-invariant acoustic voice print combining
fundamental frequency (pitch F0), spectral centroid, glottal spectral tilt, and
normalized low-order vocal-tract MFCC medians. Features are scaled against a
calibrated single-speaker variation reference (rather than z-scoring across
segments) so a single speaker is never split into fake speakers. It never raises.
"""
import logging
import wave
from dataclasses import replace
from pathlib import Path

import numpy as np

from app.processors.speech_recognizer import TranscriptSegment, TranscriptionResult

logger = logging.getLogger(__name__)

FALLBACK_SPEAKER = "Speaker"
SAMPLE_RATE = 16000
FRAME, HOP, FFT = 400, 160, 512
MEL_BANDS, MFCC_COUNT = 26, 7  # c1..c6 capture vocal-tract shape rather than vowel phonemes
MAX_SEGMENT_SECONDS = 8      # a few seconds already characterise a voice
MIN_WINDOW_SECONDS = 1.0     # shorter segments are padded into adjacent silence only
MIN_VOICED_FRAMES = 12       # ~0.14 s of speech so brief turns still get a voice print
MIN_SILHOUETTE = 0.35        # conservative threshold so 1-speaker speech stays unified
MIN_CENTER_DISTANCE = 2.1    # minimum separation in calibrated single-speaker units
SILHOUETTE_SAMPLE = 800

# Calibrated within-speaker variation per feature:
# [median_semitones, log_centroid, spectral_tilt, c1, c2, c3, c4, c5, c6]
_SINGLE_SPEAKER_SCALE = np.array([
    2.2, 0.35, 0.70, 0.40, 0.35, 1.5, 1.5, 1.5, 1.5,
])
_LAG_WEIGHTS = 1.0 - 0.0015 * np.arange(35, 230)


def _mel_filterbank() -> np.ndarray:
    def to_mel(hz): return 2595 * np.log10(1 + hz / 700)
    def to_hz(mel): return 700 * (10 ** (mel / 2595) - 1)
    points = to_hz(np.linspace(to_mel(80), to_mel(SAMPLE_RATE / 2 - 400), MEL_BANDS + 2))
    bins = np.floor((FFT + 1) * points / SAMPLE_RATE).astype(int)
    bank = np.zeros((MEL_BANDS, FFT // 2 + 1))
    for band in range(MEL_BANDS):
        left, centre, right = bins[band], bins[band + 1], bins[band + 2]
        for k in range(left, centre):
            bank[band, k] = (k - left) / max(1, centre - left)
        for k in range(centre, right):
            bank[band, k] = (right - k) / max(1, right - centre)
    row_sums = bank.sum(axis=1, keepdims=True)
    return bank / np.maximum(row_sums, 1e-10)


_BANK = _mel_filterbank()
_WINDOW = np.hamming(FRAME)
_DCT = np.cos(np.pi / MEL_BANDS * (np.arange(MEL_BANDS) + 0.5)[None, :] * np.arange(1, MFCC_COUNT)[:, None]) / MEL_BANDS
_FREQS = np.linspace(0.0, SAMPLE_RATE / 2.0, FFT // 2 + 1)
_SUBBAND_BINS = [(3, 8), (8, 26), (26, 70), (70, 128), (128, 240)]


def voice_print(samples: np.ndarray) -> np.ndarray | None:
    """Duration-invariant pitch, spectral tilt, and normalized MFCC median voice print."""
    if len(samples) < FRAME + HOP * (MIN_VOICED_FRAMES - 1):
        return None
    if float(np.max(samples ** 2)) < 1e-7:
        return None
    count = 1 + (len(samples) - FRAME) // HOP
    index = np.arange(FRAME)[None, :] + HOP * np.arange(count)[:, None]
    frames = samples[index] * _WINDOW
    energy = np.log(np.sum(frames ** 2, axis=1) + 1e-10)
    threshold = max(float(np.percentile(energy, 35)), float(energy.max()) - 8.0)
    voiced = frames[energy >= threshold]
    if len(voiced) < MIN_VOICED_FRAMES:
        return None

    # Normalize frame RMS so microphone distance does not skew spectral shape.
    rms = np.sqrt(np.mean(voiced ** 2, axis=1, keepdims=True)) + 1e-8
    norm_voiced = voiced / rms

    # 1. Pitch (F0) via subharmonic-weighted FFT autocorrelation across lags 35..229.
    acf = np.fft.irfft(np.abs(np.fft.rfft(norm_voiced, n=1024)) ** 2, n=1024)
    acf = acf / (acf[:, :1] + 1e-8)
    raw_pitch_region = acf[:, 35:230]
    weighted_region = raw_pitch_region * _LAG_WEIGHTS[None, :]
    best_idx = np.argmax(weighted_region, axis=1)
    best_lag = 35 + best_idx
    clarity = raw_pitch_region[np.arange(len(norm_voiced)), best_idx]
    voiced_f0 = SAMPLE_RATE / best_lag[clarity >= 0.35]
    if len(voiced_f0) >= max(3, len(norm_voiced) // 5):
        pitch_semitones = float(np.median(12.0 * np.log2(voiced_f0 / 100.0)))
    else:
        pitch_semitones = float("nan")

    # 2. Spectral centroid and glottal low-to-high spectral tilt.
    power = np.abs(np.fft.rfft(norm_voiced, FFT)) ** 2 + 1e-10
    centroid = np.sum(power * _FREQS[None, :], axis=1) / np.sum(power, axis=1)
    log_centroid = float(np.median(np.log2(np.maximum(centroid, 50.0) / 500.0)))
    band_logs = [
        float(np.median(np.log(np.mean(power[:, lo:hi], axis=1) + 1e-10)))
        for lo, hi in _SUBBAND_BINS
    ]
    spectral_tilt = (band_logs[0] + band_logs[1]) / 2.0 - (band_logs[2] + band_logs[3] + band_logs[4]) / 3.0

    # 3. Normalized vocal-tract MFCC medians (c1..c6; frame-centered log-mel).
    log_mel = np.log(power @ _BANK.T + 1e-10)
    log_mel -= np.mean(log_mel, axis=1, keepdims=True)
    mfcc = log_mel @ _DCT.T
    mfcc_median = np.median(mfcc, axis=0)

    return np.concatenate([[pitch_semitones, log_centroid, spectral_tilt], mfcc_median])


def _sq_dist(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.maximum((a ** 2).sum(1)[:, None] + (b ** 2).sum(1)[None, :] - 2 * a @ b.T, 0)


def _kmeans_single(x: np.ndarray, k: int, seed: int | None) -> tuple[np.ndarray, np.ndarray, float]:
    if seed is None:
        median = np.median(x, axis=0, keepdims=True)
        first = int(np.argmin(_sq_dist(x, median)[:, 0]))
        centers = x[[first]]
        while len(centers) < k:
            d = _sq_dist(x, centers).min(axis=1)
            if d.max() <= 0:
                break
            centers = np.vstack([centers, x[int(np.argmax(d))]])
    else:
        rng = np.random.default_rng(seed)
        centers = x[[rng.integers(len(x))]]
        while len(centers) < k:
            d = _sq_dist(x, centers).min(axis=1)
            if d.sum() <= 0:
                break
            centers = np.vstack([centers, x[rng.choice(len(x), p=d / d.sum())]])
    for _ in range(30):
        labels = _sq_dist(x, centers).argmin(axis=1)
        updated = np.array([
            x[labels == c].mean(axis=0) if np.any(labels == c) else centers[c]
            for c in range(len(centers))
        ])
        if np.allclose(updated, centers):
            break
        centers = updated
    d_sq = _sq_dist(x, centers)
    labels = d_sq.argmin(axis=1)
    inertia = float(np.sum(d_sq[np.arange(len(x)), labels]))
    return labels, centers, inertia


def _kmeans(x: np.ndarray, k: int, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    best_labels, best_centers, best_inertia = _kmeans_single(x, k, None)
    for extra_seed in (seed, seed + 1, seed + 2):
        labels, centers, inertia = _kmeans_single(x, k, extra_seed)
        if len(set(labels.tolist())) == k and (
            len(set(best_labels.tolist())) < k or inertia < best_inertia
        ):
            best_labels, best_centers, best_inertia = labels, centers, inertia
    return best_labels, best_centers


def _silhouette(x: np.ndarray, labels: np.ndarray) -> float:
    dist = np.sqrt(_sq_dist(x, x))
    non_singleton_a = [
        dist[i, labels == labels[i]].sum() / ((labels == labels[i]).sum() - 1)
        for i in range(len(x))
        if (labels == labels[i]).sum() >= 2
    ]
    singleton_a = max(float(np.mean(non_singleton_a)) if non_singleton_a else 1.2, 1.2)
    scores = []
    for i in range(len(x)):
        own = labels == labels[i]
        a = dist[i, own].sum() / (own.sum() - 1) if own.sum() >= 2 else singleton_a
        b = min(dist[i, labels == c].mean() for c in set(labels) if c != labels[i])
        scores.append((b - a) / max(a, b, 1e-12))
    return float(np.mean(scores))


def _min_center_distance(centers: np.ndarray) -> float:
    if len(centers) < 2:
        return 0.0
    dist = np.sqrt(_sq_dist(centers, centers))
    np.fill_diagonal(dist, np.inf)
    return float(np.min(dist))


def cluster_voice_prints(prints: np.ndarray, max_speakers: int) -> np.ndarray:
    """Return a cluster id per row; all zeros when no split is convincing."""
    n = len(prints)
    if n < 2 or max_speakers < 2:
        return np.zeros(n, dtype=int)
    clean = np.array(prints, dtype=float, copy=True)
    # Impute any missing pitch values with the recording's median pitch so unvoiced
    # segments never create artificial pitch jumps within a single speaker.
    for col in range(clean.shape[1]):
        mask = np.isnan(clean[:, col])
        if np.any(mask):
            valid = clean[~mask, col]
            clean[mask, col] = float(np.median(valid)) if len(valid) > 0 else 0.0

    if clean.shape[1] == len(_SINGLE_SPEAKER_SCALE):
        # Scale strictly by calibrated single-speaker variation; never z-score by
        # prints.std(axis=0), which would stretch 1-speaker jitter to unit variance.
        x = (clean - np.median(clean, axis=0)) / _SINGLE_SPEAKER_SCALE
    else:
        x = (clean - clean.mean(axis=0)) / (np.maximum(clean.std(axis=0), 1.0) + 1e-6)

    sample = x if n <= SILHOUETTE_SAMPLE else x[np.linspace(0, n - 1, SILHOUETTE_SAMPLE).astype(int)]
    max_k = min(max_speakers, len(sample) if len(sample) <= 4 else max(2, len(sample) // 2))
    best_k, best_score = 1, MIN_SILHOUETTE
    best_centers = None
    for k in range(2, max_k + 1):
        labels, centers = _kmeans(sample, k)
        if len(set(labels.tolist())) < k:
            continue
        counts = np.bincount(labels)
        if k > 2 and len(sample) >= 6 and int(counts.min()) < max(2, len(sample) // 25):
            continue
        min_sep = 2.5 if (int(counts.min()) == 1 and len(sample) >= 5) else MIN_CENTER_DISTANCE
        if _min_center_distance(centers) < min_sep:
            continue
        score = _silhouette(sample, labels)
        if score > best_score:
            best_k, best_score, best_centers = k, score, centers
    if best_k == 1 or best_centers is None:
        return np.zeros(n, dtype=int)
    return _sq_dist(x, best_centers).argmin(axis=1)


def label_speakers(audio_path: Path, segments: list[TranscriptSegment], max_speakers: int = 6) -> list[str]:
    """One label per segment, in order; "Speaker" when separation is not possible."""
    labels = [FALLBACK_SPEAKER] * len(segments)
    try:
        prints: dict[int, np.ndarray] = {}
        with wave.open(str(audio_path), 'rb') as source:
            if (source.getnchannels(), source.getsampwidth(), source.getframerate()) != (1, 2, SAMPLE_RATE):
                return labels
            total = source.getnframes()
            for i, segment in enumerate(segments):
                start = min(total, segment.start_ms * SAMPLE_RATE // 1000)
                end = min(total, segment.end_ms * SAMPLE_RATE // 1000)
                if end - start < int(MIN_WINDOW_SECONDS * SAMPLE_RATE):
                    # Pad short segments only into unclaimed gap between adjacent segments.
                    prev_end = min(total, segments[i - 1].end_ms * SAMPLE_RATE // 1000) if i > 0 else 0
                    next_start = min(total, segments[i + 1].start_ms * SAMPLE_RATE // 1000) if i + 1 < len(segments) else total
                    missing = int(MIN_WINDOW_SECONDS * SAMPLE_RATE) - (end - start)
                    start = max(prev_end, start - missing // 2)
                    end = min(next_start, end + missing - missing // 2)
                end = min(end, start + MAX_SEGMENT_SECONDS * SAMPLE_RATE)
                if end <= start:
                    continue
                source.setpos(start)
                pcm = np.frombuffer(source.readframes(end - start), dtype='<i2').astype(np.float32) / 32768.0
                vector = voice_print(pcm)
                if vector is not None:
                    prints[i] = vector
        if len(prints) < 2:
            return labels
        indices = sorted(prints)
        clusters = cluster_voice_prints(np.array([prints[i] for i in indices]), max_speakers)
        if len(set(clusters.tolist())) < 2:
            return labels
        assigned: dict[int, int] = dict(zip(indices, clusters.tolist()))
        # Number speakers by first appearance; very short segments inherit the previous voice.
        numbering: dict[int, int] = {}
        previous: int | None = None
        for i in range(len(segments)):
            cluster = assigned.get(i, previous)
            if cluster is None:  # leading short segments take the first identified voice
                cluster = assigned[indices[0]]
            numbering.setdefault(cluster, len(numbering) + 1)
            labels[i] = f"Speaker {numbering[cluster]}"
            previous = cluster
        return labels
    except Exception as exc:  # diarization is optional and must never fail a job
        logger.warning("speaker_identification_failed error_type=%s", type(exc).__name__)
        return [FALLBACK_SPEAKER] * len(segments)


def assign_speakers(audio_path: Path, result: TranscriptionResult, max_speakers: int = 6) -> TranscriptionResult:
    labels = label_speakers(audio_path, result.segments, max_speakers)
    return TranscriptionResult(result.language, [
        replace(segment, speaker=label) for segment, label in zip(result.segments, labels)
    ])
