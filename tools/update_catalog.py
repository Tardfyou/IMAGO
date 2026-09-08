#!/usr/bin/env python3
"""Regenerate browsing pages from the committed figure and paper registries."""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1]
DOMAINS=['安全四大','软工顶会','AI顶会']
CATEGORIES=['系统架构','方法细节','动机示例','威胁与攻击','实验图表','研究流程']
def txt(value):return str(value).replace('|',' / ').replace('\n',' ')
def link(label,path):return f'[{txt(label)}](<{path}>)'
def main():
 data=json.loads((ROOT/'catalog/figures.json').read_text());figures=data['figures'];papers=json.loads((ROOT/'catalog/papers.json').read_text())['papers'];by_id={f['id']:f for f in figures}
 lines=['# 素材索引','','[返回 README](../README.md) · [按论文查阅](papers.md) · [JSON](figures.json)','',f'{len(figures)} 张素材；点击编号查看元数据，点击 PPTX/SVG 下载单图。主库页码含第1页目录。','']
 for domain in DOMAINS:
  group=[f for f in figures if f['domain']==domain];deck=group[0]['main_deck']['path'];lines += [f'## {domain}', '',link('下载主PPT','../'+deck),'']
  for category in CATEGORIES:
   selected=[f for f in group if f['category']==category]
   if not selected:continue
   lines += [f'### {category} · {len(selected)} 张','','| 编号 / 主PPT页码 | 论文来源 | 单图 | 借鉴点 / 编辑层级 |','| --- | --- | --- | --- |']
   for f in selected:
    folder=str(Path(f['assets']['pptx']).parent);number=link(f['id'],'../'+folder+'/metadata.json')+f' / 第{f["main_deck"]["slide"]}页';source=link(f['paper_title'],f['source']['paper_url'])+f'<br>{f["conference"]} {f["year"]} · {f["figure"]}'
    assets=' · '.join(link(label,'../'+f['assets'][k])for k,label in [('pptx','PPTX'),('svg','SVG'),('preview','预览'),('reference','原图')]);lines.append(f'| {number} | {source} | {assets} | {txt(f["reuse_value"])}<br>{txt(f["editability"])} |')
   lines.append('')
 (ROOT/'catalog/figures.md').write_text('\n'.join(lines)+'\n')
 lines=['# 已涉及论文清单','','[返回 README](../README.md) · [按图查阅](figures.md) · [JSON 查重清单](papers.json)','',f'{len(papers)} 篇论文，对应 {len(figures)} 张素材。稳定论文编号、题名别名、已用图号和来源指纹保存在 JSON 中。','', '新增前先核对题名及别名，再检查图号和构图。同一论文的同一图及其裁剪变体不重复收录；不同图需要写出独立借鉴价值。','']
 for domain in DOMAINS:
  group=[p for p in papers if domain in p['domains']];lines += [f'## {domain} · {len(group)} 篇','','| 论文 | 会议 / 奖项 | 已用图与位置 |','| --- | --- | --- |']
  for p in sorted(group,key=lambda p:(-max(p['years']),p['awards'][0]['conference'],p['title'].casefold())):
   title=link(p['title'],p['sources'][0]['url'])+'<br>'+p['paper_id']
   if p['title_aliases']:title+='<br>别名：'+'<br>'.join(txt(t)for t in p['title_aliases'])
   award='<br>'.join(f'{a["conference"]} {a["year"]} · '+link(a['award_name'],a['award_url'])for a in p['awards']);materials=[]
   for ident in p['figure_ids']:
    f=by_id[ident]
    if f['domain']==domain:materials.append(link(f'{ident} · {f["figure"]}','../'+f['assets']['pptx'])+f'<br>{f["category"]}；主PPT第{f["main_deck"]["slide"]}页')
   lines.append(f'| {title} | {award} | '+ '<br><br>'.join(materials)+' |')
  lines.append('')
 (ROOT/'catalog/papers.md').write_text('\n'.join(lines)+'\n');print(f'Updated catalogs: {len(figures)} figures / {len(papers)} papers')
if __name__=='__main__':main()
