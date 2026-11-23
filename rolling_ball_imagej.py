"""ImageJ 1.x BackgroundSubtracter rolling-ball port (dark background, presmooth on).
Based on https://github.com/imagej/ImageJ/blob/master/ij/plugin/filter/BackgroundSubtracter.java
Includes ImageJ separable 3-pixel mean, block-min shrink, trimmed spherical patch,
rollBall scan, and bilinear edge extrapolation. Requires numba.
"""
import numpy as np
from numba import njit

@njit(cache=True)
def _mean3(src):
    h,w=src.shape
    a=src.copy()
    for y in range(h):
        v3=a[y,0];v2=v3
        for x in range(w):
            v1=v2;v2=v3
            if x<w-1:v3=a[y,x+1]
            a[y,x]=np.float32((v1+v2+v3)*np.float32(1/3))
    for x in range(w):
        v3=a[0,x];v2=v3
        for y in range(h):
            v1=v2;v2=v3
            if y<h-1:v3=a[y+1,x]
            a[y,x]=np.float32((v1+v2+v3)*np.float32(1/3))
    return a

@njit(cache=True)
def _shrink_min(a,fac):
    h,w=a.shape
    sh=(h+fac-1)//fac;sw=(w+fac-1)//fac
    out=np.empty((sh,sw),np.float32)
    for y in range(sh):
        for x in range(sw):
            v=np.float32(3.4028235e38)
            for yy in range(y*fac,min((y+1)*fac,h)):
                for xx in range(x*fac,min((x+1)*fac,w)):
                    if a[yy,xx]<v:v=a[yy,xx]
            out[y,x]=v
    return out

@njit(cache=True)
def _roll(a, ball):
    h,w=a.shape
    bw=ball.shape[0];r=bw//2
    out=a.copy()
    cache=np.zeros((bw,w),np.float32)
    neg=np.float32(-3.4028235e38)
    for y in range(-r,h+r):
        nextline=y+r
        if nextline<h:
            cache[nextline%bw,:]=out[nextline,:]
            out[nextline,:]=neg
        y0=max(0,y-r);yend=min(h-1,y+r)
        for x in range(-r,w+r):
            x0=max(0,x-r);xend=min(w-1,x+r)
            z=np.float32(3.4028235e38)
            for yp in range(y0,yend+1):
                by=yp-y+r
                for xp in range(x0,xend+1):
                    bx=xp-x+r
                    v=cache[yp%bw,xp]-ball[by,bx]
                    if v<z:z=v
            for yp in range(y0,yend+1):
                by=yp-y+r
                for xp in range(x0,xend+1):
                    bx=xp-x+r
                    v=z+ball[by,bx]
                    if out[yp,xp]<v:out[yp,xp]=v
    return out

@njit(cache=True)
def _enlarge(s,h,w,f):
    sh,sw=s.shape
    out=np.empty((h,w),np.float32)
    for y in range(h):
        # Java int division truncates toward zero, not floor for negatives
        iy=int((y-f//2)/f)
        if iy>=sh-1:iy=sh-2
        wy=np.float32(1.0-((y+0.5)/f-(iy+0.5)))
        for x in range(w):
            ix=int((x-f//2)/f)
            if ix>=sw-1:ix=sw-2
            wx=np.float32(1.0-((x+0.5)/f-(ix+0.5)))
            a=s[iy,ix]*wx+s[iy,ix+1]*(np.float32(1)-wx)
            b=s[iy+1,ix]*wx+s[iy+1,ix+1]*(np.float32(1)-wx)
            out[y,x]=a*wy+b*(np.float32(1)-wy)
    return out

def background_imagej(plane, radius=50, presmooth=True):
    if radius<=0:raise ValueError('radius must be positive')
    a=np.asarray(plane,dtype=np.float32)
    h,w=a.shape
    if radius<=10:fac,trim=1,24
    elif radius<=30:fac,trim=2,24
    elif radius<=100:fac,trim=4,32
    else:fac,trim=8,40
    smallrad=max(1.,float(radius)/fac)
    xtrim=int(trim*smallrad)/100 # Java integer cast occurs before division
    half=int(np.floor(smallrad-xtrim+0.5))
    coords=np.arange(-half,half+1,dtype=np.float64)
    sq=smallrad**2-coords[:,None]**2-coords[None,:]**2
    ball=np.sqrt(np.maximum(sq,0)).astype(np.float32)
    smooth=_mean3(a) if presmooth else a.copy()
    reduced=_shrink_min(smooth,fac) if fac>1 else smooth
    bg_small=_roll(reduced,ball)
    return _enlarge(bg_small,h,w,fac) if fac>1 else bg_small

def subtract_imagej(plane,radius=50,presmooth=True):
    bg=background_imagej(plane,radius,presmooth)
    # ByteProcessor conversion rounds to nearest integer with +0.5 and clips
    return np.clip(np.asarray(plane,dtype=np.float32)-bg+np.float32(.5),0,255).astype(np.uint8)
