import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from datetime import datetime
import pymysql
import time
import re

# connection
db = pymysql.connect(
    host="localhost",
    port=3306,
    user="root",
    password="0130",
    database="supermarket",
    charset="utf8mb4"
)
cursor = db.cursor()

# Chrome drive
driver = uc.Chrome(version_main=133, headless=False)
driver.maximize_window()

# ID list
christchurch_stores = [
    "c6abac35-b75f-4a02-9b43-7ad5a7c7aa37",
    "81f807e9-1879-484c-b27e-ded56245c6a4"
]

# Categories
categories = [
    {"name": "Egg", "path": "fresh-foods-and-bakery/dairy--eggs/eggs"},
    {"name": "Milk", "path": "fresh-foods-and-bakery/dairy--eggs/fresh-milk"},
    {"name": "Meat", "path": "fresh-foods-and-bakery/butchery/fresh-beef--lamb"},
]

# scrape
def get_store_products(store_id, category_name, category_path):
    url = f"https://www.newworld.co.nz/shop/category/{category_path}?storeId={store_id}"
    print(f" 正在访问: {url}")
    driver.get(url)
    time.sleep(5)

    # 点击切换超市按钮
    try:
        popup_button = WebDriverWait(driver, 8).until(
            EC.element_to_be_clickable((By.XPATH, '//button[contains(@class, "_1n8ck8q1 _1n8ck8q3 _1n8ck8q0 _1n8ck8q7")]'))
        )
        driver.execute_script("arguments[0].click();", popup_button)
        time.sleep(2)
        # print("成功点击切换门店按钮")
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, '//div[@class="_1afq4wy0"]'))
        )
    except (NoSuchElementException, TimeoutException):
        print("没有弹窗按钮，或点击失败，跳过")

    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, '//div[@class="_1afq4wy0"]'))
        )
        # print("✅ 商品数据已加载！")
    except TimeoutException:
        # print("❌ 页面加载超时，重新刷新页面")
        driver.refresh()
        time.sleep(10)

    seen_products = set()
    today = datetime.today().strftime("%Y-%m-%d")
    category_map = {"Egg": 1, "Milk": 2, "Meat": 3}
    category_id = category_map.get(category_name)

    while True:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(0.5)
        products = driver.find_elements(By.XPATH, '//div[@class="_1afq4wy0"]')

        for p in products:
            try:
                # name
                try:
                    name = p.find_element(By.XPATH, ".//p[@data-testid='product-title']").text.strip()
                except NoSuchElementException:
                    name = "NA"

                # total_quant
                try:
                    total_quant_text = p.find_element(By.XPATH, ".//p[@data-testid='product-subtitle']").text.strip()
                except NoSuchElementException:
                    total_quant_text = "NA"
                match = re.search(r'(\d+(?:\.\d+)?)(?:pk|ea|g|kg|L|ml)?', total_quant_text.lower())
                if match:
                    total_quant = float(match.group(1))
                else:
                    total_quant = None

                # unit
                try:
                    unit = p.find_element(By.XPATH, ".//p[@data-testid='product-subtitle']").text.strip()
                except NoSuchElementException:
                    unit = "NA"



                # 优先尝试促销价格（Club Deal）
                price = None
                is_promo = 0
                try:
                    # Club Deal 优先判断（decal-price 在 product-decal-4000 中）
                    deal_block = p.find_element(By.XPATH,
                                                ".//div[@data-testid='product-decal-4000']//div[@data-testid='decal-price']")
                    time.sleep(0.1)
                    dollars = deal_block.find_element(By.XPATH, ".//p[@data-testid='price-dollars']").text.strip()
                    cents = deal_block.find_element(By.XPATH, ".//p[@data-testid='price-cents']").text.strip()
                    if "." in dollars:
                        price = float(dollars + cents)
                    else:
                        price = float(f"{dollars}.{cents}")
                    is_promo = 1
                except NoSuchElementException:
                    try:
                        # Super Saver 判断（没有 deal-price，但有 product-decal-3000）
                        saver_block = p.find_element(By.XPATH, ".//div[@data-testid='product-decal-3000']")
                        time.sleep(0.1)
                        dollars = p.find_element(By.XPATH,
                                                 ".//div[@data-testid='price']//p[@data-testid='price-dollars']").text.strip()
                        cents = p.find_element(By.XPATH,
                                               ".//div[@data-testid='price']//p[@data-testid='price-cents']").text.strip()
                        if "." in dollars:
                            price = float(dollars + cents)
                        else:
                            price = float(f"{dollars}.{cents}")
                        is_promo = 1
                    except NoSuchElementException:
                        try:
                            #  普通价格
                            normal_block = p.find_element(By.XPATH, ".//div[@data-testid='price']")
                            time.sleep(0.1)
                            dollars = normal_block.find_element(By.XPATH,
                                                                ".//p[@data-testid='price-dollars']").text.strip()
                            cents = normal_block.find_element(By.XPATH, ".//p[@data-testid='price-cents']").text.strip()
                            if "." in dollars:
                                price = float(dollars + cents)
                            else:
                                price = float(f"{dollars}.{cents}")
                            is_promo = 0
                        except NoSuchElementException:
                            print("找不到价格，跳过...")
                            continue
                # 计算单位价格
                try:
                    unit_price_calc = round(price / total_quant, 2) if price and total_quant else None
                except ZeroDivisionError:
                    unit_price_calc = None

                product_key = f"{store_id}-{category_name}-{name}-{price}"
                if product_key in seen_products:
                    continue
                seen_products.add(product_key)

                # 插入数据库
                sql = """
                INSERT INTO fact_product_price (
                    product_id, store_id, category_id, total_price, total_quant,unit,unit_price,
                    original_name, collected_date, is_promo
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                values = (
                    None,  # product_id 可以后续补
                    store_id,
                    category_id,
                    price,
                    total_quant,
                    unit,
                    unit_price_calc,
                    name,
                    today,
                    is_promo
                )

                cursor.execute(sql, values)
                db.commit()
                print(f" 插入成功: {name} | ${price} | Promo: {is_promo}")

            except Exception as e:
                print(f"❌ 插入失败: {e}")
                db.rollback()
                continue

        # 翻页
        try:
            next_button = driver.find_element(By.XPATH, '//a[@data-testid="pagination-increment"]')
            driver.execute_script("arguments[0].click();", next_button)
            # print("翻页中...")
            time.sleep(5)
        except NoSuchElementException:
            # print("已到达最后一页")
            break

# main
for store_id in christchurch_stores:
    for cat in categories:
        time.sleep(5)
        print(f" 爬取 {cat['name']} @ store {store_id}")
        get_store_products(store_id, cat["name"], cat["path"])


cursor.close()
db.close()
driver.quit()
print("NewWorld data successfully collected")
print("====================================================================")
