import pymysql
import undetected_chromedriver as uc
from selenium.common import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import re
from datetime import datetime
from product_mapper import get_product_id

#  数据库连接
db = pymysql.connect(
    host="127.0.0.1",
    port=3306,
    user="root",
    password="0130",
    database="supermarket",
    charset="utf8mb4"
)
cursor = db.cursor()

store_map = { "001": "Woolworths Avonhead",
             "002": "Woolworths Ashburton",
             "003": "Woolworths Northlands",
             "004": "Woolworths Belfast",
             "005": "Woolworths Christchurch Airport",
             "006": "Woolworths Church Corner",
             "007": "Woolworths Colombo St",
             "008": "Woolworths Eastgate",
             "009": "Woolworths Ferrymead",
             "010": "Woolworths Hornby",
             "011": "Woolworths Moorhouse Ave",
             "012": "Woolworths New Brighton",
             "013": "Woolworths The Palms"
             }

categories = [
    {"name": "Egg", "url": "https://www.woolworths.co.nz/shop/browse/pantry/eggs"},
    {"name": "Milk", "url": "https://www.woolworths.co.nz/shop/browse/fridge-deli/milk/full-cream-milk"},
    {"name": "Milk", "url": "https://www.woolworths.co.nz/shop/browse/fridge-deli/milk/trim-light-milk"},
    {"name": "Meat", "url": "https://www.woolworths.co.nz/shop/browse/meat-poultry/beef"},
    {"name": "Meat", "url": "https://www.woolworths.co.nz/shop/browse/meat-poultry/lamb"}
]


def switch_store(driver, wait, store_name_list):
    try:
        change_location = wait.until(EC.element_to_be_clickable((By.LINK_TEXT, "Change location")))
        change_location.click()
    except Exception as e:
        print(f"找不到 Change location: {e}")
        return False

    try:
        pickup_radio = wait.until(EC.presence_of_element_located((By.ID, "method-pickup")))
        driver.execute_script("arguments[0].click();", pickup_radio)
        time.sleep(1)
    except Exception as e:
        print(f"切换 Pick up 失败: {e}")
        return False

    try:
        change_store_btn = wait.until(
            EC.element_to_be_clickable((By.XPATH, '//button[contains(text(), "Change store")]')))
        driver.execute_script("arguments[0].click();", change_store_btn)
    except Exception as e:
        print(f" 找不到 Change store: {e}")
        return False

    try:
        region_dropdown = wait.until(EC.element_to_be_clickable((By.ID, "area-dropdown-1")))
        region_dropdown.click()
        time.sleep(1)
        canterbury_option = wait.until(
            EC.element_to_be_clickable((By.XPATH, '//option[contains(text(), "Canterbury")]')))
        canterbury_option.click()
        time.sleep(2)
    except Exception as e:
        print(f"选择地区失败: {e}")
        return False

    for store_name in store_name_list:
        success = False
        for i in range(10):  # 最多滚动 10 次
            try:
                xpath = f'//strong[contains(text(), "{store_name}")]/ancestor::button'
                store_btn = wait.until(EC.presence_of_element_located((By.XPATH, xpath)))
                driver.execute_script("arguments[0].scrollIntoView(true);", store_btn)
                time.sleep(1)
                driver.execute_script("arguments[0].click();", store_btn)
                print(f" 切换到门店：{store_name}")
                success = True
                break
            except Exception:
                # 滚动 modal-contentSlot 容器尝试加载更多门店
                try:
                    modal = driver.find_element(By.CLASS_NAME, "modal-contentSlot")
                    driver.execute_script("arguments[0].scrollTop += 300;", modal)
                    time.sleep(1)
                except Exception as scroll_error:
                    print(f"滚动失败: {scroll_error}")
                    break  # 容器都找不到就退出

        if success:
            return True
        else:
            print(f" 找不到门店：{store_name}，尝试下一个...")

    print(" 所有候选门店都无法点击")
    return False


def scrape_products(driver, category_name, store_key):
    while True:
        # 页面滚动，加载所有商品
        last_height = driver.execute_script("return document.body.scrollHeight")
        while True:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1.5)
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height

        time.sleep(1)
        products = driver.find_elements(By.XPATH, '//div[contains(@class, "product-entry")]')
        print(f" 共找到 {len(products)} 个商品")

        for product in products:
            try:
                # name
                try:
                    name_elem = product.find_element(By.XPATH, './/h3[starts-with(@id, "product-")]')
                    name = name_elem.text.strip()
                    if not name or name.startswith('$'):
                        continue
                except Exception:
                    continue

                # total_quant
                matches = re.findall(r'\d+\.?\d*\s?(g|kg|ml|l|ea|pack)', name.lower())
                if matches:
                    match = re.findall(r'\d+\.?\d*\s?(?:g|kg|ml|l|ea|pack)', name.lower())
                    total_quant = match[-1].replace(" ", "").replace("pack", "pk")
                else:
                    total_quant = "NA"

                if category_name == "Meat":
                    total_quant = "kg"

                # 提取总价
                try:
                    price_container = product.find_element(By.XPATH,
                                                           './/h3[starts-with(@id, "product-") and contains(@id, "-price")]')
                    dollars = price_container.find_element(By.TAG_NAME, 'em').text.strip()
                    cents = price_container.find_element(By.TAG_NAME, 'span').text.strip()
                    total_price = float(f"{dollars}.{cents}")
                except Exception:
                    total_price = None

                # 单位价格
                try:
                    unit_price_raw = product.find_element(
                        By.XPATH, './/span[contains(@class, "cupPrice")]'
                    ).text.strip()

                    if not unit_price_raw.startswith('$'):
                        raise Exception("无单位价格")

                    unit_price_value, unit_price_unit = unit_price_raw.split('/')
                    unit_price = float(unit_price_value.replace('$', '').strip())
                    unit = unit_price_unit.strip().replace('1', '')
                except Exception:
                    unit_price = None
                    unit = "NA"

                # 促销标签
                try:
                    product.find_element(By.XPATH, './/span[contains(@class, "price--was")]')
                    is_promo = 1
                except NoSuchElementException:
                    try:
                        product.find_element(By.XPATH,
                                             './/div[contains(@class, "productStrap-title") and contains(text(), "LOW PRICE")]')
                        is_promo = 1
                    except NoSuchElementException:
                        is_promo = 0

                # product_id 映射
                product_id = get_product_id("cd", name, total_quant)

                if total_price is None:
                    total_price = unit_price

                print(
                    f"[{category_name}] {name} | 总价: {total_price}|总数量：{total_quant} | 单位价: {unit_price} 单位： {unit} | Promo: {is_promo}")

                # 插入数据库
                try:
                    sql = """
                    INSERT INTO fact_product_price (
                        product_id, store_id, category_id, total_price, total_quant,
                        unit, unit_price, original_name, collected_date, is_promo
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """
                    values = (
                        product_id,
                        store_key,
                        {"Egg": 1, "Milk": 2, "Meat": 3}.get(category_name),
                        total_price,
                        total_quant,
                        unit,
                        unit_price,
                        name,
                        datetime.today().strftime("%Y-%m-%d"),
                        is_promo
                    )

                    cursor.execute(sql, values)
                    db.commit()

                except Exception as e:
                    db.rollback()
                    print(f" 写入失败: {e}")

            except:
                continue

        print(f"分类 [{category_name}] 商品信息打印完毕\n")

        # 尝试翻页
        try:
            next_btn_li = driver.find_element(By.XPATH, '//li[contains(@class, "next")]')
            class_attr = next_btn_li.get_attribute("class")
            if "disabled" in class_attr:
                print("已到最后一页，停止翻页")
                break
            else:
                next_btn = next_btn_li.find_element(By.TAG_NAME, "a")
                driver.execute_script("arguments[0].click();", next_btn)
                time.sleep(3)  # 等待页面加载
        except NoSuchElementException:

            break
        except Exception as e:
            print(f"翻页出错: {e}")
            break



# 主流程
if __name__ == "__main__":
    driver = uc.Chrome(version_main=134, headless=False)
    driver.maximize_window()
    wait = WebDriverWait(driver, 15)

    for store_id in store_map:
        store_name = store_map[store_id]
        driver.get("https://www.woolworths.co.nz/shop/browse/pantry/eggs")
        wait = WebDriverWait(driver, 15)

        if switch_store(driver, wait, [store_name]):
            for cat in categories:
                time.sleep(2)
                print(f"\n 正在爬取分类：{cat['name']} - {cat['url']}")
                driver.get(cat["url"])
                wait = WebDriverWait(driver, 15)
                scrape_products(driver, cat["name"], store_id)
        else:
            print(f" 跳过门店：{store_name}")

    print("WoolWorths data successfully collected")
    print("====================================================================")
    driver.quit()
