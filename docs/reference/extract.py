from html.parser import HTMLParser
from pathlib import Path
import html,json,re,shutil,subprocess,concurrent.futures
SRC=Path('/Users/niuniutang/Downloads/微信公众平台.html')
OUT=Path(__file__).resolve().parent
VOID={'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}
class Node:
 def __init__(self,tag='',attrs=()): self.tag=tag; self.attrs=dict(attrs); self.children=[]
 def walk(self):
  yield self
  for c in self.children:
   if isinstance(c,Node): yield from c.walk()
 def text(self):
  if self.tag in {'script','style'}: return ''
  s=''.join(c.text() if isinstance(c,Node) else c for c in self.children)
  return s+('\n' if self.tag in {'p','div','section','h1','h2','h3','li','br'} else '')
class Parser(HTMLParser):
 def __init__(self): super().__init__(); self.root=Node(); self.stack=[self.root]
 def handle_starttag(self,t,a):
  n=Node(t,a); self.stack[-1].children.append(n)
  if t not in VOID:self.stack.append(n)
 def handle_startendtag(self,t,a):self.handle_starttag(t,a); self.handle_endtag(t) if t not in VOID else None
 def handle_endtag(self,t):
  for i in range(len(self.stack)-1,0,-1):
   if self.stack[i].tag==t: self.stack=self.stack[:i];break
 def handle_data(self,d):self.stack[-1].children.append(d)
p=Parser(); p.feed(SRC.read_text()); nodes=list(p.root.walk())
content=next(n for n in nodes if n.attrs.get('id')=='js_content')
title=next((n.text().strip() for n in nodes if n.attrs.get('id')=='activity-name'),'微信文章')
imgs=[n for n in content.walk() if n.tag=='img']
print(json.dumps({'title':title,'text_chars':len(content.text()),'body_images':len(imgs),'image_note':'includes one UI QR placeholder'},ensure_ascii=False))
(OUT/'images').mkdir(exist_ok=True)
records=[]; mapping={}
for n in [n for n in nodes if n.tag=='img']:
 remote=n.attrs.get('data-src',''); src=n.attrs.get('src','')
 key=remote or src
 if not key or key in mapping or key=='https://mp.weixin.qq.com/s/BfQmTUBSFOZPSwZRReUjOw':continue
 local=SRC.parent / __import__('urllib.parse',fromlist=['unquote']).unquote(src)
 if not (remote.startswith('https://') or src.startswith('https://') or local.is_file()):continue
 rec={'index':len(records)+1,'url':remote or src,'saved_src':src,'in_article':n in imgs}
 records.append(rec); mapping[key]=rec
(OUT/'manifest.json').write_text(json.dumps(records,ensure_ascii=False,indent=2))
def fetch(rec):
 existing=list((OUT/'images').glob(f"{rec['index']:03d}.*"))
 if existing and existing[0].suffix!='.bin':
  rec['file']=str(existing[0].relative_to(OUT));rec['bytes']=existing[0].stat().st_size;return
 src=rec['saved_src']; local=SRC.parent / __import__('urllib.parse',fromlist=['unquote']).unquote(src)
 dest=OUT/'images'/f"{rec['index']:03d}.bin"
 if not src.startswith(('data:', 'https:', 'http:')) and local.is_file(): shutil.copy2(local,dest)
 elif rec['url'].startswith('https://'):
  r=subprocess.run(['curl','-fLsS','--max-time','40','--retry','2','-A','Mozilla/5.0','-e','https://mp.weixin.qq.com/',rec['url'],'-o',str(dest)],capture_output=True)
  if r.returncode:rec['error']=r.stderr.decode()[:300];return
 else:rec['error']='No available source';return
 b=dest.read_bytes();ext=('.png' if b.startswith(b'\x89PNG') else '.jpg' if b.startswith(b'\xff\xd8\xff') else '.gif' if b.startswith(b'GIF8') else '.webp' if b[:4]==b'RIFF' and b[8:12]==b'WEBP' else '.svg' if b'<svg' in b[:1000] else None)
 if not ext: rec['error']='Downloaded content is not a recognized image';dest.unlink();return
 final=dest.with_suffix(ext);dest.rename(final);rec['file']=str(final.relative_to(OUT));rec['bytes']=len(b)
if '--download' in __import__('sys').argv:
 with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:list(pool.map(fetch,records))
 (OUT/'manifest.json').write_text(json.dumps(records,ensure_ascii=False,indent=2))
 def render(n):
  if isinstance(n,str):return html.escape(n)
  if n.tag in {'script','style','iframe'}:return ''
  if n.tag=='img':
   if n.attrs.get('src')=='https://mp.weixin.qq.com/s/BfQmTUBSFOZPSwZRReUjOw' and not n.attrs.get('data-src'):return ''
   r=mapping.get(n.attrs.get('data-src') or n.attrs.get('src'))
   return '<img src="'+html.escape(r['file'])+'" alt="图片">' if r and 'file' in r else '<p>[图片未能下载]</p>'
  tag=n.tag if n.tag in {'p','section','div','span','strong','b','em','i','a','br','ul','ol','li','h1','h2','h3','h4','blockquote','pre','code','table','tr','td','th','tbody','hr'} else 'div'
  return '<'+tag+'>'+''.join(render(c) for c in n.children)+('' if tag in VOID else '</'+tag+'>')
 text=re.sub(r'\n[ \t\xa0]*\n+', '\n\n', content.text()).strip()
 (OUT/'article.txt').write_text(title+'\n\n来源：https://mp.weixin.qq.com/s/BfQmTUBSFOZPSwZRReUjOw\n\n'+text)
 (OUT/'article.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>'+html.escape(title)+'</title><style>body{max-width:850px;margin:40px auto;padding:20px;line-height:1.8;font-family:system-ui}img{max-width:100%;height:auto;display:block;margin:20px auto}table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:8px}</style><h1>'+html.escape(title)+'</h1>'+render(content)+'</html>')
 shutil.copy2(SRC,OUT/'original_saved.html')
 print(json.dumps({'total':len(records),'success':sum('file' in r for r in records),'failed':[r for r in records if 'error' in r]},ensure_ascii=False))
