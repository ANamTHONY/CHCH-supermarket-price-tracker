import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException
import time
import csv
from datetime import datetime

# 启动 Chrome 驱动（规避 Cloudflare）
driver = uc.Chrome(version_main=133, headless=False)
driver.maximize_window()

# Christchurch 超市 ID 列表
christchurch_stores = [
    "4a279605-eaa8-470d-bcd4-0a9e3c9ab43b",
    "61dd754e-8525-4b9e-9e08-173389eea8a8",
    "8cd700ae-d96f-4761-bd7a-805d6b93536d",
    "be4c4780-218e-425a-a90f-63e21773572b",
    "dbca5e00-f7f9-43ae-91de-031ad16f8a92"
]

# 类别设置
categories = [
    {"name": "Egg", "path": "fresh-foods-and-bakery/dairy--eggs/eggs"},
    {"name": "Milk", "path": "fresh-foods-and-bakery/dairy--eggs/fresh-milk"},
    {"name": "Meat", "path": "fresh-foods-and-bakery/butchery/fresh-beef--lamb"}
]

# 主爬虫函数
def get_store_products(store_id, category_name, category_path):
    url = f"https://www.paknsave.co.nz/shop/category/{category_path}?storeId={store_id}"
    print(f"🌐 正在访问: {url}")
    driver.get(url)
    time.sleep(5)

    # 等待超市切换成功
    current_url = driver.current_url
    try:
        popup_button = WebDriverWait(driver, 8).until(
            EC.element_to_be_clickable((By.XPATH, '//button[contains(@class, "_1c9qavo0 _1c9qavo2 _1c9qavo8")]'))
        )
        driver.execute_script("arguments[0].click();", popup_button)
        print("✅ 成功点击切换门店按钮")

        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, '//div[@class="owfhtz0"]'))
        )

    except (NoSuchElementException, TimeoutException):
        print("⚠️ 没有弹窗按钮，或点击失败，跳过")

    # 确保商品数据加载
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, '//div[@class="owfhtz0"]'))
        )
        print("✅ 商品数据已加载！")
    except TimeoutException:
        print("❌ 页面加载超时，重新刷新页面")
        driver.refresh()
        time.sleep(10)

    # 商品爬取
    product_list = []
    seen_products = set()
    today = datetime.today().strftime("%Y-%m-%d")

    while True:
        time.sleep(2)
        products = driver.find_elements(By.XPATH, '//div[@class="owfhtz0"]')

        for product in products:
            try:
                # 检查促销标识
                try:
                    promo_flag = product.find_element(By.XPATH, './/div[contains(@class, "wgonz71 wgonz72 wgonz74")]')
                    is_promo = 1
                except NoSuchElementException:
                    is_promo = 0

                name = product.find_element(By.XPATH, ".//p[@data-testid='product-title']").text.strip()
                try:
                    price = (
                        product.find_element(By.XPATH, ".//p[@data-testid='price-dollars']").text.replace('.', '') +
                        "." +
                        product.find_element(By.XPATH, ".//p[@data-testid='price-cents']").text.strip()
                    )
                except NoSuchElementException:
                    price = "NA"

                try:
                    size = product.find_element(By.XPATH, ".//p[@data-testid='product-subtitle']").text.strip()
                except NoSuchElementException:
                    size = "NA"

                product_key = f"{store_id}-{category_name}-{name}-{price}"
                if product_key not in seen_products:
                    seen_products.add(product_key)
                    product_list.append({
                        "storeID": store_id,
                        "category": category_name,
                        "name": name,
                        "price": price,
                        "size": size,
                        "collected_date": today,
                        "promo": is_promo
                    })
                    print(f"✅ [{category_name}] {name} | ${price} | {size} | {today} | Promo: {is_promo}")

            except NoSuchElementException:
                continue

        # 翻页
        try:
            next_button = driver.find_element(By.XPATH, '//a[@data-testid="pagination-increment"]')
            driver.execute_script("arguments[0].click();", next_button)
            print("➡️ 翻页中...")
            time.sleep(5)
        except NoSuchElementException:
            print("🚀 已到达最后一页")
            break

    return product_list

# 主逻辑
all_products = []
for store_id in christchurch_stores:
    for cat in categories:
        print(f"📦 爬取 {cat['name']} @ store {store_id}")
        store_products = get_store_products(store_id, cat["name"], cat["path"])
        all_products.extend(store_products)

# 保存为 CSV 文件
filename = "paknsave_daily.csv"
with open(filename, "w", newline="", encoding="utf-8") as file:
    writer = csv.writer(file)
    writer.writerow(["storeID", "category", "name", "price", "size", "collected_date", "promo"])
    for product in all_products:
        writer.writerow([
            product["storeID"],
            product["category"],
            product["name"],
            product["price"],
            product["size"],
            product["collected_date"],
            product["promo"]
        ])

print(f"✅ 所有数据已保存到 {filename}")
driver.quit()
