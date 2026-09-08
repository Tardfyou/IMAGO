def split_contours(path):
 out=[];cur=[]
 for c in path:
  if c[0]=='m' and cur:out.append(cur);cur=[]
  cur.append(c)
 if cur:out.append(cur)
 return out

def poly(cont):
 pts=[];prev=None
 for c in cont:
  if c[0] in ('m','l'):prev=c[1];pts.append(prev)
  elif c[0]=='c':
   a=prev;b,e,d=c[1:]
   for j in range(1,25):
    t=j/24;u=1-t;pts.append([u**3*a[k]+3*u*u*t*b[k]+3*u*t*t*e[k]+t**3*d[k] for k in [0,1]])
   prev=d
 return pts

def inside(pt,pol):
 x,y=pt;odd=False;j=len(pol)-1
 for i in range(len(pol)):
  xi,yi=pol[i];xj,yj=pol[j]
  if ((yi>y)!=(yj>y)) and x<(xj-xi)*(y-yi)/(yj-yi)+xi:odd=not odd
  j=i
 return odd

def reverse(cont):
 p0=cont[0][1];p=p0;seg=[]
 for c in cont[1:]:
  if c[0]=='l':seg.append(('l',p,c[1]));p=c[1]
  elif c[0]=='c':seg.append(('c',p,*c[1:]));p=c[3]
 out=[['m',p]]
 for s in reversed(seg):
  if s[0]=='l':out.append(['l',s[1]])
  else:out.append(['c',s[3],s[2],s[1]])
 out.append(['h']);return out

def nonzero(path):
 contours=split_contours(path);polys=[poly(c) for c in contours];out=[]
 for i,(c,p) in enumerate(zip(contours,polys)):
  if len(p)<3:out+=c;continue
  area=sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(p,p[1:]+p[:1]))
  depth=sum(inside(p[0],q) for j,q in enumerate(polys) if j!=i and len(q)>2)
  target=1 if depth%2==0 else -1
  if (area>0)!=(target>0):c=reverse(c)
  out+=c
 return out
