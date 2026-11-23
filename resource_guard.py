"""Conservative, best-effort preflight for memory-heavy image processing.

Does not guarantee against operating-system OOM kills or concurrent users.
"""
from dataclasses import dataclass
from io import BytesIO
import os
import psutil
from PIL import Image, UnidentifiedImageError

# Adjustable deployment limits; deliberately conservative for free hosting.
MAX_UPLOAD_MB = int(os.getenv('MAX_UPLOAD_MB', '80'))
MAX_IMAGE_PIXELS = int(os.getenv('MAX_IMAGE_PIXELS', '12000000'))
MAX_STACK_FRAMES = int(os.getenv('MAX_STACK_FRAMES', '32'))
RESERVE_MB = int(os.getenv('MEMORY_RESERVE_MB', '160'))
# Rolling-ball, labels, masks, previews, heatmap and ZIP serialization.
ESTIMATED_BYTES_PER_PIXEL = int(os.getenv('ESTIMATED_BYTES_PER_PIXEL', '120'))

class ResourceLimitError(ValueError):
    """Expected user-facing rejection before expensive processing."""

@dataclass(frozen=True)
class ImageEstimate:
    width: int
    height: int
    frames: int
    estimated_mb: float
    available_mb: float


def _cgroup_remaining_bytes():
    """Return remaining container memory quota, if available (cgroups v1/v2)."""
    candidates = [('/sys/fs/cgroup/memory.max', '/sys/fs/cgroup/memory.current'),
                  ('/sys/fs/cgroup/memory/memory.limit_in_bytes', '/sys/fs/cgroup/memory/memory.usage_in_bytes')]
    for limit_path, used_path in candidates:
        try:
            with open(limit_path) as f: limit_text = f.read().strip()
            with open(used_path) as f: used = int(f.read().strip())
            if limit_text == 'max': continue
            limit = int(limit_text)
            if 0 < limit < (1 << 60): return max(0, limit - used)
        except (OSError, ValueError):
            continue
    return None


def preflight_image(upload_bytes: bytes) -> ImageEstimate:
    mb = 1024 * 1024
    upload_mb = len(upload_bytes) / mb
    if upload_mb > MAX_UPLOAD_MB:
        raise ResourceLimitError(f'Upload is {upload_mb:.1f} MB; this website allows at most {MAX_UPLOAD_MB} MB per file. Export a smaller image or process locally.')
    try:
        with Image.open(BytesIO(upload_bytes)) as im:
            width, height = im.size
            frames = getattr(im, 'n_frames', 1)
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ResourceLimitError('The image could not be read. Upload a valid TIFF, PNG, or JPEG.') from exc
    pixels = width * height
    if pixels > MAX_IMAGE_PIXELS:
        raise ResourceLimitError(f'Image has {pixels:,} pixels ({width} × {height}); the hosted limit is {MAX_IMAGE_PIXELS:,} pixels. Crop the tissue ROI, downsample, or run locally.')
    if frames > MAX_STACK_FRAMES:
        raise ResourceLimitError(f'Image has {frames} frames; the hosted limit is {MAX_STACK_FRAMES}. Make a maximum-intensity projection locally and upload the projection.')
    # Estimate stack decode and projection buffers, plus analysis intermediates.
    estimated = pixels * ESTIMATED_BYTES_PER_PIXEL + pixels * max(0, frames - 1) * 6 + len(upload_bytes) * 2
    cgroup = _cgroup_remaining_bytes()
    system_available = psutil.virtual_memory().available
    available = min(system_available, cgroup) if cgroup is not None else system_available
    budget = max(0, available - RESERVE_MB * mb)
    if estimated > budget:
        raise ResourceLimitError(
            f'Not enough memory available for safe processing. Image: {width} × {height}, {frames} frame(s). '
            f'Estimated additional memory: {estimated / mb:.0f} MB; currently available: {available / mb:.0f} MB '
            f'(reserving {RESERVE_MB} MB for the app). Try a cropped image, a precomputed maximum-intensity projection, '
            'or run the same pipeline locally. No analysis was performed.')
    return ImageEstimate(width, height, frames, estimated / mb, available / mb)
