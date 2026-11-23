# Cardiac innervation analysis V7.8 — pilot website

## Run locally or deploy on Streamlit Community Cloud

1. Install requirements: `pip install -r requirements.txt`
2. Run: `streamlit run app.py`
3. For Streamlit Community Cloud, upload all files including `roi_editor_component.py` and the `roi_editor/` directory to a GitHub repository and set the app entry point to `app.py`.

## Validated analysis baseline (unchanged)

- ImageJ-style rolling-ball background radius: 50 pixels; Gaussian blur sigma: 1 pixel.
- OpenCV Otsu threshold **offset 0** by default. The website retains an adjustable **-20 to +20** offset slider.
- RGB lab TIFFs: analyze the manually selected red/green/blue channel as 8-bit data. **Confirm the correct channel visually** using the red/green/blue previews. Tests 1–5 used red; Tests 6–10 used green. No automatic channel guessing is performed.
- 16-bit grayscale TIFFs: fixed `value // 256` conversion by default; native 16-bit processing remains experimental.
- Full image ROI by default; no object-area filtering beyond 1 pixel.
- Provisional calibration: 200 µm / 242 pixels. Verify calibration for each acquisition.
- Size categories: small equivalent circular diameter ≤5 µm; medium >5 and <20 µm; large ≥20 µm. **These are connected-component area-equivalent diameters, not measured fiber widths.**

## Downloads and reproducibility

The result ZIP includes `summary.csv` (all adjustable settings and measurements), `analysis_settings.json` (complete run settings), `individual_objects.csv`, analysis-input TIFF, and the original/processed/segmented/classification/heatmap PNGs. Settings are recorded with each export; they are not automatically standardized across separate runs.

## Validation and limits

Across ten user-provided validation images, V7.8 density results agreed with the user's ImageJ area fractions with approximately 0.036 percentage points mean absolute error (rounded measurements). This supports a **pilot deployment**, not proof that segmented pixels represent ground-truth nerve staining. Before using nerve-size classes for scientific conclusions, validate calibration, segmentation, and connected-component size categories independently.

This release changes **website usability and export metadata only**. It does not modify the validated `analysis.py` or rolling-ball processing code.

## Interactive calibration and exclusion editor (drag-and-drop)

The website now contains an embedded image editor with two independently movable tools:

- **Cyan line (calibration):** select **Draw scale line**, drag across the visible scale bar to measure its pixel length, move the line by dragging its center, or resize it by dragging either endpoint. Enter the scale bar's real-world length (µm) in the sidebar. The measured line length replaces the former manually entered pixel-width setting.
- **Orange rectangle (exclusion):** select **Draw exclusion rectangle**, drag to draw a new exclusion region, drag inside the region to move it, or drag its corners to resize. Enable the **Exclude scale bar / annotation rectangle** checkbox to actually remove these pixels from the segmentation and analyzed-area denominator. When unchecked, the rectangle is a preview only.

The image is displayed at a responsive size, but all tool coordinates are stored in original-image pixels. After a drag is released, Streamlit reruns the analysis with the new calibration or exclusion. The line and rectangle are independently adjustable; moving the cyan line does not automatically move the orange rectangle. Verify that the rectangle covers the bar and label but avoids tissue where possible. The editor is implemented locally in `roi_editor/index.html` and requires no external JavaScript CDN.

**Scientific note:** dragging the calibration line can change the small/medium/large densities because the object-size thresholds are in µm; it should not change the total density unless you also change the excluded ROI. Compare to prior results only when calibration and ROI match.

## Free Streamlit deployment (resource-guard edition)

This release adds `resource_guard.py`, which checks the uploaded file size, image dimensions, frame count and estimated memory consumption **before decoding or running the analysis**. It shows a readable rejection if the image exceeds conservative limits. The processing algorithms in `analysis.py` and `rolling_ball_imagej.py` are unchanged. The guard is best-effort; a host can still terminate the app under memory pressure (e.g. concurrent users).

Defaults: 80 MB maximum uploaded file, 12 million pixels, 32 frames, 160 MB free-memory reserve, estimated 120 bytes/pixel plus stack and upload overhead. Configure these using `MAX_UPLOAD_MB`, `MAX_IMAGE_PIXELS`, `MAX_STACK_FRAMES`, `MEMORY_RESERVE_MB`, and `ESTIMATED_BYTES_PER_PIXEL` environment variables. **Do not increase these limits without memory testing.**

Deploy: create a GitHub repository, put the files from this folder at the **root** of the repository, and choose `app.py` as the entrypoint at https://share.streamlit.io. `requirements.txt` installs the dependencies. For local testing, run `python -m pip install -r requirements.txt` then `python -m streamlit run app.py`. Verify outputs against known ImageJ references before research use. Avoid uploading confidential microscopy data to publicly hosted applications without lab approval.

### Final classification colors
Small = cyan (RGB 0,255,255); Medium = magenta (RGB 255,0,255); Large = yellow (RGB 255,255,0). This is a visualization-only change and does not alter any computed density.
