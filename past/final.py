import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException
import time
import csv

# **使用 undetected_chromedriver 规避 Cloudflare**
driver = uc.Chrome(version_main=133, headless=False)
driver.maximize_window()

christchurch_stores = [
    "4a279605-eaa8-470d-bcd4-0a9e3c9ab43b",
    "61dd754e-8525-4b9e-9e08-173389eea8a8",
    "8cd700ae-d96f-4761-bd7a-805d6b93536d",
    "be4c4780-218e-425a-a90f-63e21773572b",
    "dbca5e00-f7f9-43ae-91de-031ad16f8a92"
]

def get_store_products(store_id):
    url = f"https://www.paknsave.co.nz/shop/deals?storeId={store_id}"
    driver.get(url)
    time.sleep(5)  # **确保页面加载**
    driver.refresh()  # **强制刷新**
    time.sleep(5)

    # **等待超市切换成功**
    current_url = driver.current_url
    try:
        popup_button = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, '//button[contains(text(), "Change to PAK")]'))
        )
        popup_button.click()
        print("✅ 已自动切换超市！")
        WebDriverWait(driver, 10).until(lambda d: d.current_url != current_url)
        print(f"✅ URL 切换成功: {driver.current_url}")
    except (NoSuchElementException, TimeoutException):
        print("✅ 没有弹窗，继续执行")

    # **确保商品数据加载**
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, '//div[@class="owfhtz0"]'))
        )
        print("✅ 商品数据已加载！")
    except TimeoutException:
        print("❌ 页面加载超时，重新刷新页面")
        driver.refresh()
        time.sleep(10)

    # **爬取第一页商品数据**
    product_list = []
    products = driver.find_elements(By.XPATH, '//div[@class="owfhtz0"]')
    for product in products:
        try:
            name = product.find_element(By.XPATH, ".//p[@data-testid='product-title']").text.strip()
            try:
                price = (
                        product.find_element(By.XPATH, ".//p[@data-testid='price-dollars']").text.replace('.', '') + "." +
                        product.find_element(By.XPATH, ".//p[@data-testid='price-cents']").text.strip()
                )
            except NoSuchElementException:
                price = "NA"
            try:
                size = product.find_element(By.XPATH, ".//p[@data-testid='product-subtitle']").text.strip()
            except NoSuchElementException:
                size = "NA"

            product_list.append({"storeID": store_id, "name": name, "price": price, "size": size})
            print(f"✅ StoreID: {store_id} | 商品: {name} | 价格: {price} | 规格: {size}")
        except NoSuchElementException:
            continue

    # **注释掉翻页代码**
    while True:
        try:
            next_button = driver.find_element(By.XPATH, '//a[@data-testid="pagination-increment"]')
            driver.execute_script("arguments[0].click();", next_button)
            print("➡️ 翻到下一页...")
            time.sleep(3)
        except NoSuchElementException:
            print("🚀 已到达最后一页！")
            break

    return product_list

# **运行主函数**
all_products = []
for store_id in christchurch_stores:
    store_products = get_store_products(store_id)
    all_products.extend(store_products)

# **保存到 CSV**
with open("paknsave_products.csv", "w", newline="", encoding="utf-8") as file:
    writer = csv.writer(file)
    writer.writerow(["storeID", "name", "price", "size"])
    for product in all_products:
        writer.writerow([product["storeID"], product["name"], product["price"], product["size"]])

print("✅ 数据已保存到 paknsave_products.csv")

driver.quit()
