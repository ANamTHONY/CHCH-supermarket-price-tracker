"""Current Foodstuffs public storefront scraping with verified stores and complete pagination."""
from datetime import datetime
from decimal import Decimal
import re
from urllib.parse import urljoin
from zoneinfo import ZoneInfo
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from store_navigation import navigate_foodstuffs,foodstuffs_identity
from woolworths_scraper import money,cup

CARDS='[itemtype="https://schema.org/Product"]'
CARD_SCRIPT=r'''
return Array.from(document.querySelectorAll('[itemtype="https://schema.org/Product"]'))
 .filter(card=>!card.closest('[aria-roledescription="carousel"]')).map(card=>{
 const text=s=>card.querySelector(s)?.textContent?.trim()||'';
 const price=s=>{const el=card.querySelector(s);if(!el)return '';
 const dollars=el.querySelector('[data-testid="price-dollars"]')?.textContent||'';
 const cents=el.querySelector('[data-testid="price-cents"]')?.textContent||'';
 return dollars.trim()&&cents.trim()?'$'+dollars.replace(/[^0-9]/g,'')+'.'+cents.replace(/[^0-9]/g,''):'';};
 return {source_product_id:card.getAttribute('data-testid'),original_name:text('[data-testid="product-title"]'),
 total_quant:text('[data-testid="product-subtitle"]'),product_url:card.querySelector('a[href*="/shop/product/"]')?.href||'',
 normal_price:price('[data-testid="price"]'),offer_price:price('[data-testid="decal-price"]'),
 member_offer:!!card.querySelector('[data-testid="product-decal-4000"]'),
 public_cup:text('[data-testid="non-promo-unit-price"]'),offer_cup:text('[data-testid="complex-promo-unit-price"]'),
 price_basis:text('[data-testid="price-per"]'),displayed_product_text:card.innerText};
});
'''


def parse_product(raw):
    if not raw['source_product_id'] or not raw['original_name'] or not raw['product_url']:
        raise ValueError('Incomplete source product identity')
    member=raw['member_offer']
    public=money(raw['normal_price'])
    offer=money(raw['offer_price'])
    was=None
    if offer is not None and not member:
        if public is not None and Decimal(public)>Decimal(offer):was=public
        public=offer
    unit_price,unit=cup(raw['public_cup'])
    if not member and raw['offer_cup'] and offer is not None:unit_price,unit=cup(raw['offer_cup'])
    basis=raw['price_basis'].strip().lower()
    if unit_price is None and basis in ['kg','l','ea']:
        unit_price,unit=public,basis
    member_cup,member_unit=cup(raw['offer_cup']) if member else (None,None)
    return {
        'product_id':None,'source_product_id':raw['source_product_id'],'original_name':raw['original_name'],
        'total_quant':raw['total_quant'] or 'NA','product_url':raw['product_url'],
        'total_price':public,'non_member_price':public,'member_price':offer if member else None,
        'unit_price':unit_price,'unit':unit or basis or 'NA','member_unit_price':member_cup,
        'member_unit':member_unit,'was_price':was,'is_promo':int(member or offer is not None),
        'displayed_product_text':raw['displayed_product_text'],
    }


def require_store(driver,store_id,timeout=30):
    def matches(browser):
        store=foodstuffs_identity(browser)
        if store['id']!=store_id:return False
        return store if store['name'] in browser.find_element(By.TAG_NAME,'body').text[:600] else False
    return WebDriverWait(driver,timeout).until(matches)


def read_page(driver,timeout=40):
    def loaded(browser):
        text=browser.find_element(By.TAG_NAME,'body').text
        if 'page not found' in text.lower() or '404' in browser.title:raise RuntimeError('Category route is not available')
        rows=browser.execute_script(CARD_SCRIPT)
        if rows:return rows
        if re.search(r'\b(?:no products|no results|0 products)\b',text,re.I):return {'empty':True}
        return False
    return WebDriverWait(driver,timeout).until(loaded)


def next_page(driver):
    direct=driver.find_elements(By.CSS_SELECTOR,'a[data-testid="pagination-increment"]')
    if direct:return direct[0].get_attribute('href')
    current=driver.find_elements(By.CSS_SELECTOR,'a[aria-current="page"]')
    page=int(current[0].text.strip()) if current and current[0].text.strip().isdigit() else 1
    for anchor in driver.find_elements(By.CSS_SELECTOR,'a[data-testid="pagination-number"]'):
        if anchor.text.strip()==str(page+1):return anchor.get_attribute('href')
    return None


def collect_store(driver,source,store_id,store_name,categories,limit=None):
    origin=f'https://www.{source}.co.nz'
    initial=origin+'/shop/category/fridge-deli-and-eggs/eggs?storeId='+store_id
    store=navigate_foodstuffs(driver,initial,store_id,timeout=40)
    if store['id']!=store_id:raise RuntimeError('Store ID mismatch')
    import json
    fallback=json.loads(driver.find_element(By.ID,'__NEXT_DATA__').get_attribute('textContent'))['props']['pageProps']['fallback']
    tree=fallback.get('categories-'+store_id)
    if not tree:raise RuntimeError('Missing verified store category navigation')
    available=set()
    def visit(nodes):
        for node in nodes:
            available.add(node['url'].rstrip('/'))
            visit(node.get('children',[]))
    visit(tree)
    collected=datetime.now(ZoneInfo('Pacific/Auckland')).date().isoformat()
    all_seen=set();count=0
    for category in categories:
        if category['url'].rstrip('/') not in available:
            print(f"CATEGORY {store_name} {category['name']} {category.get('label','')}: absent from this store's official navigation",flush=True)
            continue
        driver.get(urljoin(origin,category['url']))
        pages=set();seen=set();advertised=None
        while True:
            require_store(driver,store_id)
            rows=read_page(driver)
            if driver.current_url in pages:raise RuntimeError('Repeated pagination URL')
            pages.add(driver.current_url)
            if isinstance(rows,dict):break
            text=driver.find_element(By.TAG_NAME,'body').text
            match=re.search(r'Showing\s+[\d,]+\s*[-–]\s*[\d,]+\s+of\s+([\d,]+)\s+products',text,re.I)
            if match:advertised=int(match.group(1).replace(',',''))
            require_store(driver,store_id)
            fresh=0
            for raw in rows:
                record=parse_product(raw);sku=record['source_product_id']
                if sku in seen:continue
                seen.add(sku);fresh+=1
                key=(category['name'],sku)
                if key in all_seen:continue
                all_seen.add(key)
                record.update(source=source,store_id=store_id,store_name=store_name,actual_store_name=store['name'],
                              category_id={'Egg':1,'Milk':2,'Meat':3}[category['name']],category_name=category['name'],
                              collected_date=collected,store_verified=True)
                yield record;count+=1
                if limit is not None and count>=limit:return
            if not fresh:raise RuntimeError('Pagination produced no new product IDs')
            print(f"PAGE {store_name} {category['name']} {category.get('label','')} pages={len(pages)} products={len(seen)} total={advertised}",flush=True)
            target=next_page(driver)
            if not target:
                if advertised is not None and len(seen)<advertised:
                    raise RuntimeError(f'Incomplete category: {len(seen)} of {advertised} products')
                break
            driver.get(target)
        print(f"CATEGORY {store_name} {category['name']} {category.get('label','')}: {len(seen)} products",flush=True)
