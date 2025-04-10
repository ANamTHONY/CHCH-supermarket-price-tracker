from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import csv
import time
import Store_id

# **设置 Chrome 无头模式**
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--window-size=1920x1080")
chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36")

# **启动 WebDriver**
service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=chrome_options)

product_list = []

for store_id in Store_id.pak_ids:
    # **访问不同超市的促销页面**
    url = f"https://www.paknsave.co.nz/shop/deals"
    driver.get(url)
    print(f"🚀 正在抓取超市 ID {store_id[:1]} 的数据...")

    # **等待页面加载**
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, '//p[@data-testid="product-title"]'))
        )
    except:
        print(f"❌ 超市 ID {store_id} 没有数据")
        continue

    # **滚动页面，加载所有商品**
    for _ in range(10):  # 滚动 10 次，确保所有商品加载出来
        driver.execute_script("window.scrollBy(0, 1000);")
        time.sleep(2)

    # **获取商品信息**
    products = driver.find_elements(By.XPATH, '//div[@class="owfhtz0"]')

    for product in products:
        try:
            name = product.find_element(By.XPATH, ".//p[@data-testid='product-title']").text.strip()
            price = (
                product.find_element(By.XPATH, ".//p[@data-testid='price-dollars']").text.replace('.', '') + "." +
                product.find_element(By.XPATH, ".//p[@data-testid='price-cents']").text.strip()
            ) if product.find_elements(By.XPATH, ".//p[@data-testid='price-dollars']") else "价格未找到"

            size = product.find_element(By.XPATH, ".//p[@data-testid='product-subtitle']").text.strip() if product.find_elements(By.XPATH, ".//p[@data-testid='product-subtitle']") else "未知"

            product_list.append({
                "超市 ID": store_id,
                "name": name,
                "price": price,
                "size": size
            })

        except:
            continue

    print(f"✅ 超市 ID {store_id} 数据抓取完成！\n")

# **保存到 CSV**
with open("paknsave_christchurch_products.csv", "w", newline="", encoding="utf-8") as file:
    writer = csv.writer(file)
    writer.writerow(["超市 ID", "name", "price", "size"])
    for product in product_list:
        writer.writerow([product["超市 ID"], product["name"], product["price"], product["size"]])

print("✅ 基督城所有 PAK'nSAVE 数据已保存到 `paknsave_christchurch_products.csv`")

# **关闭浏览器**
driver.quit()
