import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from datetime import datetime
import time
import csv

from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ✅ 启动浏览器
driver = uc.Chrome(version_main=133, headless=False)
driver.maximize_window()

# ✅ 门店 ID 列表（可随时添加）
store_ids = [
    # New World Ilam
    "c6abac35-b75f-4a02-9b43-7ad5a7c7aa37",
    "81f807e9-1879-484c-b27e-ded56245c6a4"

]

# ✅ 商品分类路径
categories = [
    {"name": "Egg", "path": "fresh-foods-and-bakery/dairy--eggs/eggs"},
    {"name": "Milk", "path": "fresh-foods-and-bakery/dairy--eggs/fresh-milk"},
    {"name": "Meat", "path": "fresh-foods-and-bakery/butchery/fresh-beef--lamb"},
]

# ✅ 日期和初始化
today = datetime.today().strftime("%Y-%m-%d")
product_list = []
seen = set()

# ✅ 主逻辑
for store_id in store_ids:
    for cat in categories:
        url = f"https://www.newworld.co.nz/shop/category/{cat['path']}?storeId={store_id}&pg=1"
        print(f"\n🔎 正在爬取分类 {cat['name']} 的商品...")
        driver.get(url)
        time.sleep(5)

        # ✅ 这里加上门店切换弹窗处理
        try:
            popup_button = WebDriverWait(driver, 8).until(
                EC.element_to_be_clickable((By.XPATH, '//button[contains(@class, "_1n8ck8q1 _1n8ck8q3 _1n8ck8q0 _1n8ck8q7")]'))
            )
            driver.execute_script("arguments[0].click();", popup_button)
            print("✅ 成功点击切换门店按钮")
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.XPATH, '//div[@class="_1afq4wy0"]'))
            )
        except (NoSuchElementException, TimeoutException):
            print("⚠️ 没有弹窗按钮，或点击失败，跳过")

        while True:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1.5)

            products = driver.find_elements(By.XPATH, '//div[@class="_1afq4wy0"]')
            time.sleep(1.5)

            for p in products:
                try:
                    # ✅ 商品名
                    try:
                        name = p.find_element(By.XPATH, ".//p[@data-testid='product-title']").text.strip()
                    except NoSuchElementException:
                        name = "NA"

                    # ✅ 单位
                    try:
                        unit = p.find_element(By.XPATH, ".//p[@data-testid='product-subtitle']").text.strip()
                    except NoSuchElementException:
                        unit = "NA"

                    # ✅ 优先尝试促销价格（Club Deal）
                    price = None
                    is_promo = 0
                    try:
                        deal_block = p.find_element(By.XPATH, ".//div[@data-testid='decal']//div[@data-testid='decal-price']")
                        time.sleep(0.3)
                        dollars = deal_block.find_element(By.XPATH, ".//p[@data-testid='price-dollars']").text.strip()
                        cents = deal_block.find_element(By.XPATH, ".//p[@data-testid='price-cents']").text.strip()
                        if "." in dollars:
                            price = float(dollars + cents)
                        else:
                            price = float(f"{dollars}.{cents}")
                        is_promo = 1
                    except NoSuchElementException:
                        try:
                            normal_block = p.find_element(By.XPATH, ".//div[@data-testid='price']")
                            time.sleep(0.3)
                            dollars = normal_block.find_element(By.XPATH, ".//p[@data-testid='price-dollars']").text.strip()
                            cents = normal_block.find_element(By.XPATH, ".//p[@data-testid='price-cents']").text.strip()
                            if "." in dollars:
                                price = float(dollars)
                            else:
                                price = float(f"{dollars}.{cents}")
                            is_promo = 0
                        except NoSuchElementException:
                            print("⚠️ 找不到价格，跳过...")
                            continue

                    key = f"{store_id}-{cat['name']}-{name}-{price}"
                    if key in seen:
                        continue
                    seen.add(key)

                    product_list.append({
                        "store_id": store_id,
                        "category": cat["name"],
                        "name": name,
                        "price": price,
                        "unit": unit,
                        "is_promo": is_promo,
                        "collected_date": today
                    })

                    print(f"✅ {cat['name']}: {name} | ${price} | {unit} | Promo: {is_promo}")

                except Exception as e:
                    print(f"❌ 解析错误: {e}")
                    continue

            # ✅ 翻页
            try:
                next_btn = driver.find_element(By.XPATH, '//a[@data-testid="pagination-increment"]')
                driver.execute_script("arguments[0].click();", next_btn)
                print("➡️ 翻页中...")
                time.sleep(4)
            except NoSuchElementException:
                print("🚀 已到达最后一页")
                break

# ✅ 写入 CSV 文件
filename = "../newworld_products.csv"
with open(filename, "w", newline="", encoding="utf-8") as file:
    writer = csv.DictWriter(file, fieldnames=[
        "store_id", "category", "name", "price", "unit", "is_promo", "collected_date"
    ])
    writer.writeheader()
    for row in product_list:
        writer.writerow(row)

print(f"\n✅ 所有数据已保存到 {filename}")
driver.quit()
