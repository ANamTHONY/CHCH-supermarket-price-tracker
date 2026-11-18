"""Collect only public store directory fields from official store detail pages."""
import sys,json,re
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from browser_driver import Chrome, uc, chrome_major_version
root=Path(__file__).resolve().parents[1]

def finder_stores(tag):
 j=json.loads((root/f'data/{tag}_page.json').read_text(encoding='utf-8'))
 found=[]
 def walk(x):
  if isinstance(x,dict):
   if 'regionStoreGroupings' in x:
    for group in x['regionStoreGroupings']['southIsland']:
     if group['heading']=='Canterbury':found.extend(group['stores'])
   for v in x.values():walk(v)
  elif isinstance(x,list):
   for v in x:walk(v)
 walk(j['props']['pageProps']['page'])
 return found
out=[]
executable=uc.find_chrome_executable()
b=Chrome(browser_executable_path=executable,version_main=chrome_major_version(executable),driver_executable_path=uc.Patcher().executable_path,headless=False)
b.set_page_load_timeout(18)
try:
 for tag,domain in [('nw','www.newworld.co.nz'),('pak','www.paknsave.co.nz')]:
  stores=finder_stores(tag)
  for store in stores:
   if 'Christchurch' not in store.get('address','') and store['title'] not in ['Bishopdale','Durham Street','Fendalton','Ferry Road','Halswell','Ilam','Northwood','Prestons','St Martins','Stanmore','Wigram']:continue
   url='https://'+domain+store['url']
   try:
    b.get(url)
    j=json.loads(b.find_element('id','__NEXT_DATA__').get_attribute('textContent'))
    p=j['props']['pageProps']['page']
    contact=p['contact_details']
    row={'source':'newworld' if tag=='nw' else 'paknsave','store_id':p['ecom_store_id'],'store_name':p['card_info']['heading'],'address':contact['address'],'latitude':contact['latitude'],'longitude':contact['longitude'],'source_url':url,'title':store['title']}
    out.append(row);print(row,flush=True)
    (root/'data/official_foodstuffs_locations.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
   except Exception as e:print(store['title'],type(e).__name__,flush=True)
finally:b.quit()
