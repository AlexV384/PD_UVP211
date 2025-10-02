import time
import sqlite3
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium_stealth import stealth

DB_FILE = "data.db"


def init_webdriver():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    driver = webdriver.Chrome(options=options)
    stealth(driver, platform="Win32")
    return driver


def scrolldown(driver, deep):
    for i in range(deep):
        driver.execute_script('window.scrollBy(0, 500)')
        time.sleep(1)


def get_catalog_sections(driver, base_url):
    driver.get(base_url)
    scrolldown(driver, 20)
    soup = BeautifulSoup(driver.page_source, "html.parser")
    sections = soup.find_all(
        "a",
        class_="src-components-CatalogList-Block-Block__titleLink src-components-CatalogList-Block-Block__titleLink_header"
    )
    catalog_urls = {}
    for section in sections:
        section_href = section.get("href")
        section_url = f"https://kancleroptshilovo.ru{section_href}"
        section_name_tag = section.find_next("p", class_="src-components-Text-Text__text")
        section_name = section_name_tag.text.strip() if section_name_tag else "Неизвестный раздел"
        catalog_urls[section_name] = section_url
    return catalog_urls


def get_mainpage_cards(driver, url):
    driver.get(url)
    scrolldown(driver, 50)
    soup = BeautifulSoup(driver.page_source, "html.parser")
    product_divs = soup.find_all(
        "div",
        class_="src-components-SSRLazyRender-SSRLazyRender__SSRLazyRender src-components-Products-Products__product"
    )
    if not product_divs:
        return {}
    products = {}
    for idx, product in enumerate(product_divs):
        try:
            name_a = product.find("a", class_="src-components-Product-ProductList-ProductList__name")
            name_span = name_a.find("span", itemprop="name") if name_a else None
            name = name_span.text.strip() if name_span else "Неизвестно"
            description_meta = product.find("meta", itemprop="description")
            description = description_meta["content"].strip() if description_meta else "Нет описания"
            price_span = product.find("span", itemprop="lowPrice")
            price = price_span.text.strip() if price_span else "Цена не указана"
            amount_p = product.find(
                "p",
                class_="src-components-Text-Text__text src-components-Text-Text__text_align_text_inherit src-components-Product-ProductBalance-ProductBalance__restAmount_productList src-components-Product-ProductBalance-ProductBalance__wrapText_productList"
            )
            amount = amount_p.text.strip() if amount_p else "Количество не указано"
            link_tag = product.find("a", itemprop="url")
            product_url = f"https://kancleroptshilovo.ru{link_tag['href']}" if link_tag else "URL не найден"
            image_tag = product.find("img", class_="src-components-Image-Image__preview src-components-Image-Image__imgContain")
            image_url = image_tag["src"] if image_tag else "Фото не найдено"
            product_key = f"{product_url}_prod_{idx}"
            products[product_key] = {
                "name": name,
                "description": description,
                "price": price,
                "amount": amount,
                "image_url": image_url,
                "product_url": product_url
            }
        except Exception as e:
            print(f"Ошибка при обработке товара {idx}: {e}")
    return products


def build_catalog_with_products(driver, base_url, max_products=None):
    all_data = {}
    total_count = 0
    catalog_sections = get_catalog_sections(driver, base_url)
    for section_name, section_url in catalog_sections.items():
        if max_products is not None and total_count >= max_products:
            break
        print(f"\nПарсинг раздела: {section_name} ({section_url})")
        base_section_url = section_url.replace("/catalog-list", "/catalog")
        page = 1
        while True:
            if max_products is not None and total_count >= max_products:
                break
            current_url = f"{base_section_url}?limit=108&p={page}"
            print(f"Парсим страницу {page}: {current_url}")
            products = get_mainpage_cards(driver, current_url)
            if not products:
                break
            if max_products is not None and total_count + len(products) > max_products:
                needed = max_products - total_count
                products = dict(list(products.items())[:needed])
            all_data.setdefault(section_name, {}).update(products)
            total_count += len(products)
            print(f"Добавлено товаров: {len(products)}, всего спаршено: {total_count}")
            page += 1
    print(f"\nОбщее количество товаров спаршено: {total_count}")
    return all_data


def save_to_sqlite(data, table_name="kancleroptshilovo_products"):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT,
            name TEXT,
            description TEXT,
            price TEXT,
            amount TEXT,
            image_url TEXT,
            product_url TEXT
        )
    """)
    for section, products in data.items():
        for _, product in products.items():
            cur.execute(f"""
                INSERT INTO {table_name} (category, name, description, price, amount, image_url, product_url)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                section,
                product["name"],
                product["description"],
                product["price"],
                product["amount"],
                product["image_url"],
                product["product_url"]
            ))
    conn.commit()
    conn.close()
    print(f"\nДанные сохранены в SQLite таблицу '{table_name}' ({DB_FILE})")


if __name__ == "__main__":
    driver = init_webdriver()
    try:
        base_url = "https://kancleroptshilovo.ru/catalog-list"
        data = build_catalog_with_products(driver, base_url, max_products=None)
        save_to_sqlite(data, table_name="kancleroptshilovo_products")
    finally:
        driver.quit()
