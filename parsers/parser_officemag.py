import time
import psycopg2
from psycopg2 import sql
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium_stealth import stealth

def init_webdriver():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    driver = webdriver.Chrome(options=options)
    stealth(driver, platform="Win32")
    return driver

def scrolldown(driver, deep=3, delay=0.5):
    for _ in range(deep):
        driver.execute_script('window.scrollBy(0, 500)')
        time.sleep(delay)

def get_sections_from_url(driver, url):
    driver.get(url)
    scrolldown(driver, 2)
    soup = BeautifulSoup(driver.page_source, "html.parser")
    sections = {}
    li_tags = soup.select("li > a[href^='/catalog/'] > strong")
    for strong_tag in li_tags:
        name = strong_tag.get_text(strip=True)
        href = strong_tag.parent.get("href")
        if name and href:
            full_url = f"https://www.officemag.ru{href}"
            sections[name] = full_url
    return sections

def get_leaf_subsubsections(driver, top_url):
    subsubsections = {}
    visited = set()
    stack = list(get_sections_from_url(driver, top_url).values())
    for sub_url in stack:
        child_sections = get_sections_from_url(driver, sub_url)
        for name, url in child_sections.items():
            if url not in visited:
                subsubsections[name] = url
                visited.add(url)
    return subsubsections

def parse_products_from_page(driver, base_url, total_count=0, max_products=None):
    page = 1
    products = {}
    idx_global = 0
    while True:
        if max_products is not None and total_count >= max_products:
            break
        url = f"{base_url}?PAGEN_1={page}" if page > 1 else base_url
        driver.get(url)
        time.sleep(2)
        scrolldown(driver, 6, delay=0.8)
        time.sleep(2)
        soup = BeautifulSoup(driver.page_source, "html.parser")
        items = soup.find_all("div", class_="listItem__content")
        if not items:
            print(f"Страница {page} пуста, заканчиваем.")
            break
        print(f"Парсинг страницы {page}, найдено товаров: {len(items)}")
        page_count = 0
        for item in items:
            if max_products is not None and total_count >= max_products:
                break
            try:
                name_tag = item.select_one("div.nameWrapper a")
                name = name_tag.text.strip() if name_tag else "Без названия"
                product_link_tag = item.select_one("a.listItemPhoto__link")
                relative_url = product_link_tag.get("href") if product_link_tag else "#"
                product_url = f"https://www.officemag.ru{relative_url}"
                info_ul = item.find("ul", class_="info")
                description = " ".join(li.get_text(strip=True) for li in info_ul.find_all("li")) if info_ul else ""
                price_rubles_tag = item.select_one("span.Price__count")
                price_kop_tag = item.select_one("span.Price__penny")
                rubles = price_rubles_tag.get_text(strip=True) if price_rubles_tag else "Цена не указана"
                kop = price_kop_tag.get_text(strip=True) if price_kop_tag else "00"
                price = f"{rubles},{kop}"
                availability_tag = item.find("td", class_="AvailabilityBox AvailabilityBox--green")
                amount = availability_tag.get_text(strip=True) if availability_tag else "Количество не указано"
                img_tag = item.find("img", class_="ProductPhoto__img listItemPhoto__img js-productPhotoMain")
                image_url = img_tag["src"] if img_tag else "Фото не найдено"
                product_key = f"{product_url}_prod_{idx_global}"
                idx_global += 1

                products[product_key] = {
                    "name": name,
                    "description": description,
                    "price": price,
                    "amount": amount,
                    "image_url": image_url,
                    "product_url": product_url
                }

                total_count += 1
                page_count += 1
            except Exception as e:
                print(f"Ошибка при парсинге товара: {e}")
        print(f"Страница {page} обработана, добавлено товаров: {page_count}, всего спаршено: {total_count}")
        page += 1
    return products, total_count

def build_catalog_with_products(driver, base_url, max_products=None):
    all_data = {}
    total_count = 0
    top_sections = get_sections_from_url(driver, base_url)
    for i, (section_name, section_url) in enumerate(top_sections.items(), 1):
        if max_products is not None and total_count >= max_products:
            break
        print(f"\n[{i}/{len(top_sections)}] Главный раздел: {section_name}")
        leaf_sections = get_leaf_subsubsections(driver, section_url)
        if not leaf_sections:
            print("Нет подподразделов, пропускаем.")
            continue
        for leaf_name, leaf_url in leaf_sections.items():
            if max_products is not None and total_count >= max_products:
                break
            print(f"Парсинг товаров из подподраздела: {leaf_name}")
            products, total_count = parse_products_from_page(driver, leaf_url, total_count, max_products)
            all_data.setdefault(section_name, {}).update(products)
    return all_data

def save_to_postgres(data, table_name="officemag_products"):
    conn = psycopg2.connect(
        dbname="mydatabase",
        user="myuser",
        password="mypassword",
        host="localhost",
        port="5432"
    )
    cur = conn.cursor()
    cur.execute(sql.SQL(f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            id SERIAL PRIMARY KEY,
            name TEXT,
            description TEXT,
            price TEXT,
            amount TEXT,
            image_url TEXT,
            product_url TEXT
        )
    """))
    for section, products in data.items():
        for _, product in products.items():
            cur.execute(
                sql.SQL(f"""
                    INSERT INTO {table_name} (name, description, price, amount, image_url, product_url)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """),
                (
                    product["name"],
                    product["description"],
                    product["price"],
                    product["amount"],
                    product["image_url"],
                    product["product_url"]
                )
            )
    conn.commit()
    cur.close()
    conn.close()
    print(f"Данные сохранены в PostgreSQL таблицу '{table_name}'")

if __name__ == "__main__":
    driver = init_webdriver()
    try:
        base_url = "https://www.officemag.ru/catalog/"
        data = build_catalog_with_products(driver, base_url, max_products=None)
        save_to_postgres(data, table_name="officemag_products")
        print("\nГотово! Данные сохранены в PostgreSQL")
    finally:
        driver.quit()