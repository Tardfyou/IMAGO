"""Resolve nonzero-winding overlaps before PowerPoint's even-odd custom fill."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
from shapely.geometry import LineString,Polygon
from shapely.ops import unary_union,polygonize
from winding import split_contours,poly

def winding_number(p,points):
 x,y=p;n=0
 for a,b in zip(points,points[1:]+points[:1]):
  cross=(b[0]-a[0])*(y-a[1])-(x-a[0])*(b[1]-a[1])
  if a[1]<=y:
   if b[1]>y and cross>0:n+=1
  elif b[1]<=y and cross<0:n-=1
 return n

def solid_nonzero(path):
 contours=[poly(c) for c in split_contours(path)];contours=[p for p in contours if len(p)>2]
 if not contours:return path
 polygons=[Polygon(p) for p in contours]
 needs=any(not p.is_valid for p in polygons)
 if not needs:
  for i,a in enumerate(polygons):
   for b in polygons[i+1:]:
    if a.intersects(b) and not (a.contains(b) or b.contains(a)) and a.intersection(b).area>1e-8:needs=True;break
   if needs:break
 # Normally nested font contours already agree with even-odd; retain their exact Beziers.
 if not needs:return path
 lines=[LineString(p+[p[0]]) for p in contours];faces=list(polygonize(unary_union(lines)));kept=[];different=False
 for f in faces:
  p=f.representative_point();wn=sum(winding_number((p.x,p.y),c) for c in contours)
  if wn:kept.append(f)
  if wn and abs(wn)%2==0:different=True
 if not different:return path
 result=unary_union(kept);out=[]
 def emit(g):
  if g.is_empty:return
  if g.geom_type=='Polygon':
   for ring in [g.exterior,*g.interiors]:
    pp=list(ring.coords);out.append(['m',list(pp[0])]);out.extend(['l',list(p)] for p in pp[1:]);out.append(['h'])
  elif hasattr(g,'geoms'):
   for sub in g.geoms:emit(sub)
 emit(result);return out or path
