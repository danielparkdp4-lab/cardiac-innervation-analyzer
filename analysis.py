"""ImageJ-style projected nerve area fraction; ImageJ source-aligned rolling-ball background subtraction.
Not an exact ImageJ reproduction: ImageJ's smoothing/downsampling algorithm and its radius,
image channel, ROI, and data type must match to obtain identical values.
"""
from io import BytesIO
import cv2, numpy as np, pandas as pd
from rolling_ball_imagej import subtract_imagej, background_imagej
from PIL import Image, ImageSequence

def load_image(file_or_path, channel='red', return_metadata=False, preserve_16bit=False):
    """Load original 8-bit RGB lab exports or original 16-bit grayscale MIPs.

    A 16-bit grayscale TIFF is converted by fixed unsigned 16-to-8 bit scaling
    (pixel >> 8), matching the conversion used in the Test 4 MIP validation.
    This deliberately does NOT auto-contrast each image independently.
    """
    im = Image.open(BytesIO(file_or_path) if isinstance(file_or_path, bytes) else file_or_path)
    planes = []
    rgb_planes = []
    kinds = []
    for frame in ImageSequence.Iterator(im):
        raw = np.asarray(frame)
        if raw.ndim == 2 and np.issubdtype(raw.dtype, np.unsignedinteger) and raw.dtype.itemsize == 2:
            # Pillow returns native or big-endian unsigned 16-bit arrays.
            plane = raw.astype(np.uint16).copy() if preserve_16bit else (raw.astype(np.uint16) >> 8).astype(np.uint8)
            rgb_frame = np.repeat((plane >> 8 if plane.dtype==np.uint16 else plane)[:, :, None], 3, axis=2)
            kinds.append('16-bit grayscale TIFF → native 16-bit' if preserve_16bit else '16-bit grayscale TIFF → fixed 8-bit (value // 256)')
        elif raw.ndim == 2:
            plane = np.asarray(frame.convert('L'), dtype=np.uint8)
            rgb_frame = np.repeat(plane[:, :, None], 3, axis=2)
            kinds.append('8-bit grayscale')
        else:
            rgb_frame = np.asarray(frame.convert('RGB'), dtype=np.uint8)
            if channel == 'red': plane = rgb_frame[:, :, 0]
            elif channel == 'green': plane = rgb_frame[:, :, 1]
            elif channel == 'blue': plane = rgb_frame[:, :, 2]
            else: plane = cv2.cvtColor(rgb_frame, cv2.COLOR_RGB2GRAY)
            kinds.append('RGB → ' + channel + ' channel')
        planes.append(plane)
        rgb_planes.append(rgb_frame)
    if not planes: raise ValueError('No image frames found')
    if len({p.shape for p in planes}) != 1: raise ValueError('All stack frames must have the same dimensions')
    projected = np.maximum.reduce(planes)
    # Preview should represent the actual projected intensities used in analysis.
    preview = np.repeat((projected >> 8 if projected.dtype==np.uint16 else projected)[:, :, None], 3, axis=2) if kinds[0].startswith(('16-bit', '8-bit')) else np.maximum.reduce(rgb_planes)
    meta = {'input_processing': kinds[0], 'frames': len(planes), 'original_mode': im.mode,
            'original_dtype': str(np.asarray(im).dtype), 'projection': 'maximum' if len(planes)>1 else 'single frame'}
    return (preview, projected, meta) if return_metadata else (preview, projected)

def analyze(plane, rgb, um_per_px=200/242, radius=50, sigma=1.0, small_um=5.0, large_um=20.0,
            exclude_bottom=0, min_object_px=1, threshold_offset=0, exclude_rect=None):
    if large_um<=small_um: raise ValueError('Large cutoff must exceed small cutoff')
    h,w=plane.shape
    # Native 16-bit experimental path: no irreversible >>8 intensity quantization.
    # OpenCV 16-bit Otsu is NOT guaranteed identical to ImageJ's histogram method.
    native16=plane.dtype==np.uint16
    if native16:
        bg=background_imagej(plane,radius=int(radius),presmooth=True)
        corrected=np.clip(plane.astype(np.float32)-bg,0,65535).astype(np.float32)
        blurred=cv2.GaussianBlur(corrected,(0,0),sigmaX=sigma,sigmaY=sigma)
    else:
        corrected=subtract_imagej(plane,radius=int(radius),presmooth=True)
        blurred=cv2.GaussianBlur(corrected,(0,0),sigmaX=sigma,sigmaY=sigma)
    roi=np.ones((h,w),dtype=bool)
    if exclude_bottom: roi[-int(exclude_bottom):,:]=False
    if exclude_rect is not None:
        x0,y0,x1,y1=map(int,exclude_rect)
        if not (0<=x0<x1<=w and 0<=y0<y1<=h):
            raise ValueError("Scale-bar exclusion rectangle must be inside the image and have positive dimensions")
        roi[y0:y1,x0:x1]=False
    if not roi.any(): raise ValueError("No pixels remain after ROI exclusion")
    # Exclude annotation from threshold estimation too, not only final mask.
    valid=blurred[roi]
    otsu_input=np.clip(np.rint(valid),0,65535).astype(np.uint16) if native16 else valid.astype(np.uint8)
    threshold,_=cv2.threshold(otsu_input.reshape(-1,1),0,65535 if native16 else 255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)
    effective_threshold=float(threshold)+float(threshold_offset)
    binary=(blurred>effective_threshold)&roi
    n, labels, stats, centroids=cv2.connectedComponentsWithStats(binary.astype('uint8'),8)
    areas=stats[1:,cv2.CC_STAT_AREA]
    keep=np.zeros(n,dtype=bool);keep[1:]=areas>=min_object_px
    label_ids=np.flatnonzero(keep)
    diam=2*np.sqrt(stats[label_ids,cv2.CC_STAT_AREA]*(um_per_px**2)/np.pi)
    classes=np.where(diam<=small_um,'Small',np.where(diam<large_um,'Medium','Large'))
    # RGB visualization only: cyan / magenta / yellow. No effect on segmentation or densities.
    palette={'Small':(0,255,255),'Medium':(255,0,255),'Large':(255,255,0)}
    lut=np.zeros((n,3),dtype=np.uint8)
    for k in palette: lut[label_ids[classes==k]]=palette[k]
    class_img=lut[labels]
    class_img[~roi]=0
    selected=keep[labels]
    mask=(selected.astype(np.uint8)*255)
    valid_px=int(roi.sum())
    results={k:100*int(stats[label_ids[classes==k],cv2.CC_STAT_AREA].sum())/valid_px for k in palette}
    results['Total']=100*int(mask.sum()//255)/valid_px
    records=pd.DataFrame({'object_id':label_ids,'area_px':stats[label_ids,cv2.CC_STAT_AREA],
                          'area_um2':stats[label_ids,cv2.CC_STAT_AREA]*um_per_px**2,
                          'equivalent_diameter_um':diam,'category':classes,
                          'center_x_px':centroids[label_ids,0], 'center_y_px':centroids[label_ids,1]})
    # Local density heatmap is a visualization; it does not change measured area fractions.
    density=cv2.GaussianBlur(selected.astype('float32'),(0,0),sigmaX=24,sigmaY=24)
    t=np.clip((density-.02)/.28,0,1)
    colored=cv2.applyColorMap((t*255).astype('uint8'),cv2.COLORMAP_TURBO)
    colored=cv2.cvtColor(colored,cv2.COLOR_BGR2RGB)
    colored[t==0]=0;colored[~roi]=0
    return {'rgb':rgb,'corrected':corrected,'blurred':blurred,'mask':mask,'categories':class_img,
            'heatmap':colored,'threshold':threshold,'effective_threshold':effective_threshold,'threshold_offset':threshold_offset,'densities':results,'objects':records,
            'roi_mask':roi.astype(np.uint8)*255,'valid_pixels':valid_px,'segmented_pixels':int(np.count_nonzero(mask)),'precision_mode':'native_16bit_experimental' if native16 else 'legacy_8bit'}
