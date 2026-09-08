"""Task-local PDF figure reconstruction: native paths + source image insets."""
import sys,os,json,re,math,base64,copy,io,hashlib
from PIL import Image,ImageChops,ImageDraw
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import pymupdf
from lxml import etree as E
from fontTools.svgLib.path import parse_path
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.qu2cuPen import Qu2CuPen
from shapely.geometry import Polygon,LineString,box as sbox,GeometryCollection
from shapely import make_valid
IDENT=(1,0,0,1,0,0)
def mul(a,b):
 return(a[0]*b[0]+a[2]*b[1],a[1]*b[0]+a[3]*b[1],a[0]*b[2]+a[2]*b[3],a[1]*b[2]+a[3]*b[3],a[0]*b[4]+a[2]*b[5]+a[4],a[1]*b[4]+a[3]*b[5]+a[5])
def pt(m,p):return[m[0]*p[0]+m[2]*p[1]+m[4],m[1]*p[0]+m[3]*p[1]+m[5]]
def trans(s):
 m=IDENT
 for name,v in re.findall(r'(\w+)\(([^)]+)\)',s or ''):
  v=[float(x) for x in re.findall(r'[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?',v)]
  if name=='matrix':n=v
  elif name=='translate':n=(1,0,0,1,v[0],v[1] if len(v)>1 else 0)
  elif name=='scale':n=(v[0],0,0,v[1] if len(v)>1 else v[0],0,0)
  elif name=='rotate':
   a=math.radians(v[0]);n=(math.cos(a),math.sin(a),-math.sin(a),math.cos(a),0,0)
   if len(v)>2:n=mul(mul((1,0,0,1,v[1],v[2]),n),(1,0,0,1,-v[1],-v[2]))
  else:continue
  m=mul(m,n)
 return m

def path_commands(text,m):
 r=RecordingPen();parse_path(text,Qu2CuPen(r,max_err=.00001,all_cubic=True));out=[]
 for op,ps in r.value:
  if op in ('moveTo','lineTo','curveTo'):out.append([{'moveTo':'m','lineTo':'l','curveTo':'c'}[op],*[pt(m,p) for p in ps]])
  elif op=='closePath':out.append(['h'])
 return out

def bbox(cmd):
 pts=[p for c in cmd for p in c[1:]]
 return[min(p[0] for p in pts),min(p[1] for p in pts),max(p[0] for p in pts),max(p[1] for p in pts)] if pts else None

def polys(cmd):
 parts=[];cur=[];last=None
 for c in cmd:
  if c[0]=='m':
   if cur:parts.append(cur)
   cur=[c[1]];last=c[1]
  elif c[0]=='l':cur.append(c[1]);last=c[1]
  elif c[0]=='c':
   a=last;b,v,d=c[1:]
   for i in range(1,25):
    t=i/24;u=1-t;cur.append([u**3*a[k]+3*u*u*t*b[k]+3*u*t*t*v[k]+t**3*d[k] for k in [0,1]])
   last=d
  elif c[0]=='h':
   if cur and cur[-1]!=cur[0]:cur.append(cur[0])
 if cur:parts.append(cur)
 return parts

def clip_cmd(cmd,rect,fill):
 ps=polys(cmd);geom=GeometryCollection()
 if fill:
  for p in ps:
   if len(p)>2:
    try:geom=geom.symmetric_difference(make_valid(Polygon(p)))
    except:pass
 else:
  from shapely.ops import unary_union
  geom=unary_union([LineString(p) for p in ps if len(p)>1])
 geom=geom.intersection(rect if hasattr(rect,'geom_type') else sbox(*rect));out=[]
 def emit(g):
  if g.is_empty:return
  if g.geom_type=='Polygon':
   for ring in [g.exterior,*g.interiors]:
    p=list(ring.coords);out.append(['m',list(p[0])]);out.extend(['l',list(q)] for q in p[1:]);out.append(['h'])
  elif g.geom_type in ('LineString','LinearRing'):
   p=list(g.coords);out.append(['m',list(p[0])]);out.extend(['l',list(q)] for q in p[1:])
  elif hasattr(g,'geoms'):
   for v in g.geoms:emit(v)
 emit(geom);return out

def extract(job,outdir):
 outdir=Path(outdir);outdir.mkdir(parents=True,exist_ok=True)
 doc=pymupdf.open(job.get('render_source_pdf',job['pdf_path']));page=doc[job.get('render_source_page',job['page'])-1];page.set_cropbox(pymupdf.Rect(job.get('render_source_bbox',job['bbox'])))
 W,H=page.rect.width,page.rect.height;capture_scale=float(job.get('svg_capture_scale',1));svg=Path(job['render_source_svg']).read_text() if job.get('render_source_svg') else page.get_svg_image(matrix=pymupdf.Matrix(capture_scale,capture_scale),text_as_path=True);(outdir/'source.svg').write_text(svg)
 raw_xrefs={}
 for image in page.get_images(full=True):
  try:raw_xrefs[hashlib.sha256(doc.xref_stream_raw(image[0])).hexdigest()]=image[0]
  except:pass
 root=E.fromstring(svg.encode());ids={e.get('id'):e for e in root.iter() if e.get('id')};objs=[];warnings=[];raster_n=0
 shading_boxes=set();shading_doc=None
 if job.get('isolated_shadings_pdf'):
  shading_doc=pymupdf.open(job['isolated_shadings_pdf']);shading_page=shading_doc[job['page']-1];shading_page.set_cropbox(pymupdf.Rect(job['bbox']))
 def intersect(a,b):return[max(a[0],b[0]),max(a[1],b[1]),min(a[2],b[2]),min(a[3],b[3])]
 def clipshape(ref,m):
  id=re.search(r'#([^)]*)',ref or '')
  if not id or id[1] not in ids:return None
  e=ids[id[1]];result=GeometryCollection()
  for el in e.iter():
   if E.QName(el).localname in ['path','rect']:
    if E.QName(el).localname=='rect':
     x=float(el.get('x',0));y=float(el.get('y',0));w=float(el.get('width'));h=float(el.get('height'));path_d=f'M{x} {y}h{w}v{h}h{-w}Z'
    else:path_d=el.get('d')
    cmds=path_commands(path_d,mul(m,trans(el.get('transform'))));shape=GeometryCollection();contours=[p for p in polys(cmds) if len(p)>2]
    if el.get('clip-rule',e.get('clip-rule','nonzero'))=='evenodd':
     for p in contours:
      try:shape=shape.symmetric_difference(make_valid(Polygon(p)))
      except:pass
    elif len(contours)==1 and Polygon(contours[0]).is_valid:
     shape=Polygon(contours[0])
    elif contours:
     # SVG clip paths default to nonzero winding. XOR incorrectly cuts white
     # holes where a curved arrow shaft overlaps its arrowhead.
     from shapely.ops import unary_union,polygonize
     from solid_path import winding_number
     lines=[LineString(p if p[-1]==p[0] else p+[p[0]]) for p in contours]
     faces=list(polygonize(unary_union(lines)));kept=[]
     for face in faces:
      point=face.representative_point()
      if sum(winding_number((point.x,point.y),p) for p in contours):kept.append(face)
     shape=unary_union(kept)
    result=result.union(shape)
  return result if not result.is_empty else None
 def styleof(e,style):
  n=dict(style)
  for pair in(e.get('style') or '').split(';'):
   if ':' in pair:k,v=pair.split(':',1);n[k.strip()]=v.strip()
  for k in ['fill','stroke','stroke-width','fill-rule','stroke-linecap','stroke-linejoin','stroke-dasharray','fill-opacity','stroke-opacity']:
   if e.get(k) is not None:n[k]=e.get(k)
  n['opacity']=float(style.get('opacity',1))*float(e.get('opacity',1))
  for k in ['fill','stroke']:
   if n.get(k,'').startswith('rgb('):
    values=n[k][4:-1].split(',');n[k]='#'+''.join(f'{max(0,min(255,round(float(v.strip().rstrip("%"))*(2.55 if "%" in v else 1)))):02x}' for v in values)
  return n
 def addpath(e,m,style,clip,glyph=None,cg=None):
  cmd=path_commands(e.get('d',''),m);b=bbox(cmd)
  if not b:return
  visible=intersect(b,clip)
  if visible[2]<visible[0] or visible[3]<visible[1]:return
  fill=style.get('fill','#000000');stroke=style.get('stroke','none')
  if style.get('mix-blend-mode')=='multiply' and fill.lower() in ['#ffffff','#fff','white'] and stroke=='none':
   # White is the identity color under multiply, including translucent white.
   return
  if style.get('mix-blend-mode','normal')!='normal':warnings.append('nontrivial blend mode requires review '+style['mix-blend-mode'])
  gradient=None
  if fill.startswith('url('):
   gradient_id=re.search(r'#([^)]*)',fill);g=ids.get(gradient_id[1]) if gradient_id else None
   if job.get('native_linear_gradients') and g is not None and E.QName(g).localname=='linearGradient' and g.get('gradientUnits')=='userSpaceOnUse':
    gm=mul(m,trans(g.get('gradientTransform')));g1=pt(gm,[float(g.get('x1',0)),float(g.get('y1',0))]);g2=pt(gm,[float(g.get('x2',1)),float(g.get('y2',0))]);stops=[]
    if abs(g1[0]-g2[0])<.001 or abs(g1[1]-g2[1])<.001:
     for st in g:
      color=st.get('stop-color','#000000')
      if color.startswith('rgb('):color='#'+''.join(f'{max(0,min(255,round(float(v.strip().rstrip("%"))*(2.55 if "%" in v else 1)))):02x}' for v in color[4:-1].split(','))
      stops.append([float(st.get('offset',0)),color,float(st.get('stop-opacity',1))])
     gradient={'p1':g1,'p2':g2,'stops':stops}
   if gradient is None:warnings.append('gradient/path fill requires review')
   fill='#888888'
  lw=float(style.get('stroke-width',1))*(1 if glyph is not None else math.sqrt(abs(m[0]*m[3]-m[1]*m[2]))) if stroke!='none' else 0
  # Clip the painted stroke area, not merely its centerline. PDF exporters often
  # clip a thick border to the inside of its own shape (an inset border).
  if fill=='none' and stroke!='none' and lw>0 and cg is not None and style.get('stroke-dasharray','none') in ('','none') and not cg.buffer(.00001).covers(sbox(b[0]-lw*5,b[1]-lw*5,b[2]+lw*5,b[3]+lw*5)):
   from shapely.ops import unary_union
   ls=[LineString(p) for p in polys(cmd) if len(p)>1]
   if ls:
    painted=unary_union(ls).buffer(lw/2,quad_segs=24,cap_style={'round':1,'butt':2,'square':3}.get(style.get('stroke-linecap','butt'),2),join_style={'round':1,'miter':2,'bevel':3}.get(style.get('stroke-linejoin','miter'),2))
    if not cg.buffer(.00001).covers(painted):
     clipped=painted.intersection(cg);outline=[]
     def emit_stroke(g):
      if g.is_empty:return
      if g.geom_type=='Polygon':
       for ring in [g.exterior,*g.interiors]:
        points=list(ring.coords);outline.append(['m',list(points[0])]);outline.extend(['l',list(p)] for p in points[1:]);outline.append(['h'])
      elif hasattr(g,'geoms'):
       for child in g.geoms:emit_stroke(child)
     emit_stroke(clipped);bb=bbox(outline)
     if bb:
      objs.append({'kind':'path','path':outline,'bbox':bb,'fill':stroke,'stroke':'none','lineWidth':0,'fillOpacity':float(style.get('stroke-opacity',1))*style['opacity'],'strokeOpacity':1,'evenodd':True,'lineCap':'butt','lineJoin':'miter','name':'Clipped source stroke outline','source_stroke_width':lw,'source_clip_reconstructed':True})
     return
  if cg is not None and not cg.buffer(.001).covers(sbox(*b)):
   cmd=clip_cmd(cmd,cg,fill!='none');b=bbox(cmd)
   if not b:return
  ob={'kind':'path','path':cmd,'bbox':b,'fill':fill,'stroke':stroke,'lineWidth':lw,'fillOpacity':float(style.get('fill-opacity',1))*style['opacity'],'strokeOpacity':float(style.get('stroke-opacity',1))*style['opacity'],'evenodd':style.get('fill-rule')=='evenodd','lineCap':style.get('stroke-linecap','butt'),'lineJoin':style.get('stroke-linejoin','miter'),'name':('Text '+glyph if glyph else 'Vector element')}
  if gradient is not None:ob['native_gradient']=gradient
  dash=style.get('stroke-dasharray')
  if dash and dash!='none':ob['dash']=[float(x)*math.sqrt(abs(m[0]*m[3]-m[1]*m[2])) for x in re.findall(r'[\d.]+',dash)]
  if glyph is not None:ob['glyph']=glyph;ob['baseline']=[m[4],m[5]];ob['fontSize']=math.hypot(m[0],m[1])
  objs.append(ob)
 def walk(e,m,style,clip,ref=False,glyph=None,masks=(),cg=None):
  nonlocal raster_n
  tag=E.QName(e).localname
  if tag in ['defs','clipPath','mask','metadata'] and not ref:return
  m=mul(m,trans(e.get('transform')));style=styleof(e,style)
  maskref=re.search(r'#([^)]*)',e.get('mask',''))
  if maskref:masks=(*masks,maskref[1])
  c=clipshape(e.get('clip-path'),m)
  if c is not None:
   cg=cg.intersection(c) if cg is not None else c
   if cg.is_empty:return
   clip=list(cg.bounds)
  if clip[2]<=clip[0] or clip[3]<=clip[1]:return
  if tag=='use':
   target=ids.get((e.get('{http://www.w3.org/1999/xlink}href') or e.get('href','')).lstrip('#'))
   if target is not None:
    off=(1,0,0,1,float(e.get('x',0)),float(e.get('y',0)))
    walk(target,mul(m,off),style,clip,True,e.get('data-text'),masks,cg)
  elif tag=='path':addpath(e,m,style,clip,glyph,cg)
  elif tag=='rect' and style.get('fill','').startswith('url('):
   # Preserve bitmap texture fills as isolated source layers. All other figure
   # content remains native; no rendered full-figure crop is used here.
   pattern_id=re.search(r'#([^)]*)',style['fill'])[1]
   pattern=ids.get(pattern_id)
   if pattern is None or E.QName(pattern).localname!='pattern':
    warnings.append('unsupported rectangle paint '+pattern_id);return
   x=float(e.get('x',0));y=float(e.get('y',0));w=float(e.get('width'));h=float(e.get('height'))
   pp=[pt(m,p) for p in [(x,y),(x+w,y),(x,y+h),(x+w,y+h)]]
   b=intersect([min(p[0] for p in pp),min(p[1] for p in pp),max(p[0] for p in pp),max(p[1] for p in pp)],clip)
   if b[2]<=b[0] or b[3]<=b[1]:return
   # MuPDF's SVG reader does not render bitmap patterns. Resolve the original
   # tile and its transforms explicitly, retaining the texture's source pixels.
   images=[]
   def pattern_images(node,tm,seen=()):
    tm=mul(tm,trans(node.get('transform')));nt=E.QName(node).localname
    href=node.get('{http://www.w3.org/1999/xlink}href') or node.get('href','')
    if nt=='image':images.append((node,tm))
    elif nt=='use' and href.startswith('#') and href not in seen:
     target=ids.get(href[1:])
     if target is not None:pattern_images(target,mul(tm,(1,0,0,1,float(node.get('x',0)),float(node.get('y',0)))),(*seen,href))
    else:
     for child in node:pattern_images(child,tm,seen)
   pattern_images(pattern,IDENT)
   if len(images)!=1 or pattern.get('patternUnits')!='userSpaceOnUse' or pattern.get('patternContentUnits','userSpaceOnUse')!='userSpaceOnUse':
    warnings.append('unsupported bitmap pattern structure '+pattern_id);return
   import numpy as np
   ie,imatrix=images[0];href=ie.get('{http://www.w3.org/1999/xlink}href') or ie.get('href','');raw=base64.b64decode(href.split(',',1)[1]);tile=Image.open(io.BytesIO(raw)).convert('RGBA')
   def invert(tm):
    a,bb,c,d,ee,ff=tm;det=a*d-bb*c
    return(d/det,-bb/det,-c/det,a/det,(c*ff-d*ee)/det,(bb*ee-a*ff)/det)
   scale=16;ww=max(1,round((b[2]-b[0])*scale));hh=max(1,round((b[3]-b[1])*scale));yy,xx=np.mgrid[0:hh,0:ww];xx=b[0]+(xx+.5)*(b[2]-b[0])/ww;yy=b[1]+(yy+.5)*(b[3]-b[1])/hh
   inv=invert(mul(m,trans(pattern.get('patternTransform'))));u=inv[0]*xx+inv[2]*yy+inv[4];v=inv[1]*xx+inv[3]*yy+inv[5]
   pw=float(pattern.get('width'));ph=float(pattern.get('height'));u=(u-float(pattern.get('x',0)))%pw;v=(v-float(pattern.get('y',0)))%ph
   inv=invert(imatrix);ix=(inv[0]*u+inv[2]*v+inv[4]-float(ie.get('x',0)))*tile.width/float(ie.get('width'))-.5;iy=(inv[1]*u+inv[3]*v+inv[5]-float(ie.get('y',0)))*tile.height/float(ie.get('height'))-.5
   tx=np.floor(ix).astype(int);ty=np.floor(iy).astype(int);fx=(ix-tx)[...,None];fy=(iy-ty)[...,None];arr=np.asarray(tile,dtype=float)
   result=(arr[ty%tile.height,tx%tile.width]*(1-fx)*(1-fy)+arr[ty%tile.height,(tx+1)%tile.width]*fx*(1-fy)+arr[(ty+1)%tile.height,tx%tile.width]*(1-fx)*fy+arr[(ty+1)%tile.height,(tx+1)%tile.width]*fx*fy)
   im=Image.fromarray(np.clip(np.round(result),0,255).astype('uint8'),'RGBA')
   if cg is not None:
    alpha=Image.new('L',im.size,0);draw=ImageDraw.Draw(alpha)
    def draw_pattern_clip(g):
     if g.is_empty:return
     if g.geom_type=='Polygon':
      draw.polygon([((x-b[0])*ww/(b[2]-b[0]),(y-b[1])*hh/(b[3]-b[1])) for x,y in g.exterior.coords],fill=255)
      for hole in g.interiors:draw.polygon([((x-b[0])*ww/(b[2]-b[0]),(y-b[1])*hh/(b[3]-b[1])) for x,y in hole.coords],fill=0)
     elif hasattr(g,'geoms'):
      for sub in g.geoms:draw_pattern_clip(sub)
    draw_pattern_clip(cg);im.putalpha(ImageChops.multiply(im.getchannel('A'),alpha))
   raster_n+=1;f=outdir/f'inset-{raster_n}.png';im.save(f)
   objs.append({'kind':'image','bbox':b,'file':str(f.resolve()),'name':'Original bitmap pattern layer '+pattern_id,'asset_origin':'isolated embedded PDF bitmap texture pattern','source_pattern_id':pattern_id,'source_image_sha256':hashlib.sha256(raw).hexdigest(),'alpha_coverage':sum(im.getchannel('A').getdata())/(255*im.width*im.height)})
  elif tag=='rect':
   x=float(e.get('x',0));y=float(e.get('y',0));w=float(e.get('width'));h=float(e.get('height'));path_el=E.Element('path',d=f'M{x} {y}h{w}v{h}h{-w}Z');addpath(path_el,m,style,clip,glyph,cg)
  elif tag=='image' and not e.get('id') and shading_doc is not None:
   x=float(e.get('x',0));y=float(e.get('y',0));w=float(e.get('width'));h=float(e.get('height'));pp=[pt(m,p) for p in [(x,y),(x+w,y),(x,y+h),(x+w,y+h)]];b=intersect([min(p[0] for p in pp),min(p[1] for p in pp),max(p[0] for p in pp),max(p[1] for p in pp)],clip)
   key=tuple(round(v,4) for v in b)
   if key in shading_boxes or b[2]<=b[0] or b[3]<=b[1]:return
   shading_boxes.add(key);pix=shading_page.get_pixmap(matrix=pymupdf.Matrix(16,16),clip=pymupdf.Rect(b),alpha=True);im=Image.open(io.BytesIO(pix.tobytes('png'))).convert('RGBA')
   raster_n+=1;f=outdir/f'inset-{raster_n}.png';im.save(f)
   objs.append({'kind':'image','bbox':b,'file':str(f.resolve()),'name':'Isolated original PDF gradient asset','asset_origin':'original PDF shading operations only, with text and ordinary path painting removed from isolated copy','shading_pdf_sha256':hashlib.sha256(Path(job['isolated_shadings_pdf']).read_bytes()).hexdigest(),'alpha_coverage':sum(im.getchannel('A').getdata())/(255*im.width*im.height)})
  elif tag=='image':
   x=float(e.get('x',0));y=float(e.get('y',0));w=float(e.get('width'));h=float(e.get('height'));pp=[pt(m,p) for p in [(x,y),(x+w,y),(x,y+h),(x+w,y+h)]];b=[min(p[0] for p in pp),min(p[1] for p in pp),max(p[0] for p in pp),max(p[1] for p in pp)];b=intersect(b,clip)
   if b[2]-b[0]<.1 or b[3]-b[1]<.1:return
   raster_n+=1;f=outdir/f'inset-{raster_n}.png'
   href=e.get('{http://www.w3.org/1999/xlink}href') or e.get('href','');raw=base64.b64decode(href.split(',',1)[1]);im=Image.open(io.BytesIO(raw))
   if im.mode=='CMYK':
    xref=raw_xrefs.get(hashlib.sha256(raw).hexdigest())
    if not xref:
     # MuPDF may re-encode CMYK JPEGs in SVG. Resolve a unique page-local
     # image by dimensions and color space before applying its PDF profile.
     matches=[a[0] for a in page.get_images(full=True) if tuple(a[2:4])==im.size and a[5]=='DeviceCMYK']
     if len(matches)==1:
      xref=matches[0];raw_xrefs[hashlib.sha256(raw).hexdigest()]=xref
    if xref:
     pix=pymupdf.Pixmap(doc,xref)
     if pix.colorspace.n>3:pix=pymupdf.Pixmap(pymupdf.csRGB,pix)
     im=Image.open(io.BytesIO(pix.tobytes('png')))
    else:
     im=Image.merge('CMYK',[ImageChops.invert(ch) for ch in im.split()]);warnings.append('CMYK fallback inversion reviewed separately')
   im=im.convert('RGBA')
   def find_mask_image(node,seen=None):
    seen=set() if seen is None else seen
    if node is None:return None
    if node in seen:return None
    seen.add(node);href=node.get('{http://www.w3.org/1999/xlink}href') or node.get('href','')
    if E.QName(node).localname=='image' and href.startswith('data:'):return node
    if href.startswith('#'):
     found=find_mask_image(ids.get(href[1:]),seen)
     if found is not None:return found
    for child in node:
     found=find_mask_image(child,seen)
     if found is not None:return found
    return None
   for maskid in masks:
    if maskid in job.get('flattened_uniform_image_masks',[]):continue
    mask=ids.get(maskid);mi=find_mask_image(mask)
    if mi is not None:
     mh=mi.get('{http://www.w3.org/1999/xlink}href') or mi.get('href','');mm=Image.open(io.BytesIO(base64.b64decode(mh.split(',',1)[1]))).convert('RGBA')
     target=mask
     use=next((z for z in mask.iter() if E.QName(z).localname=='use'),None)
     if use is not None:target=ids.get((use.get('{http://www.w3.org/1999/xlink}href') or '').lstrip('#'),mask)
     white=any(E.QName(n).localname=='rect' and n.get('fill') in ['white','#ffffff','#fff'] for n in target.iter())
     bg=Image.new('RGBA',mm.size,(255,255,255,255) if white else (0,0,0,255));mm=Image.alpha_composite(bg,mm).convert('L').resize(im.size,Image.Resampling.LANCZOS);im.putalpha(ImageChops.multiply(im.getchannel('A'),mm))
    else:warnings.append('image mask requires review '+maskid)
   # PDF soft masks may declare a Matte: stored RGB has already been blended.
   # Undo that blend before applying the alpha, or transparent white planes turn grey.
   source_xref=raw_xrefs.get(hashlib.sha256(raw).hexdigest())
   if source_xref:
    sm_type,sm_value=doc.xref_get_key(source_xref,'SMask')
    if sm_type=='xref':
     mt,mv=doc.xref_get_key(int(sm_value.split()[0]),'Matte')
     if mt=='array':
      matte=[float(v) for v in re.findall(r'[-+]?[0-9]*\.?[0-9]+',mv)]
      if len(matte) in [1,3]:
       import numpy as np
       arr=np.array(im,dtype=np.float32);alpha=arr[:,:,3:4]/255.;bg=np.array(matte*3 if len(matte)==1 else matte,dtype=np.float32).reshape((1,1,3))*255
       arr[:,:,:3]=np.where(alpha>0,(arr[:,:,:3]-(1-alpha)*bg)/np.maximum(alpha,1/255),0)
       im=Image.fromarray(np.clip(np.round(arr),0,255).astype('uint8'),'RGBA')
   if style['opacity']<.999:im.putalpha(im.getchannel('A').point(lambda v:round(v*style['opacity'])))
   # Native source bytes are transformed only for placement and rectangular clipping.
   # Never crop the rendered whole figure to stand in for an image asset.
   a,bb,c,dd,ee,ff=m;det=a*dd-bb*c;scale=max(4,min(16,max(im.width/(w*max(math.hypot(a,bb),1e-9)),im.height/(h*max(math.hypot(c,dd),1e-9)))))
   if abs(det)<1e-12:return
   coeff=(dd/det/scale,-c/det/scale,(dd*(b[0]-ee)-c*(b[1]-ff))/det-x,-bb/det/scale,a/det/scale,(-bb*(b[0]-ee)+a*(b[1]-ff))/det-y)
   im=im.transform((max(1,round((b[2]-b[0])*scale)),max(1,round((b[3]-b[1])*scale))),Image.Transform.AFFINE,coeff,Image.Resampling.BICUBIC)
   if cg is not None and not cg.buffer(.001).covers(sbox(*b)):
    alpha=Image.new('L',im.size,0);draw=ImageDraw.Draw(alpha)
    def drawclip(g):
     if g.is_empty:return
     if g.geom_type=='Polygon':
      draw.polygon([((x-b[0])*scale,(y-b[1])*scale) for x,y in g.exterior.coords],fill=255)
      for hole in g.interiors:draw.polygon([((x-b[0])*scale,(y-b[1])*scale) for x,y in hole.coords],fill=0)
     elif hasattr(g,'geoms'):
      for sub in g.geoms:drawclip(sub)
    drawclip(cg);im.putalpha(ImageChops.multiply(im.getchannel('A'),alpha))
   if hashlib.sha256(raw).hexdigest() in job.get('opaque_white_image_assets',[]):
    white=Image.new('RGBA',im.size,(255,255,255,255));white.alpha_composite(im);im=white
   im.save(f)
   objs.append({'kind':'image','bbox':b,'file':str(f.resolve()),'name':'Original source image asset','source_image_sha256':hashlib.sha256(raw).hexdigest(),'asset_origin':'embedded PDF image','alpha_coverage':sum(im.getchannel('A').getdata())/(255*im.width*im.height)})
  elif tag in ['g','svg','a']:
   for child in e:walk(child,m,style,clip,masks=masks,cg=cg)
  elif tag not in ['title','desc']:warnings.append('unhandled SVG element '+tag)
 walk(root,(1/capture_scale,0,0,1/capture_scale,0,0),{'fill':'#000000','stroke':'none','opacity':1},[0,0,W,H],cg=sbox(0,0,W,H))
 if job.get('restore_transmitted_rays'):
  # A bounded correction for the source's uniform 0.7 image mask: retain the
  # color-managed scene artwork and restore the rays transmitted through it.
  spec=job['restore_transmitted_rays'];ix=spec['image_index'];asset=objs[ix];assert asset['kind']=='image'
  im=Image.open(asset['file']).convert('RGBA');alpha=im.getchannel('A');bb=asset['bbox'];rays=[]
  for index in spec['path_indices']:
   ray=copy.deepcopy(objs[index]);assert ray['kind']=='path' and len(ray['path'])==2 and ray['stroke']==spec['source_stroke']
   start,end=ray['path'][0][1],ray['path'][1][1];inside=[]
   for i in range(2001):
    t=i/2000;x=start[0]+t*(end[0]-start[0]);y=start[1]+t*(end[1]-start[1]);px=int((x-bb[0])*im.width/(bb[2]-bb[0]));py=int((y-bb[1])*im.height/(bb[3]-bb[1]))
    if 0<=px<im.width and 0<=py<im.height and alpha.getpixel((px,py))>128:inside.append((x,y))
   if inside:
    ray['path']=[['m',list(inside[0])],['l',list(inside[-1])]];ray['bbox']=bbox(ray['path']);ray['strokeOpacity']*=spec['transmission'];ray['name']='Native ray transmitted through source scene';rays.append(ray)
  objs[ix+1:ix+1]=rays
 if shading_doc is not None and job.get('opaque_white_shading_assets'):
  # Office interpolates transparent black edge pixels into a dark halo. Group
  # intersecting gradient parts and flatten each independent asset onto white.
  pending=[(i,o) for i,o in enumerate(objs) if o.get('shading_pdf_sha256')];groups=[]
  while pending:
   group=[pending.pop(0)];changed=True
   while changed:
    changed=False
    for item in pending[:]:
     if any(sbox(*item[1]['bbox']).buffer(.05).intersects(sbox(*other[1]['bbox'])) for other in group):group.append(item);pending.remove(item);changed=True
   groups.append(group)
  replaced={};removed=set()
  for gi,group in enumerate(groups):
   bounds=[min(o['bbox'][0] for _,o in group),min(o['bbox'][1] for _,o in group),max(o['bbox'][2] for _,o in group),max(o['bbox'][3] for _,o in group)]
   pix=shading_page.get_pixmap(matrix=pymupdf.Matrix(16,16),clip=pymupdf.Rect(bounds),alpha=False);f=outdir/f'gradient-group-{gi+1}.png';pix.save(f)
   first=min(i for i,_ in group);ob=dict(group[0][1],bbox=bounds,file=str(f.resolve()),alpha_coverage=1,gradient_components=len(group),name='Independent original gradient group on white');replaced[first]=ob;removed.update(i for i,_ in group if i!=first)
  remaining=[o for i,o in enumerate(objs) if i not in removed and i not in replaced]
  insertion=0
  while insertion<len(remaining) and remaining[insertion].get('fill')=='#ffffff' and remaining[insertion]['bbox'][2]-remaining[insertion]['bbox'][0]>W*.9:insertion+=1
  objs=remaining[:insertion]+list(replaced.values())+remaining[insertion:];raster_n=sum(o['kind']=='image' for o in objs)
 # Combine sequential glyphs into editable vector labels; preserve glyph holes as compound paths.
 merged=[]
 for o in objs:
  if o.get('glyph') is not None and merged and merged[-1].get('glyph') is not None:
   a=merged[-1]
   if abs(a['baseline'][1]-o['baseline'][1])<.2 and all(a.get(k)==o.get(k) for k in ['fill','stroke','fillOpacity','strokeOpacity','lineWidth','lineCap','lineJoin','dash','evenodd']) and abs(a['fontSize']-o['fontSize'])<.1 and -.2<o['bbox'][0]-a['bbox'][2]<o['fontSize']*1.5:
    a['path']+=o['path'];a['bbox']=[min(a['bbox'][0],o['bbox'][0]),min(a['bbox'][1],o['bbox'][1]),max(a['bbox'][2],o['bbox'][2]),max(a['bbox'][3],o['bbox'][3])];a['glyph']+=o['glyph'];a['name']='Text '+a['glyph'];continue
  merged.append(o)
 if job.get('restore_llm2clip_gradient_border'):
  assert job['id']=='AI-082' and merged[2].get('native_gradient') and merged[3]['stroke']=='#0f9ed5'
  merged[2]['bbox']=copy.deepcopy(merged[3]['bbox']);merged[2]['path']=copy.deepcopy(merged[3]['path']);merged[2]['name']='Native blue gradient following exact source rounded border'
 result={'id':job['id'],'width':W,'height':H,'objects':merged,'warnings':sorted(set(warnings)),'meta':job,'native_text_count':0,'vector_label_count':sum('glyph'in o for o in merged),'image_count':raster_n,'image_area_ratio':sum((o['bbox'][2]-o['bbox'][0])*(o['bbox'][3]-o['bbox'][1]) for o in merged if o['kind']=='image')/(W*H)}
 (outdir/'figure.json').write_text(json.dumps(result,ensure_ascii=False))
 if job.get('render_source_pdf'):
  rd=pymupdf.open(job['pdf_path']);rp=rd[job['page']-1];rp.set_cropbox(pymupdf.Rect(job['bbox']));rp.get_pixmap(matrix=pymupdf.Matrix(2000/max(rp.rect.width,rp.rect.height),2000/max(rp.rect.width,rp.rect.height)),alpha=False).save(outdir/'reference.png')
 else:page.get_pixmap(matrix=pymupdf.Matrix(2000/max(W,H),2000/max(W,H)),alpha=False).save(outdir/'reference.png')
 return result
if __name__=='__main__':
 jobs=json.load(open(sys.argv[1]));wanted=set(sys.argv[3:])
 for j in jobs:
  if wanted and j['id'] not in wanted:continue
  out=Path(sys.argv[2])/j['id'];r=extract(j,out);print(j['id'],len(r['objects']),'objects',r['image_count'],'images',r['warnings'],flush=True)
