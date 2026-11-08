"""Woolworths NZ's current React storefront: verified store and public/member prices."""
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import re
import time
import threading
from urllib.parse import urljoin
from zoneinfo import ZoneInfo
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from store_navigation import select_woolworths_store
from access_guard import check_access

ORIGIN='https://www.woolworths.co.nz'
EGGS_URL=ORIGIN+'/shop/browse/pantry/eggs'
CARDS='[class*="product-grid_productTileCell"]'
LINKS='a[class*="product-tile_description"]'
PAGE_INTERVAL_SECONDS=10
_navigation_lock=threading.Lock()
_last_navigation=0.0


def paced_navigation(driver,url=None):
    """Space document navigation starts; this does not override website access rules."""
    global _last_navigation
    with _navigation_lock:
        delay=PAGE_INTERVAL_SECONDS-(time.monotonic()-_last_navigation)
        if delay>0:time.sleep(delay)
        _last_navigation=time.monotonic()
        if url is None:driver.refresh()
        else:driver.get(url)
    check_access(driver)

CARD_DATA = r'''
const card=arguments[0];
const text=selector => card.querySelector(selector)?.textContent?.trim() || '';
const link=card.querySelector('a[class*="product-tile_description"]');
return {
 name:link?.textContent?.trim() || '', url:link?.href || '',
 hero_price:text('[class*="product-price_value"]'),
 non_member_price:text('[class*="product-tile_nonMemberPrice"] [class*="product-tile_price"]'),
 cup_price:text('[class*="product-tile_cupPrice"]'),
 non_member_cup_price:text('[class*="product-tile_nonMembercupPrice"]'),
 member_offer:!!card.querySelector('[class*="product-price_memberPricePanel"]'),
 was_price:text('[class*="product-price_priceWas"]'),
 displayed_text:card.innerText
};
'''


def money(text):
    match=re.search(r'\$\s*([\d,]+(?:\.\d{1,2})?)',text or '')
    return str(Decimal(match.group(1).replace(',','')).quantize(Decimal('0.01'))) if match else None


def cup(text):
    if not text or '/' not in text:return None,None
    price=money(text)
    unit=text.split('/',1)[1].strip()
    unit=re.sub(r'^1(?=[a-zA-Z])','',unit).lower()
    return price,unit


def parse_product(raw):
    name=raw['name'].strip()
    sku=re.search(r'/product-details/(\d+)/',raw['url'])
    if not name or not sku:raise ValueError('Product card lacks a name or source product ID')
    is_member=bool(raw['member_offer'])
    member_price=money(raw['hero_price']) if is_member else None
    normal_price=money(raw['non_member_price']) if is_member else money(raw['hero_price'])
    normal_cup=raw['non_member_cup_price'] if is_member else raw['cup_price']
    unit_price,unit=cup(normal_cup)
    member_unit_price,member_unit=cup(raw['cup_price']) if is_member else (None,None)
    was_price=money(raw['was_price'])
    spec=re.search(r'(\d+(?:\.\d+)?\s*(?:pack|pk|kg|g|ml|l|ea))\s*$',name,re.I)
    quantity=spec.group(1).lower().replace(' ','').replace('pack','pk') if spec else 'NA'
    return {
        'source_product_id':sku.group(1),'original_name':name,'product_url':raw['url'],
        'total_quant':quantity,'total_price':normal_price,'non_member_price':normal_price,
        'member_price':member_price,'was_price':was_price,
        'unit_price':unit_price,'unit':unit or 'NA',
        'member_unit_price':member_unit_price,'member_unit':member_unit,
        'is_promo':int(is_member or (was_price is not None and normal_price is not None and Decimal(was_price)>Decimal(normal_price))),
        'is_member_offer':is_member,
        'price_status':'ok' if normal_price is not None else 'public_price_missing',
        'displayed_product_text':raw['displayed_text'],
    }


def actual_store(driver):
    check_access(driver)
    buttons=driver.find_elements(By.CSS_SELECTOR,'button[aria-label^="Selected Store:"]')
    return next((button.text.strip() for button in buttons if button.is_displayed()),None)


def require_store(driver,expected,timeout=45):
    return WebDriverWait(driver,timeout).until(lambda browser:actual_store(browser)==expected)


def open_page(driver,url):
    try:paced_navigation(driver,url)
    except TimeoutException:
        # Third-party assets can keep load pending; only proceed when real page content exists.
        if not driver.find_elements(By.CSS_SELECTOR,LINKS):raise
    check_access(driver)


def prepare_store(driver,name,timeout=45):
    open_page(driver,EGGS_URL)
    label=select_woolworths_store(driver,name,timeout)
    # Reload with the saved pickup preference so prices come from the selected store.
    paced_navigation(driver)
    require_store(driver,label,timeout)
    return label


def iter_products(driver,url,expected_store,limit=None,timeout=45):
    # Buffer a category so a failed pagination pass cannot publish partial rows.
    for attempt in range(2):
        try:
            records=list(_iter_products(driver,url,expected_store,limit,timeout))
            yield from records
            return
        except RuntimeError as error:
            if attempt or not str(error).startswith('Incomplete category:'):
                raise
            print('Retrying incomplete Woolworths category:',url,flush=True)


def _iter_products(driver,url,expected_store,limit=None,timeout=45):
    open_page(driver,url)
    seen=set();visited=set()
    while True:
        require_store(driver,expected_store,timeout)
        def page_ready(browser):
            check_access(browser)
            if browser.find_elements(By.CSS_SELECTOR,LINKS):return 'products'
            text=browser.find_element(By.TAG_NAME,'body').text
            if 'page not found' in text.lower() or '404' in browser.title:
                raise RuntimeError('Category route is not available')
            if re.search(r'\b(?:0 products|no products|no results)\b',text,re.I):return 'empty'
            return False
        for attempt in range(3):
            try:
                ready=WebDriverWait(driver,timeout).until(page_ready)
                break
            except TimeoutException:
                if attempt==2:raise
                print('Reloading incomplete Woolworths page:',driver.current_url,flush=True)
                paced_navigation(driver)
                require_store(driver,expected_store,timeout)
        if ready=='empty':return
        def cards_ready(browser):
            check_access(browser)
            text=browser.find_element(By.TAG_NAME,'body').text
            bounds=re.search(r'(\d+)\s+to\s+(\d+)\s+of\s+[\d,]+\s+products',text,re.I)
            cards=browser.find_elements(By.CSS_SELECTOR,LINKS)
            named=sum(bool(card.text.strip()) for card in cards)
            return named>=int(bounds.group(2))-int(bounds.group(1))+1 if bounds else bool(named)
        WebDriverWait(driver,timeout).until(cards_ready)
        if driver.current_url in visited:raise RuntimeError('Pagination loop detected')
        visited.add(driver.current_url)
        read_card='function(card){'+CARD_DATA.replace('const card=arguments[0];','')+'}'
        raw_rows=driver.execute_script('return Array.from(document.querySelectorAll(arguments[0])).map('+read_card+');',CARDS)
        parsed=0
        for raw in raw_rows:
            if not raw['name']:continue  # Promotional tiles and skeleton placeholders.
            record=parse_product(raw)
            if record['source_product_id'] in seen:continue
            seen.add(record['source_product_id']);parsed+=1
            yield record
            if limit is not None and len(seen)>=limit:return
        if not parsed:raise RuntimeError('No new product records on this page')
        print('PAGE Woolworths',expected_store,driver.current_url,'products',len(seen),flush=True)
        next_links=driver.find_elements(By.CSS_SELECTOR,'nav[aria-label="Pagination"] a[rel="next"]')
        if not next_links:
            text=driver.find_element(By.TAG_NAME,'body').text
            expected=re.search(r'\d+\s+to\s+\d+\s+of\s+([\d,]+)\s+products',text,re.I)
            if expected and len(seen)<int(expected.group(1).replace(',','')):
                raise RuntimeError(f'Incomplete category: {len(seen)} products collected')
            return
        next_url=next_links[0].get_attribute('href')
        open_page(driver,urljoin(ORIGIN,next_url))


def collect_store(driver,store_id,store_name,categories,limit=None):
    label=prepare_store(driver,store_name)
    collected=datetime.now(ZoneInfo('Pacific/Auckland')).date().isoformat()
    count=0;seen=set()
    for category in categories:
        remaining=None if limit is None else limit-count
        if remaining is not None and remaining<=0:break
        for record in iter_products(driver,category['url'],label,remaining):
            key=(category['name'],record['source_product_id'])
            if key in seen:continue
            seen.add(key)
            record.update(source='woolworths',store_id=store_id,store_name=store_name,
                          actual_store_name=label,collected_date=collected,
                          category_id={'Egg':1,'Milk':2,'Meat':3}[category['name']],
                          category_name=category['name'],store_verified=True)
            yield record
            count+=1


def save_diagnostics(driver,directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    (directory/'page.html').write_text(driver.page_source,encoding='utf-8')
    (directory/'page.txt').write_text(driver.find_element(By.TAG_NAME,'body').text,encoding='utf-8')
    driver.save_screenshot(str(directory/'page.png'))
