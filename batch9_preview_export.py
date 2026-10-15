from pathlib import Path
import sys,json,secrets,base64,re,mimetypes
from urllib.parse import urlsplit
from bs4 import BeautifulSoup
r=Path(__file__).resolve().parent;sys.path.insert(0,str(r/'tests'))
from local_browser_server import disposable_app
from fastapi.testclient import TestClient
out=r/'batch9-preview';out.mkdir(exist_ok=True)
paths=['/'] + ['/leak-repair-'+s for s in ['guildford','woking','merrow','fairlands']] + ['/toilet-repair-'+s for s in ['guildford','woking','burpham']]
entries=[]
with disposable_app(secrets.token_urlsafe(12),secrets.token_urlsafe(16),projects_as_drafts=False,advice_as_drafts=False) as (app,_):
 with TestClient(app.app) as client:
  def embedded(path):
   assert path.startswith(('/site-images/','/static/'))
   response=client.get(path);assert response.status_code==200,path
   return 'data:'+response.headers.get('content-type',mimetypes.guess_type(path)[0])+';base64,'+base64.b64encode(response.content).decode()
  for path in paths:
   response=client.get(path);assert response.status_code==200,path
   d=BeautifulSoup(response.text,'html.parser')
   for t in d.find_all(['script','form','iframe']):t.decompose()
   for t in d.select('#analytics-consent, #analytics-settings, meta[name="robots"]'):t.decompose()
   for t in d.find_all(True):
    for k in list(t.attrs):
     if k.startswith('on'):del t[k]
   for a in d.find_all('a',href=True):
    href=a['href'];u=urlsplit(href)
    if href.startswith('#'):continue
    if u.path in paths and not u.scheme:a['href']=('/' if u.path=='/' else u.path+'.html')+('#'+u.fragment if u.fragment else '')
    else:a['href']='#preview-notice';a['title']='Preview only — contact and other links disabled'
   for img in d.find_all('img',src=True):
    src=img['src']
    if src.startswith('/'):img['src']=embedded(src)
    assert img['src'].startswith('data:'),src
    img.attrs.pop('srcset',None)
   for style in d.find_all('style'):
    style.string=re.sub(r'url\([\"\']?(/[^\"\')]+)[\"\']?\)',lambda m:'url('+embedded(m[1])+')',style.get_text())
   d.head.insert(0,d.new_tag('meta',attrs={'http-equiv':'Content-Security-Policy','content':"default-src 'none'; img-src data:; style-src 'unsafe-inline'; form-action 'none'; base-uri 'none'; connect-src 'none'"}))
   d.head.append(d.new_tag('meta',attrs={'name':'robots','content':'noindex,nofollow,noarchive'}))
   notice=d.new_tag('div',id='preview-notice',style='background:#fff4d9;color:#123247;padding:8px 4%;font:14px system-ui')
   notice.append('PR #17 content preview · Contact and enquiry links disabled · ')
   for label,url in [('Home','/'),('Leak Guildford','/leak-repair-guildford.html'),('Toilet Burpham','/toilet-repair-burpham.html')]:
    a=d.new_tag('a',href=url);a.string=label;notice.append(a);notice.append(' · ')
   d.body.insert(0,notice)
   filename='index.html' if path=='/' else path[1:]+'.html';content=str(d);(out/filename).write_text(content)
   entries.append({'path':'batch9-preview/'+filename,'type':'blob','mode':'100644','content':content})
for filename,content in [('robots.txt','User-agent: *\nDisallow: /\n')]:
 (out/filename).write_text(content);entries.append({'path':'batch9-preview/'+filename,'type':'blob','mode':'100644','content':content})
print(json.dumps({'pages':len(paths),'bytes':sum(len(x['content']) for x in entries)}))
