# Cardiac innervation analysis V7.8 — pilot website

## Run locally or deploy on Streamlit Community Cloud

1. Install requirements: `pip install -r requirements.txt`
2. Run: `streamlit run app.py`
3. For Streamlit Community Cloud, upload `app.py`, `analysis.py`, `rolling_ball_imagej.py`, and `requirements.txt` to a GitHub repository and set the app entry point to `app.py`.

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

## Scale-bar exclusion (new optional setting)
Enable **Exclude scale bar / annotation rectangle** and enter the left X, top Y, right X, bottom Y coordinates (pixels, origin at upper left). Check the red rectangle preview before running. The entire rectangle is excluded from Otsu histogram estimation, object detection, and the analyzed-area denominator. The original image remains unchanged, and the exported analyzed ROI mask documents exactly what was measured. The rectangle and enabled status are recorded in the CSV and JSON. This option defaults **off** so the prior V7.8 results remain reproducible. Use the same ROI in ImageJ when validating new values. The pre-existing optional bottom-strip exclusion is also available.

## Free Streamlit deployment (resource-guard edition)

This release adds `resource_guard.py`, which checks the uploaded file size, image dimensions, frame count and estimated memory consumption **before decoding or running the analysis**. It shows a readable rejection if the image exceeds conservative limits. The processing algorithms in `analysis.py` and `rolling_ball_imagej.py` are unchanged. The guard is best-effort; a host can still terminate the app under memory pressure (e.g. concurrent users).

Defaults: 80 MB maximum uploaded file, 12 million pixels, 32 frames, 160 MB free-memory reserve, estimated 120 bytes/pixel plus stack and upload overhead. Configure these using `MAX_UPLOAD_MB`, `MAX_IMAGE_PIXELS`, `MAX_STACK_FRAMES`, `MEMORY_RESERVE_MB`, and `ESTIMATED_BYTES_PER_PIXEL` environment variables. **Do not increase these limits without memory testing.**

Deploy: create a GitHub repository, put the files from this folder at the **root** of the repository, and choose `app.py` as the entrypoint at https://share.streamlit.io. `requirements.txt` installs the dependencies. For local testing, run `python -m pip install -r requirements.txt` then `python -m streamlit run app.py`. Verify outputs against known ImageJ references before research use. Avoid uploading confidential microscopy data to publicly hosted applications without lab approval.

### Final classification colors
Small = cyan (RGB 0,255,255); Medium = magenta (RGB 255,0,255); Large = yellow (RGB 255,255,0). This is a visualization-only change and does not alter any computed density.
