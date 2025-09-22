import json
import time
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium_stealth import stealth


def init_webdriver():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    driver = webdriver.Chrome(options=options)
    stealth(driver, platform="Win32")
    return driver


def scrolldown(driver, deep):
    for _ in range(deep):
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


def get_all_pages(driver, base_url):
    all_products = {}
    page = 1
    while True:
        current_url = f"{base_url}?limit=108&p={page}"
        print(f"Парсим страницу {page}: {current_url}")
        products = get_mainpage_cards(driver, current_url)
        if not products:
            print("Достигнут конец каталога или товары не загружены.")
            break
        all_products.update(products)
        page += 1
    return all_products


def get_mainpage_cards(driver, url):
    driver.get(url)
    scrolldown(driver, 50)
    soup = BeautifulSoup(driver.page_source, "html.parser")
    product_divs = soup.find_all("div",
                                 class_="src-components-SSRLazyRender-SSRLazyRender__SSRLazyRender src-components-Products-Products__product")
    if not product_divs:
        print("На этой странице нет товаров.")
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
            amount_p = product.find("p", class_="src-components-Text-Text__text src-components-Text-Text__text_align_text_inherit src-components-Product-ProductBalance-ProductBalance__restAmount_productList src-components-Product-ProductBalance-ProductBalance__wrapText_productList")
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


if __name__ == "__main__":
    driver = init_webdriver()
    try:
        base_url = "https://kancleroptshilovo.ru/catalog-list"
        catalog_sections = get_catalog_sections(driver, base_url)
        all_data = {}
        for section_name, section_url in catalog_sections.items():
            print(f"Парсинг раздела каталога: {section_name} ({section_url})")
            base_section_url = section_url.replace("/catalog-list", "/catalog")
            products = get_all_pages(driver, base_section_url)
            all_data[section_name] = products
        with open("products.json", "w", encoding="utf-8") as f:
            json.dump(all_data, f, ensure_ascii=False, indent=4)
        print(f"Всего каталогов: {len(catalog_sections)}")
        print(f"Всего товаров: {sum(len(products) for products in all_data.values())}")
    finally:
        driver.quit()