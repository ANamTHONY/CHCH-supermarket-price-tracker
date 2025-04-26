import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from datetime import datetime
import pymysql
import time
import re
from product_mapper import get_product_id

# connection
db = pymysql.connect(
    host="127.0.0.1",
    port=3306,
    user="root",
    password="0130",
    database="supermarket",
    charset="utf8mb4"
)
cursor = db.cursor()

# drive
driver = uc.Chrome( headless=False)
driver.maximize_window()

# ID list
christchurch_stores = [
    "4a279605-eaa8-470d-bcd4-0a9e3c9ab43b",
    "61dd754e-8525-4b9e-9e08-173389eea8a8",
    "8cd700ae-d96f-4761-bd7a-805d6b93536d",
    "be4c4780-218e-425a-a90f-63e21773572b",
    "dbca5e00-f7f9-43ae-91de-031ad16f8a92"
]

# Categories
categories = [
    {"name": "Egg", "path": "fresh-foods-and-bakery/dairy--eggs/eggs"},
    {"name": "Milk", "path": "fresh-foods-and-bakery/dairy--eggs/fresh-milk"},
    {"name": "Meat", "path": "fresh-foods-and-bakery/butchery/fresh-beef--lamb"}
]

# main
def get_store_products(store_id, category_name, category_path):
    url = f"https://www.paknsave.co.nz/shop/category/{category_path}?storeId={store_id}"
    print(f"正在访问: {url}")
    driver.get(url)
    time.sleep(5)

    # 点击切换超市按钮
    try:
        popup_button = WebDriverWait(driver, 8).until(
            EC.element_to_be_clickable((By.XPATH, '//button[contains(@class, "_1c9qavo0 _1c9qavo2 _1c9qavo8")]'))
        )
        driver.execute_script("arguments[0].click();", popup_button)

        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, '//div[@class="owfhtz0"]'))
        )
    except (NoSuchElementException, TimeoutException):
        print("没有弹窗按钮，跳过")

    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, '//div[@class="owfhtz0"]'))
        )

    except TimeoutException:

        driver.refresh()
        time.sleep(10)

    seen_products = set()
    today = datetime.today().strftime("%Y-%m-%d")
    category_map = {"Egg": 1, "Milk": 2, "Meat": 3}
    category_id = category_map.get(category_name)

    while True:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        products = driver.find_elements(By.XPATH, '//div[@class="owfhtz0"]')

        for product in products:
            try:
                # 促销判断
                try:
                    promo_flag = product.find_element(By.XPATH, './/div[contains(@class, "wgonz71")]')
                    is_promo = 1
                except NoSuchElementException:
                    is_promo = 0
                # name
                name = product.find_element(By.XPATH, ".//p[@data-testid='product-title']").text.strip()

                #price
                try:
                    price = (
                        product.find_element(By.XPATH, ".//p[@data-testid='price-dollars']").text.replace('.', '') +
                        "." +
                        product.find_element(By.XPATH, ".//p[@data-testid='price-cents']").text.strip()
                    )
                    price = float(price)
                except NoSuchElementException:
                    price = None

                #unit
                try:
                    unit = product.find_element(By.XPATH, ".//p[@data-testid='price-per']").text.strip()

                except NoSuchElementException:
                    continue

                #total_quant
                try:
                    total_quant_text = product.find_element(By.XPATH, ".//p[@data-testid='product-subtitle']").text.strip()
                except NoSuchElementException:
                    total_quant_text = "NA"
                match = re.search(r'(\d+(?:\.\d+)?)(?:pk|ea|g|kg|L|ml)?', total_quant_text.lower())
                if match:
                    total_quant = float(match.group(1))
                else:
                    total_quant = None



                product_key = f"{store_id}-{category_name}-{name}-{price}"
                if product_key in seen_products:
                    continue
                seen_products.add(product_key)


                # 计算单位价格
                try:
                    unit_price_calc = round(price / total_quant, 2) if price and total_quant else None
                except ZeroDivisionError:
                    unit_price_calc = None

                # id
                product_id = get_product_id("pak", name, total_quant_text)

                # 插入数据库
                sql = """
                INSERT INTO fact_product_price (
                    product_id, store_id, category_id, total_price, total_quant,unit,unit_price,original_name, collected_date, is_promo
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                values = (
                    product_id,  # product_id 可以后续补
                    store_id,
                    category_id,
                    price,
                    total_quant_text,
                    unit,
                    unit_price_calc,
                    name,
                    today,
                    is_promo
                )

                cursor.execute(sql, values)
                db.commit()
                print(f"✅ 插入成功: {name} | ${price} | Promo: {is_promo}")

            except Exception as e:
                print(f"❌ 插入失败: {e}")
                db.rollback()
                continue

        # 翻页
        try:
            next_button = driver.find_element(By.XPATH, '//a[@data-testid="pagination-increment"]')
            driver.execute_script("arguments[0].click();", next_button)

            time.sleep(5)
        except NoSuchElementException:

            break

# 主逻辑
for store_id in christchurch_stores:
    for cat in categories:
        time.sleep(5)
        print(f" 爬取 {cat['name']} @ store {store_id}")
        get_store_products(store_id, cat["name"], cat["path"])

# 关闭连接
cursor.close()
db.close()
driver.quit()
print("PAKnSAVE data successfully collected")
print("====================================================================")
