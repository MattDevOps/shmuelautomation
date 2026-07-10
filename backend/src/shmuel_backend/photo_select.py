"""Pick visually distinct photos for a property's share pack.

Yad2 galleries routinely contain near-duplicates: the same shot re-exported
at a different size/quality, or trivially retouched. Posting those side by
side in a collage looks careless, so we hash every candidate with a 64-bit
difference hash (dHash) and greedily pick the most mutually distinct set,
always anchoring on the lead (first) photo.

Pure Pillow, no extra dependencies: dHash is just "grayscale, shrink to 9x8,
compare each pixel to its right neighbour".
"""
from __future__ import annotations

from PIL import Image

# Two photos within this Hamming distance (out of 64 bits) are treated as the
# same shot. Re-encodes and brightness tweaks land at or below it; distinct
# rooms (even similar ones) land well above. Kept tight on purpose: dropping
# a real photo hurts more than keeping a borderline duplicate.
NEAR_DUPLICATE_BITS = 4


def dhash(image: Image.Image) -> int:
    """64-bit difference hash of `image`.

    Grayscale, resize to 9x8 (LANCZOS), then emit one bit per horizontally
    adjacent pixel pair: 1 when the left pixel is brighter than the right.
    """
    small = image.convert("L").resize((9, 8), Image.LANCZOS)
    px = small.load()
    bits = 0
    for row in range(8):
        for col in range(8):
            bits = (bits << 1) | (1 if px[col, row] > px[col + 1, row] else 0)
    return bits


def hamming(a: int, b: int) -> int:
    """Number of differing bits between two hashes."""
    return (a ^ b).bit_count()


def select_diverse(
    images: list[Image.Image],
    k: int,
    *,
    near_dup_bits: int = NEAR_DUPLICATE_BITS,
) -> list[int]:
    """Indices of up to `k` mutually distinct images, lead photo first.

    Greedy max-min: anchor on index 0 (the lead photo), then repeatedly add
    the candidate whose minimum Hamming distance to the picked set is largest.
    Candidates within `near_dup_bits` of any picked image are near-duplicates
    and never picked, so the result may be shorter than `k`.
    """
    if not images or k <= 0:
        return []
    hashes = [dhash(img) for img in images]
    picked = [0]
    while len(picked) < k:
        best_idx: int | None = None
        best_score = -1
        for i, h in enumerate(hashes):
            if i in picked:
                continue
            dist = min(hamming(h, hashes[j]) for j in picked)
            if dist <= near_dup_bits:
                continue  # near-duplicate of something already picked
            if dist > best_score:
                best_score = dist
                best_idx = i
        if best_idx is None:
            break  # everything left duplicates a picked photo
        picked.append(best_idx)
    return picked
