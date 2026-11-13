"""Deterministic rendered-content hashes; no models, embeddings or cloud services."""
import hashlib

import numpy as np

# Low-frequency 8x8 DCT coefficients from a 32x32 grayscale render (64 bits).
_samples = np.arange(32) + .5
_basis = np.cos(np.pi / 32 * np.arange(8)[:, None] * _samples)
_basis[0] /= np.sqrt(2)


def hash_rendered_slide(rgb: bytes, grayscale: bytes, text: str) -> tuple[str, str]:
    """An exact match requires both normalized pixels and normalized text.

    Text is included to keep changed numbers/labels from becoming exact through
    rasterization. A matching perceptual hash alone NEVER establishes equality.
    The version prefix fixes the canonical canvas/hash recipe for cached results.
    """
    normalized_text = ' '.join(text.split()).encode('utf-8')
    exact = hashlib.sha256(b'restore-slide-v1\0' + rgb + b'\0' + normalized_text).hexdigest()
    pixels = np.frombuffer(grayscale, dtype=np.uint8).reshape(32, 32).astype(np.float64)
    coefficients = (_basis @ pixels @ _basis.T).ravel()
    coefficients[np.abs(coefficients) < 1e-8] = 0  # Discard DCT round-off on blank slides.
    median = np.median(coefficients[1:])  # Ignore average brightness (the DC term).
    bits = coefficients > median
    bits[0] = False
    perceptual = f'{int.from_bytes(np.packbits(bits).tobytes(), "big"):016x}'
    return exact, perceptual


def perceptual_distance(first: str, second: str) -> int:
    return (int(first, 16) ^ int(second, 16)).bit_count()
