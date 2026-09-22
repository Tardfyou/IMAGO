#!/usr/bin/env python3
"""Validate the committed library without external services or extra packages."""
from pathlib import Path
from urllib.parse import unquote,urlsplit
import collections,hashlib,json,re,sys,zipfile
from xml.etree import ElementTree as E
ROOT=Path(__file__).resolve().parents[1]

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def visual(parts):return hashlib.sha256(b''.join(n.encode()+parts[n]for n in sorted(parts)if not n.startswith('ppt/notesSlides/'))).hexdigest()
def figure_key(label):
    m=re.search(r'(?:figure|fig\.?)\s*([a-z]?\d+)',label,re.I)
    return m[1].casefold() if m else re.sub(r'\s+','',label).casefold()
def main():
 catalog=json.loads((ROOT/'catalog/figures.json').read_text());figures=catalog['figures'];papers=json.loads((ROOT/'catalog/papers.json').read_text())['papers'];pack=json.loads((ROOT/'validation/packaging.json').read_text());pack_by_path={x['path']:x for x in pack['entries']};status=json.loads((ROOT/'validation/status.json').read_text());appendices=status.get('main_deck_appendices',{});errors=[];identity={};paper_by_id={p['paper_id']:p for p in papers};pairs=set();ids=set();all_ppt=set();local_links=0
 def require(ok,message):
  if not ok:errors.append(message)
 for p in papers:
  for key in p['identity_keys']:
   require(key not in identity or identity[key]==p['paper_id'],'Paper identity conflict: '+p['paper_id'])
   identity[key]=p['paper_id']
 for f in figures:
  require(f['id']not in ids,'Duplicate ID: '+f['id']);ids.add(f['id']);require(f['paper_id']in paper_by_id,'Missing paper: '+f['id']);pair=(f['paper_id'],figure_key(f['figure']));require(pair not in pairs,'Duplicate paper/figure: '+f['id']);pairs.add(pair)
  require(bool(re.fullmatch('[a-f0-9]{64}',f['source']['pdf_sha256'])),'Missing PDF fingerprint: '+f['id'])
  for key,rel in f['assets'].items():
   file=ROOT/rel;require(file.is_file(),'Missing asset: '+rel)
   if file.is_file():require(sha(file)==f['hashes'][key],'Asset hash mismatch: '+rel)
  ppt=f['assets']['pptx'];all_ppt.add(ppt)
  with zipfile.ZipFile(ROOT/ppt)as z:
   require(z.testzip()is None,'Corrupt ZIP: '+ppt);slides=[n for n in z.namelist()if re.fullmatch(r'ppt/slides/slide\d+\.xml',n)];require(len(slides)==1,'Individual slide count: '+ppt)
   notes='\n'.join(''.join(E.fromstring(z.read(n)).itertext())for n in z.namelist()if n.startswith('ppt/notesSlides/notesSlide')and n.endswith('.xml'))
   for url in [f['source']['paper_url'],f['source']['award_url']]:require(url in notes,'Missing note attribution: '+f['id'])
  svg=E.parse(ROOT/f['assets']['svg']).getroot();require(svg.tag.split('}')[-1]=='svg','Invalid SVG root: '+f['id'])
  for el in svg.iter():
   for key,value in el.attrib.items():
    if key.endswith('href'):require(value.startswith(('#','data:')),'SVG external dependency: '+f['id'])
  metadata=ROOT/Path(ppt).parent/'metadata.json';require(json.loads(metadata.read_text())==f,'Metadata differs from catalog: '+f['id'])
 for p in papers:
  expected={f['id']for f in figures if f['paper_id']==p['paper_id']};require(expected==set(p['figure_ids']),'Paper figure list mismatch: '+p['paper_id']);require(len(expected)==p['figure_count'],'Paper figure count mismatch: '+p['paper_id'])
 decks={f['main_deck']['path']for f in figures}
 for deck in decks:
  selected=[f for f in figures if f['main_deck']['path']==deck];all_ppt.add(deck)
  with zipfile.ZipFile(ROOT/deck)as z:
   require(z.testzip()is None,'Corrupt deck: '+deck);slides=[n for n in z.namelist()if re.fullmatch(r'ppt/slides/slide\d+\.xml',n)];require(len(slides)==len(selected)+1+appendices.get(deck,0),'Main slide count: '+deck)
   for f in selected:
    r=E.fromstring(z.read(f'ppt/slides/slide{f["main_deck"]["slide"]}.xml'));require(any(f['id']in x.get('name','')for x in r.iter()if x.tag.endswith('cNvPr')),'Missing figure on main slide: '+f['id'])
 for rel in sorted(all_ppt):
  file=ROOT/rel;record=pack_by_path.get(rel);require(record is not None,'Missing packaging record: '+rel)
  with zipfile.ZipFile(file)as z:parts={n:z.read(n)for n in z.namelist()}
  if record:
   require(sha(file)==record['repository_sha256'],'Packaged PPT hash mismatch: '+rel);require(visual(parts)==record['visual_payload_sha256'],'Visual payload changed: '+rel)
  for name,data in parts.items():
   if name.endswith(('.xml','.rels')):require(b'/Users/'not in data,'Machine path in PPT: '+rel)
 for file in ROOT.rglob('*'):
  if not file.is_file()or '.git' in file.relative_to(ROOT).parts or '__pycache__'in file.parts:continue
  require(file.stat().st_size<100*1024*1024,'File exceeds100MiB: '+str(file.relative_to(ROOT)))
  if file.suffix in ['.md','.json','.py','.mjs']:
   text=file.read_text();require('/Users/'not in text or file.name=='check_library.py','Machine path in text: '+str(file.relative_to(ROOT)))
  if file.suffix=='.md':
   text=file.read_text();targets=re.findall(r'\]\((?:<([^>]+)>|([^\s)]+))\)',text);links=[a or b for a,b in targets]+re.findall(r'(?:src|href)="([^"]+)"',text)
   for value in links:
    if value.startswith(('http:','https:','mailto:','#')):continue
    path=unquote(urlsplit(value).path)
    if path:local_links+=1;require((file.parent/path).exists(),'Broken local link in '+str(file.relative_to(ROOT))+': '+path)
 summary=catalog['summary'];require(summary['figures']==len(figures),'Summary figure count');require(summary['papers']==len(papers),'Summary paper count')
 for k,n in summary['by_category'].items():require(n==sum(f['category']==k for f in figures),'Category count: '+k)
 for k,n in summary['by_domain'].items():require(n==sum(f['domain']==k for f in figures),'Domain count: '+k)
 print(json.dumps({'figures':len(figures),'papers':len(papers),'pptx_files':len(all_ppt),'local_links_checked':local_links,'errors':errors,'native_powerpoint_editor_review':summary['native_powerpoint_editor_review']},ensure_ascii=False,indent=2));return 1 if errors else 0
if __name__=='__main__':raise SystemExit(main())
