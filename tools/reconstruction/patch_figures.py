import json,zipfile,sys,hashlib
from pathlib import Path
from lxml import etree as E
from winding import nonzero
from solid_path import solid_nonzero
N={'p':'http://schemas.openxmlformats.org/presentationml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main'};q=lambda k:'{'+N['a']+'}'+k
for folder in sys.argv[1:]:
 b=Path(folder);d=json.load(open(b/'figure.json'));S=3*9525
 with zipfile.ZipFile(b/'draft.pptx') as z:parts={n:z.read(n) for n in z.namelist()}
 r=E.fromstring(parts['ppt/slides/slide1.xml'])
 for sp in r.findall('.//p:sp',N):
  c=sp.find('p:nvSpPr/p:cNvPr',N)
  if not c.get('name','').startswith('Figure element '):continue
  i=int(c.get('name').split()[-1]);o=d['objects'][i];c.set('name',o['name'][:200]);x,y,xr,yb=o['bbox']
  pl=sp.find('p:spPr/a:custGeom/a:pathLst',N);pl.clear();pa=E.SubElement(pl,q('path'),w=str(max(1,round((xr-x)*S))),h=str(max(1,round((yb-y)*S))))
  if o['fill']=='none':pa.set('fill','none')
  for cmd in (nonzero(o['path']) if o.get('evenodd') else (solid_nonzero(o['path']) if o['fill']!='none' else o['path'])):
   el=E.SubElement(pa,q({'m':'moveTo','l':'lnTo','c':'cubicBezTo','h':'close'}[cmd[0]]))
   for p in cmd[1:]:E.SubElement(el,q('pt'),x=str(round((p[0]-x)*S)),y=str(round((p[1]-y)*S)))
  if o.get('native_gradient'):
   grad=o['native_gradient'];axis=1 if abs(grad['p1'][0]-grad['p2'][0])<.001 else 0;lo=o['bbox'][axis];hi=o['bbox'][axis+2];g0=grad['p1'][axis];g1=grad['p2'][axis];stops=grad['stops']
   def color_at(t):
    if t<=stops[0][0]:return stops[0][1:]
    if t>=stops[-1][0]:return stops[-1][1:]
    for a,b in zip(stops,stops[1:]):
     if a[0]<=t<=b[0]:
      w=(t-a[0])/(b[0]-a[0] or 1);rgb='#'+''.join(f'{round(int(a[1][k:k+2],16)*(1-w)+int(b[1][k:k+2],16)*w):02x}'for k in [1,3,5]);return[rgb,a[2]*(1-w)+b[2]*w]
   ts=sorted(set([0.,1.]+[(g0+(g1-g0)*t-lo)/(hi-lo)for t,_,_ in stops if lo<g0+(g1-g0)*t<hi]))
   pr=sp.find('p:spPr',N)
   for e in list(pr):
    if E.QName(e).localname in ['solidFill','noFill','gradFill']:pr.remove(e)
   gf=E.SubElement(pr,q('gradFill'),rotWithShape='1');gl=E.SubElement(gf,q('gsLst'))
   for t in ts:
    color,alpha=color_at((lo+t*(hi-lo)-g0)/(g1-g0));gs=E.SubElement(gl,q('gs'),pos=str(round(t*100000)));cl=E.SubElement(gs,q('srgbClr'),val=color.lstrip('#'));E.SubElement(cl,q('alpha'),val=str(round(alpha*o.get('fillOpacity',1)*100000)))
   E.SubElement(gf,q('lin'),ang=str(5400000 if axis else 0),scaled='1')
  ln=sp.find('p:spPr/a:ln',N)
  if ln is not None:
   ln.set('cap',{'butt':'flat','round':'rnd','square':'sq'}.get(o['lineCap'],'flat'))
   if o.get('dash') and o['lineWidth']>0:
    for el in list(ln):
     if E.QName(el).localname in ['prstDash','custDash']:ln.remove(el)
    dash=E.SubElement(ln,q('custDash'));v=o['dash'];v=v if len(v)%2==0 else v*2
    for a,c in zip(v[0::2],v[1::2]):E.SubElement(dash,q('ds'),d=str(round(a/o['lineWidth']*100000)),sp=str(round(c/o['lineWidth']*100000)))
   for j in ['round','miter','bevel']:
    if o['lineJoin']==j:E.SubElement(ln,q(j))
  for expr,alpha in [('p:spPr/a:solidFill/*',o['fillOpacity']),('p:spPr/a:ln/a:solidFill/*',o['strokeOpacity'])]:
   if alpha<.999:
    color=sp.find(expr,N)
    if color is not None:E.SubElement(color,q('alpha'),val=str(round(alpha*100000)))
 fixes=json.load(open(Path(__file__).parent/'line_repairs.json'))
 fix=fixes.get(d['id'])
 if fix and hashlib.sha256(Path(d['meta']['pdf_path']).read_bytes()).hexdigest()==fix['source_sha256']:
  tree=r.find('p:cSld/p:spTree',N);sp=E.SubElement(tree,'{'+N['p']+'}sp');nv=E.SubElement(sp,'{'+N['p']+'}nvSpPr');nid=max(int(x.get('id')) for x in r.findall('.//p:cNvPr',N))+1
  E.SubElement(nv,'{'+N['p']+'}cNvPr',id=str(nid),name=fix['reason']);E.SubElement(nv,'{'+N['p']+'}cNvSpPr');E.SubElement(nv,'{'+N['p']+'}nvPr');pr=E.SubElement(sp,'{'+N['p']+'}spPr');xf=E.SubElement(pr,q('xfrm'));origin=d['meta']['bbox'];p1,p2=fix['endpoints'];x1=(p1[0]-origin[0])*S;y1=(p1[1]-origin[1])*S;x2=(p2[0]-origin[0])*S;y2=(p2[1]-origin[1])*S
  E.SubElement(xf,q('off'),x=str(round(min(x1,x2))),y=str(round(min(y1,y2))));E.SubElement(xf,q('ext'),cx=str(round(abs(x2-x1))),cy=str(round(abs(y2-y1))))
  geo=E.SubElement(pr,q('prstGeom'),prst='line');E.SubElement(geo,q('avLst'));E.SubElement(pr,q('noFill'));ln=E.SubElement(pr,q('ln'),w=str(round(fix['width']*S)),cap='sq');fill=E.SubElement(ln,q('solidFill'));E.SubElement(fill,q('srgbClr'),val=fix['color']);E.SubElement(ln,q('prstDash'),val='solid')
 parts['ppt/slides/slide1.xml']=E.tostring(r,xml_declaration=True,encoding='UTF-8',standalone=True)
 with zipfile.ZipFile(b/'figure.pptx','w',zipfile.ZIP_DEFLATED) as z:
  for n,v in parts.items():z.writestr(n,v)
 print(d['id'],'native PPTX patched',len(r.findall('.//p:sp',N)),'paths',len(r.findall('.//p:pic',N)),'images')
