"""Verify the actual store before collecting prices."""
import json
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def foodstuffs_identity(driver):
    data = json.loads(driver.find_element(By.ID, "__NEXT_DATA__").get_attribute("textContent"))
    return data["props"]["pageProps"]["fallback"]["default-store"]


def navigate_foodstuffs(driver, url, store_id, timeout=25):
    """Reattach storeId after legacy category redirects, then check ID and header."""
    # Legacy dairy category paths redirect and discard query parameters.
    url = url.replace("/fresh-foods-and-bakery/dairy--eggs/", "/fridge-deli-and-eggs/")
    driver.get(url)
    WebDriverWait(driver, timeout).until(
        lambda browser: browser.find_elements(By.CSS_SELECTOR, '[data-testid="product-title"]')
    )
    final = urlsplit(driver.current_url)
    query = dict(parse_qsl(final.query))
    if foodstuffs_identity(driver).get("id") != store_id and query.get("storeId") != store_id:
        query["storeId"] = store_id
        driver.get(urlunsplit(final._replace(query=urlencode(query))))

    def verified(browser):
        try:
            store = foodstuffs_identity(browser)
            if store.get("id") != store_id:
                return False
            # Header text is checked as well as server-rendered store metadata.
            header = browser.find_element(By.TAG_NAME, "body").text[:500]
            return store if store["name"] in header else False
        except (KeyError, ValueError):
            return False

    store = WebDriverWait(driver, timeout).until(verified)
    WebDriverWait(driver, timeout).until(
        lambda browser: browser.find_elements(By.CSS_SELECTOR, '[data-testid="product-title"]')
    )
    print(f"Verified shopping store: {store['name']} ({store['id']})", flush=True)
    return store


def select_woolworths_store(driver, store_name, timeout=30):
    """Select the pickup store using the current location dialog."""
    wait = WebDriverWait(driver, timeout)
    wait.until(lambda browser: browser.find_elements(
        By.CSS_SELECTOR, 'button[aria-label="Select an address"], button[aria-label^="Selected Store:"]'
    ))
    # Header has a location button after the Delivery/Pick up label.
    buttons = driver.find_elements(By.CSS_SELECTOR, 'button[aria-label="Select an address"]')
    if not buttons:
        buttons = driver.find_elements(By.CSS_SELECTOR, '[class*="fulfilment"] button, [class*="fulfillment"] button')
        buttons = [b for b in buttons if b.is_displayed() and "time" not in (b.get_attribute("aria-label") or "").lower()]
    if not buttons:
        buttons = driver.find_elements(By.XPATH, '//button[contains(@aria-label,"Woolworths")]')
    if not buttons:
        raise RuntimeError("Cannot find Woolworths header location button")
    button = next(b for b in buttons if b.is_displayed())
    wait.until(lambda browser: browser.execute_script(
        'return Object.keys(arguments[0]).some(k => k.startsWith("__reactProps$"));', button
    ))
    def open_dialog(browser):
        tabs=browser.find_elements(By.ID,'tab-1-pickup')
        if tabs and tabs[0].is_displayed() and tabs[0].is_enabled():return tabs[0]
        browser.execute_script("arguments[0].click();",button)
        return False
    pickup = WebDriverWait(driver,timeout,poll_frequency=2).until(open_dialog)
    wait.until(lambda browser: browser.execute_script(
        'return Object.keys(arguments[0]).some(k => k.startsWith("__reactProps$"));', pickup
    ))
    pickup.click()
    wait.until(lambda browser: browser.find_element(By.ID, "tab-1-pickup").get_attribute("aria-selected") == "true")
    search = wait.until(EC.visibility_of_element_located((By.ID, "pickup-store-search")))
    branch = re.sub(r"\s+(?:Street|St|Avenue|Ave)$", "", store_name.replace("Woolworths", "").strip(), flags=re.I)
    search.clear()
    search.send_keys(branch)

    def matching_option(browser):
        for option in browser.find_elements(By.CSS_SELECTOR, '#pickup-store-search-dropdown [role="option"]'):
            if option.is_displayed() and branch.lower() in option.text.splitlines()[0].lower():
                return option
        return False

    option = wait.until(matching_option)
    selected_label = option.text.splitlines()[0]
    option.click()
    wait.until(EC.element_to_be_clickable((By.XPATH, '//button[normalize-space()="Save and continue"]'))).click()
    wait.until(EC.invisibility_of_element_located((By.ID, "pickup-store-search")))
    wait.until(lambda browser: selected_label in browser.find_element(By.TAG_NAME, "body").text[:700])
    close = driver.find_elements(By.CSS_SELECTOR, 'button[aria-label="close"]')
    for button in close:
        if button.is_displayed():
            button.click()
            break
    print(f"Verified pickup store: {selected_label}", flush=True)
    return selected_label
