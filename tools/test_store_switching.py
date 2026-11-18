"""Scrape five products per store only after verifying actual shopping-store identity."""
import argparse,csv,json,re,sys,time,traceback
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));sys.stdout.reconfigure(encoding='utf-8')
from browser_driver import create_driver
from store_navigation import navigate_foodstuffs,foodstuffs_identity
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/store_switch_test'
OUT.mkdir(parents=True,exist_ok=True)
RUN_ID=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')


def foodstuffs_products(driver,limit=5):
    items=[];seen=set()
    for card in driver.find_elements(By.CSS_SELECTOR,'[itemtype="https://schema.org/Product"]'):
        sku=card.get_attribute('data-testid')
        if sku in seen:continue
        title=card.find_element(By.CSS_SELECTOR,'[data-testid="product-title"]').text.strip()
        spec=card.find_element(By.CSS_SELECTOR,'[data-testid="product-subtitle"]').text.strip()
        blocks=card.find_elements(By.CSS_SELECTOR,'[data-testid="decal-price"]')
        if not blocks:blocks=card.find_elements(By.CSS_SELECTOR,'[data-testid="price"]')
        price=None
        for block in blocks:
            dollars=block.find_elements(By.CSS_SELECTOR,'[data-testid="price-dollars"]')
            cents=block.find_elements(By.CSS_SELECTOR,'[data-testid="price-cents"]')
            if dollars and cents and dollars[0].text.strip():
                price=float(re.sub(r'[^0-9]','',dollars[0].text)+'.'+re.sub(r'[^0-9]','',cents[0].text));break
        if not title or price is None:continue
        seen.add(sku)
        items.append({'sku':sku,'original_name':title,'total_quant':spec,'total_price':price,'displayed_product_text':card.text})
        if len(items)==limit:return items
    raise RuntimeError(f'Only {len(items)} valid product cards; expected {limit}')


def new_browser(page_load_strategy="eager"):
    driver=create_driver(page_load_strategy=page_load_strategy)
    driver.set_page_load_timeout(45)
    return driver


def save_results(results):
    (OUT/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/f'results_{RUN_ID}.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    rows=[]
    for r in results:
        for p in r.get('products',[]):
            rows.append({k:v for k,v in {**{x:r.get(x) for x in ['source','requested_store_id','requested_store_name','actual_store_id','actual_store_name','verified','checked_at']},**p}.items() if k!='displayed_product_text'})
    if rows:
        with (OUT/'products.csv').open('w',encoding='utf-8',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(dict.fromkeys(key for row in rows for key in row)));writer.writeheader();writer.writerows(rows)


def run_foodstuffs(only_source=None):
    previous=json.loads((OUT/'results.json').read_text(encoding='utf-8')) if (OUT/'results.json').exists() else []
    results=[r for r in previous if r['source'] != only_source] if only_source else []
    locations=json.loads((ROOT/'reference/store_locations.json').read_text(encoding='utf-8'))
    wanted={'newworld':['New World Wigram','New World Ilam','New World Fendalton'],'paknsave':["PAK'nSAVE Riccarton","PAK'nSAVE Moorhouse","PAK'nSAVE Papanui"]}
    driver=None
    try:
        for source,names in wanted.items():
            if only_source and source!=only_source:continue
            for name in names:
                if driver is not None:driver.quit()
                driver=new_browser()
                store=next(s for s in locations if s['store_name']==name)
                id=store['store_id']
                result={'source':source,'requested_store_id':id,'requested_store_name':name,'checked_at':datetime.now(timezone.utc).isoformat(),'verified':False}
                try:
                    # Exercise the legacy URL used by the production pipeline, including redirect recovery.
                    url=f'https://www.{source}.co.nz/shop/category/fresh-foods-and-bakery/dairy--eggs/eggs?storeId={id}'
                    identity=navigate_foodstuffs(driver,url,id)
                    assert identity['name']==name,(identity['name'],name)
                    first_products=foodstuffs_products(driver)
                    driver.refresh()
                    WebDriverWait(driver,25).until(lambda b:foodstuffs_identity(b)['id']==id and name in b.find_element(By.TAG_NAME,'body').text[:500])
                    WebDriverWait(driver,25).until(lambda b:len(b.find_elements(By.CSS_SELECTOR,'[itemtype="https://schema.org/Product"]'))>=5)
                    products=foodstuffs_products(driver)
                    result.update(actual_store_id=identity['id'],actual_store_name=identity['name'],verified=True,reload_verified=True,products=products,final_url=driver.current_url)
                    driver.save_screenshot(str(OUT/f'{source}_{id}.png'))
                    print('PASS',name,'5 products; store identity survives refresh',flush=True)
                except Exception as e:
                    result.update(error=str(e),error_type=type(e).__name__,final_url=driver.current_url)
                    try:
                        result['diagnostic_identity']=foodstuffs_identity(driver)
                        result['diagnostic_header']=driver.find_element(By.TAG_NAME,'body').text[:500]
                        (OUT/f'{source}_{id}_failed.html').write_text(driver.page_source,encoding='utf-8')
                    except Exception:
                        pass
                    print('FAIL',name,type(e).__name__,str(e)[:250],flush=True)
                results.append(result);save_results(results)
    finally:
        if driver is not None:driver.quit()
    return results


def woolworths_products(driver,limit=5):
    from woolworths_scraper import CARD_DATA,parse_product,CARDS
    products=[];seen=set()
    for card in driver.find_elements(By.CSS_SELECTOR,CARDS):
        raw=driver.execute_script(CARD_DATA,card)
        if not raw['name']:continue
        record=parse_product(raw)
        if record['source_product_id'] in seen:continue
        seen.add(record['source_product_id'])
        record['sku']=record['source_product_id']
        products.append(record)
        if len(products)==limit:return products
    raise RuntimeError(f'Only {len(products)} Woolworths products loaded')


def run_woolworths():
    from store_navigation import select_woolworths_store
    from selenium.common.exceptions import TimeoutException
    results=json.loads((OUT/'results.json').read_text(encoding='utf-8')) if (OUT/'results.json').exists() else []
    results=[r for r in results if r['source']!='woolworths']
    for id,name in [('001','Woolworths Avonhead'),('006','Woolworths Church Corner'),('005','Woolworths Christchurch Airport')]:
        driver=new_browser('normal')
        result={'source':'woolworths','requested_store_id':id,'requested_store_name':name,'id_namespace':'project-local','checked_at':datetime.now(timezone.utc).isoformat(),'verified':False}
        try:
            driver.get('https://www.woolworths.co.nz/shop/browse/pantry/eggs')
            print('Checking',name,flush=True)
            label=select_woolworths_store(driver,name,timeout=45)
            # A fresh document after store selection avoids retaining old store prices.
            driver.refresh()
            wait=WebDriverWait(driver,70)
            wait.until(lambda b:label in b.find_element(By.TAG_NAME,'body').text[:700])
            print('Store persisted;',name,'waiting for 5 product cards',flush=True)
            wait.until(lambda b:len(b.find_elements(By.CSS_SELECTOR,'a[class*="product-tile_description"]'))>=5)
            products=woolworths_products(driver)
            result.update(actual_store_id=id,actual_store_name=label,verified=True,reload_verified=True,products=products,final_url=driver.current_url)
            driver.save_screenshot(str(OUT/f'woolworths_{id}.png'))
            print('PASS',name,'5 products; pickup store survives refresh',flush=True)
        except Exception as e:
            result.update(traceback=traceback.format_exc(),error=str(e),error_type=type(e).__name__,final_url=driver.current_url,diagnostic_header=driver.find_element(By.TAG_NAME,'body').text[:700])
            (OUT/f'woolworths_{id}_failed.html').write_text(driver.page_source,encoding='utf-8')
            driver.save_screenshot(str(OUT/f'woolworths_{id}_failed.png'))
            print('FAIL',name,type(e).__name__,str(e)[:200],traceback.format_exc()[:900],flush=True)
        finally:driver.quit()
        results.append(result);save_results(results)
    return results


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',choices=['newworld','paknsave','woolworths'])
    args=parser.parse_args()
    if args.source=='woolworths':run_woolworths()
    else:
        run_foodstuffs(args.source)
        if not args.source:run_woolworths()
