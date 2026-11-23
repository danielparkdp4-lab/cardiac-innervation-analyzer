"""Streamlit UI for ImageJ-style cardiac innervation quantification."""
from io import BytesIO
import json
from pathlib import Path
import zipfile
import numpy as np
import pandas as pd
import streamlit as st
from PIL import Image
from analysis import load_image, analyze
from resource_guard import preflight_image, ResourceLimitError
from roi_editor_component import roi_editor
import hashlib

st.set_page_config(page_title='Cardiac innervation | ImageJ workflow',layout='wide')
st.title('Cardiac innervation quantification — V7.8 (pilot)')
st.caption('Max projection → ImageJ-aligned rolling-ball subtraction → Gaussian σ=1 px → Otsu (dark background) → area fractions')
st.info('RGB lab TIFFs: extracts the chosen fluorescence channel as a reproducible 8-bit grayscale analysis image. Original 16-bit MIPs: fixed value // 256 conversion. RGB exports cannot be converted back into the original 16-bit MIP; no artificial image shift or density correction is applied.')
with st.sidebar:
    precision_mode=st.selectbox('16-bit image processing', ['Validated legacy 8-bit conversion','Experimental native 16-bit'],help='RGB inputs always use the unchanged 8-bit pipeline. Native 16-bit processing is experimental and not yet validated against ImageJ end-to-end.')
    st.subheader('Fluorescence channel')
    channel=st.selectbox('Fluorescence channel to analyze', ['red','green','blue','grayscale'],help='Choose the channel containing the nerve stain. Earlier validation used red for Tests 1–5 and green for Tests 6–10. Confirm visually for every new TIFF.')
    st.caption('Channel selection is manual to prevent an automatic guess from silently changing the assay.')
    radius=st.number_input('Background subtraction radius (px)',min_value=1,max_value=500,value=50)
    sigma=st.number_input('Gaussian blur σ (px)',min_value=0.1,max_value=10.,value=1.,step=0.1)
    threshold_offset=st.slider('Otsu threshold offset (intensity levels)',min_value=-20,max_value=20,value=0,step=1,help='0 = standard Otsu (validated V7.8 default). Adjust for controlled comparisons only; any change is saved with the results.')
    small=st.number_input('Small diameter maximum (µm)',min_value=.1,value=5.)
    large=st.number_input('Large diameter minimum (µm)',min_value=.2,value=20.)
    bar_um=st.number_input('Scale-bar label (µm)',min_value=.01,value=200.)
    st.caption('Scale-bar width is measured by dragging the cyan line on the image below.')
    exclude=st.number_input('Bottom annotation strip to exclude (pixels)',min_value=0,value=0)
    exclude_scale=st.checkbox('Exclude scale bar / annotation rectangle',value=False,help='Enable to exclude only the scale-bar rectangle, including its label. Disabled by default to preserve V7.8 validation measurements.')
    min_area=st.number_input('Minimum segmented object area (pixels)',min_value=1,value=1)
    st.caption('For closest ImageJ area fraction, use min object area = 1. This counts all thresholded pixels. Verify the correct ROI.')
file=st.file_uploader('Upload TIFF stack or microscopy image',type=['tif','tiff','png','jpg','jpeg'])
if file:
    try:
        upload_bytes=file.getvalue()
        estimate=preflight_image(upload_bytes)
        st.caption(f'Resource check passed: {estimate.width} × {estimate.height}, {estimate.frames} frame(s); estimated additional RAM {estimate.estimated_mb:.0f} MB.')
        rgb,plane,metadata=load_image(upload_bytes,channel,return_metadata=True,preserve_16bit=precision_mode=='Experimental native 16-bit')
        st.caption(f"Input: {metadata['input_processing']} | {metadata['frames']} frame(s) | {metadata['projection']} projection")
        if metadata['original_mode'] in ('RGB','RGBA','P'):
            st.subheader('Verify your staining channel')
            channel_previews=np.asarray(Image.open(BytesIO(upload_bytes)).convert('RGB'))
            preview_cols=st.columns(3)
            for preview_col, idx, label in zip(preview_cols, range(3), ('Red','Green','Blue')):
                preview_col.image(channel_previews[:,:,idx],caption=label+' channel',clamp=True,use_container_width=True)
            st.info(f'Analyzing the **{channel}** channel. Check the previews above: choose the channel with the nerve signal, not the background or scale bar.')
        if 'RGB' in metadata['input_processing']:
            st.warning('This is an RGB lab export, not an original 16-bit MIP. Analysis uses the selected 8-bit channel directly; the original 16-bit intensities cannot be recovered. For ImageJ comparisons, open the exported analysis_input_8bit.tif in ImageJ and apply the same settings.')
        st.image(plane if plane.dtype==np.uint8 else (plane>>8).astype(np.uint8), caption='Grayscale preview (native 16-bit values retained internally when selected)', use_container_width=False)
        if plane.dtype==np.uint16: st.warning('Experimental native 16-bit: results are not yet validated against ImageJ end-to-end. Legacy 8-bit mode remains the recommended baseline.')
        if exclude>=plane.shape[0]: st.error('Annotation exclusion is too large.');st.stop()
        h,w=plane.shape
        image_id=hashlib.sha256(upload_bytes).hexdigest()[:12]
        state_key='roi_editor_'+image_id
        if state_key not in st.session_state:
            st.session_state[state_key]={'line':[max(0,w-310),max(0,h-80),max(0,w-68),max(0,h-80)],
                                         'rect':[max(0,w-350),max(0,h-110),w,h]}
        st.subheader('Interactive scale calibration and annotation exclusion')
        st.write('**Cyan line:** drag the endpoints to match the actual scale bar, or drag the middle to move it. **Orange rectangle:** drag it over the scale bar and its text; drag corners to resize. Choose the drawing mode above the image to redraw either shape.')
        st.caption('The cyan line measures pixel length; it does not remove any pixels. Only the orange rectangle is excluded, and only when the exclusion checkbox is enabled.')
        previous=st.session_state[state_key]
        edited=roi_editor(rgb,previous['line'],previous['rect'],key='editor_'+image_id)
        if edited is not None and all(k in edited for k in ('line','rect')):
            previous={'line':edited['line'],'rect':edited['rect']}
            st.session_state[state_key]=previous
        line=previous['line']
        measured_px=float(np.hypot(line[2]-line[0],line[3]-line[1]))
        if measured_px<1:
            st.error('Scale calibration line must be at least 1 pixel long. Drag its endpoints to the two ends of the scale bar.')
            st.stop()
        bar_px=measured_px
        st.info(f'Scale line: **{bar_px:.2f} px** = **{bar_um:g} µm**; calibration: **{bar_um/bar_px:.5f} µm/px**.')
        raw_rect=previous['rect']
        x0,y0,x1,y1=[int(round(v)) for v in raw_rect]
        x0=max(0,min(x0,w-1));x1=max(x0+1,min(x1,w))
        y0=max(0,min(y0,h-1));y1=max(y0+1,min(y1,h))
        rect=(x0,y0,x1,y1) if exclude_scale else None
        if exclude_scale:
            st.info(f'Excluding rectangle x={x0}–{x1}, y={y0}–{y1} ({(x1-x0)*(y1-y0):,} pixels). These pixels are excluded from both the numerator and denominator.')
        else:
            st.caption('Orange rectangle is a preview only; exclusion is currently OFF.')

        r=analyze(plane,rgb,um_per_px=bar_um/bar_px,radius=radius,sigma=sigma,small_um=small,large_um=large,exclude_bottom=exclude,min_object_px=min_area,threshold_offset=threshold_offset,exclude_rect=rect)
        st.info(f'Otsu threshold: {r["threshold"]:.0f}; applied threshold: {r["effective_threshold"]:.0f}. Analyzed pixels: {r["valid_pixels"]:,}.')
        cols=st.columns(4)
        for col,name in zip(cols,['Small','Medium','Large','Total']): col.metric(name+' density',f'{r["densities"][name]:.3f}%')
        ims=[('Original',rgb),('Background-subtracted',r['corrected']),('Otsu segmentation',r['mask']),('Analyzed ROI (white included)',r['roi_mask']),('Size categories: cyan / magenta / yellow',r['categories']),('Local density heatmap',r['heatmap'])]
        for col,(name,im) in zip(st.columns(2),ims[:2]): col.image(im,caption=name,use_container_width=True)
        for col,(name,im) in zip(st.columns(2),ims[2:]): col.image(im,caption=name,use_container_width=True)
        st.caption('Class sizes are equivalent circular diameters derived from connected-component area, not directly measured nerve width.')
        summary=pd.DataFrame([{'pipeline_version':'V7.8-pilot','fluorescence_channel':channel,'image':file.name,'precision_mode':r['precision_mode'],'input_processing':metadata['input_processing'],'original_mode':metadata['original_mode'],'frames':metadata['frames'],'projection':metadata['projection'],'otsu_threshold':r['threshold'],'threshold_offset':threshold_offset,'effective_threshold':r['effective_threshold'],'background_radius_px':radius,'gaussian_sigma_px':sigma,'scale_bar_um':bar_um,'scale_bar_px':bar_px,'scale_line_xyxy':str(line),'scale_um_per_px':bar_um/bar_px,'small_max_equivalent_diameter_um':small,'large_min_equivalent_diameter_um':large,'min_object_area_px':min_area,'excluded_bottom_px':exclude,'scale_bar_rectangle_enabled':exclude_scale,'excluded_rectangle_xyxy':str(rect),'small_density_percent':r['densities']['Small'],'medium_density_percent':r['densities']['Medium'],'large_density_percent':r['densities']['Large'],'total_density_percent':r['densities']['Total'],'object_count':len(r['objects'])}])
        st.dataframe(summary,hide_index=True)
        settings={'pipeline_version':'V7.8-pilot','image':file.name,'channel':channel,'precision_mode':r['precision_mode'],'input_processing':metadata['input_processing'],'frames':metadata['frames'],'projection':metadata['projection'],'rolling_ball_radius_px':radius,'gaussian_sigma_px':sigma,'otsu_threshold':float(r['threshold']),'otsu_offset':int(threshold_offset),'applied_threshold':float(r['effective_threshold']),'scale_bar_um':bar_um,'scale_bar_px':bar_px,'scale_line_xyxy':str(line),'um_per_px':bar_um/bar_px,'small_max_equivalent_diameter_um':small,'large_min_equivalent_diameter_um':large,'min_object_area_px':min_area,'excluded_bottom_px':exclude,'scale_bar_rectangle_enabled':exclude_scale,'excluded_rectangle_xyxy':str(rect),'classification_note':'Connected-component equivalent circular diameter, not measured nerve fiber width','density_note':'Percentage of valid ROI pixels in segmented connected objects'}
        buffer=BytesIO()
        with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as z:
            tiff_bytes=BytesIO();Image.fromarray(plane).save(tiff_bytes,format='TIFF');z.writestr('analysis_input_16bit.tif' if plane.dtype==np.uint16 else 'analysis_input_8bit.tif',tiff_bytes.getvalue())
            z.writestr('summary.csv',summary.to_csv(index=False))
            z.writestr('analysis_settings.json',json.dumps(settings,indent=2))
            z.writestr('individual_objects.csv',r['objects'].to_csv(index=False))
            for name,im in ims:
                b=BytesIO();Image.fromarray(im).save(b,format='PNG');z.writestr(name.lower().replace(' ','_').replace('/','_')+'.png',b.getvalue())
        st.download_button('Download results ZIP',buffer.getvalue(),file_name='imagej_style_innervation_results.zip',mime='application/zip')
    except ResourceLimitError as e:
        st.error(f'Image cannot be processed safely on this server: {e}')
        st.info('Your file was not analyzed. For the original resolution, run the same app locally with `streamlit run app.py`.')
    except MemoryError:
        st.error('The server ran out of memory while processing this image. Try a smaller image or run locally.')
    except Exception as e:
        st.error('Analysis failed. Please verify the image and settings, or contact the app maintainer.')
        with st.expander('Technical error details'):
            st.exception(e)
