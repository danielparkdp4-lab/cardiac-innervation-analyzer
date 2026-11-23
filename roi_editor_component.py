"""Drag-to-calibrate scale line and exclusion ROI (no external frontend dependencies)."""
import base64
from io import BytesIO
from pathlib import Path
from PIL import Image
import streamlit.components.v1 as components

_editor = components.declare_component('cardiac_roi_editor', path=str(Path(__file__).parent / 'roi_editor'))

def roi_editor(rgb, line, rect, key):
    image = Image.fromarray(rgb).convert('RGB')
    b = BytesIO()
    image.save(b, format='JPEG', quality=84)
    return _editor(image=base64.b64encode(b.getvalue()).decode('ascii'), width=image.width,
                   height=image.height, line=list(line), rect=list(rect), key=key, default=None)
