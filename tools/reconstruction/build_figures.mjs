import fs from 'node:fs/promises';import path from 'node:path';
import {Presentation,PresentationFile} from '@oai/artifact-tool';
const dirs=process.argv.slice(2);
for(const dir of dirs){
 const d=JSON.parse(await fs.readFile(path.join(dir,'figure.json'),'utf8'));const SCALE=3;
 const p=Presentation.create({slideSize:{width:d.width*SCALE,height:d.height*SCALE}});const s=p.slides.add();s.background.fill='#FFFFFF';
 for(let i=0;i<d.objects.length;i++){
  const o=d.objects[i],[x,y,xr,yb]=o.bbox;const w=Math.max(.001,(xr-x)*SCALE),h=Math.max(.001,(yb-y)*SCALE);
  const pos={left:x*SCALE,top:y*SCALE,width:w,height:h};
  if(o.kind==='image'){s.images.add({blob:new Uint8Array(await fs.readFile(o.file)),contentType:'image/png',alt:o.name,fit:'contain',position:pos});continue;}
  const commands=o.path.map(c=>c[0]==='h'?{close:{}}:{[c[0]==='m'?'moveTo':'lineTo']:{x:(c.at(-1)[0]-x)*SCALE,y:(c.at(-1)[1]-y)*SCALE}});
  s.shapes.add({geometry:'custom',name:`Figure element ${i}`,position:pos,fill:o.fill,line:{fill:o.stroke,width:o.lineWidth*SCALE},customPaths:[{width:w,height:h,commands}]});
 }
 s.speakerNotes.textFrame.setText(`${d.meta.paper_title}\n${d.meta.conference??d.meta.venue} ${d.meta.year} ${d.meta.award_name??d.meta.award}\n${d.meta.figure}, PDF page ${d.meta.page}\nPaper: ${d.meta.paper_url}\nAward: ${d.meta.award_url}\nCategory: ${d.meta.category}\nReuse: ${d.meta.reuse_value}`);
 await (await PresentationFile.exportPptx(p)).save(path.join(dir,'draft.pptx'));console.log(d.id,d.objects.length,'native objects exported');
}
