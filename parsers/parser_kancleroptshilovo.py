import time
import sqlite3
import threading
from typing import Dict, List, Tuple
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium_stealth import stealth
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

DB_FILE = "data.db"
MAX_THREADS = 4
DB_WRITE_TIMEOUT = 30
POLL_INTERVAL = 0.8
SCROLL_PAUSE = 0.6
STABILITY_CHECKS = 5
PAGE_FILL_RETRIES = 10
PAGE_FILL_WAIT = 1.0
DB_LOCK = threading.Lock()
MAIN_SECTION_SELECTOR = (
    "a.src-components-CatalogList-Block-Block__titleLink"
    ".src-components-CatalogList-Block-Block__titleLink_header"
)
SUBSECTION_LINK_SELECTOR = "a.src-components-CatalogList-Block-Block__titleLink"
PRODUCT_NODE_SELECTORS = [
    'div[class*="Products-Products__product"]',
    'div[class*="Products__product"]',
]

def create_driver() -> webdriver.Chrome:
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--log-level=3")
    driver = webdriver.Chrome(options=options)
    stealth(driver, platform="Win32")
    return driver


def safe_scroll(driver: webdriver.Chrome, px: int) -> None:
    try:
        driver.execute_script(f"window.scrollBy(0, {px});")
    except Exception:
        pass


def wait_until_products_stable(driver: webdriver.Chrome, min_wait: float = 1.0, max_wait: float = 45.0) -> int:
    last_count = 0
    stable_rounds = 0
    start = time.time()
    while time.time() - start < max_wait:
        html = driver.page_source
        soup = BeautifulSoup(html, "html.parser")
        nodes = []
        for sel in PRODUCT_NODE_SELECTORS:
            nodes.extend(soup.select(sel))
        count = len(nodes)
        if count == last_count and count > 0:
            stable_rounds += 1
        else:
            stable_rounds = 0
            last_count = count
        if stable_rounds >= STABILITY_CHECKS:
            break
        safe_scroll(driver, 1000)
        time.sleep(POLL_INTERVAL)
    time.sleep(min_wait)
    return last_count


def ensure_images_loaded(driver: webdriver.Chrome, per_node_timeout: float = 1.5, per_step_sleep: float = 0.08) -> None:
    try:
        count = driver.execute_script(
            "return document.querySelectorAll('div[class*=\"Products-Products__product\"], div[class*=\"Products__product\"]').length;"
        )
    except Exception:
        return
    if not count:
        return
    for i in range(count):
        try:
            driver.execute_script(
                f"""
                var nodes = document.querySelectorAll('div[class*="Products-Products__product"], div[class*="Products__product"]');
                if (nodes.length > {i}) nodes[{i}].scrollIntoView({{block: 'center'}});
                """
            )
        except Exception:
            pass
        start = time.time()
        while time.time() - start < per_node_timeout:
            try:
                src = driver.execute_script(
                    f"""
                    var nodes = document.querySelectorAll('div[class*="Products-Products__product"], div[class*="Products__product"]');
                    if (nodes.length <= {i}) return '';
                    var el = nodes[{i}];
                    var img = el.querySelector('img');
                    if (!img) return '';
                    var s = img.getAttribute('src') || img.getAttribute('data-src') || img.getAttribute('data-lazy') || img.getAttribute('data-original') || img.getAttribute('data-srcset') || '';
                    if (!s && img.hasAttribute('srcset')) s = img.getAttribute('srcset');
                    return s || '';
                    """
                )
                if src and str(src).strip():
                    break
            except Exception:
                pass
            time.sleep(0.06)
        time.sleep(per_step_sleep)
    time.sleep(0.25)


def discover_subsections(driver: webdriver.Chrome, base_url: str) -> List[Tuple[str, str]]:
    driver.get(base_url)
    time.sleep(2)
    soup = BeautifulSoup(driver.page_source, "html.parser")
    main_sections = soup.select(MAIN_SECTION_SELECTOR)
    subsections: List[Tuple[str, str]] = []
    for main in main_sections:
        href = main.get("href")
        if not href:
            continue
        main_url = f"https://kancleroptshilovo.ru{href}"
        main_name_tag = main.find_next("p", class_="src-components-Text-Text__text")
        main_name = main_name_tag.text.strip() if main_name_tag else "Без имени"
        driver.get(main_url)
        time.sleep(1.2)
        sub_soup = BeautifulSoup(driver.page_source, "html.parser")
        subs = sub_soup.select(SUBSECTION_LINK_SELECTOR)
        if subs:
            for s in subs:
                sub_href = s.get("href")
                if not sub_href:
                    continue
                sub_url = f"https://kancleroptshilovo.ru{sub_href}"
                sub_name_tag = s.find_next("p", class_="src-components-Text-Text__text")
                sub_name = sub_name_tag.text.strip() if sub_name_tag else "Без имени"
                subsections.append((f"{main_name} → {sub_name}", sub_url))
        else:
            subsections.append((main_name, main_url))
    return subsections


def parse_products_from_soup(soup: BeautifulSoup, page_url: str) -> Dict[str, Dict]:
    nodes = []
    for sel in PRODUCT_NODE_SELECTORS:
        nodes.extend(soup.select(sel))
    products: Dict[str, Dict] = {}
    for node in nodes:
        try:
            name = "Неизвестно"
            name_a = node.find("a", class_="src-components-Product-ProductList-ProductList__name")
            if name_a:
                name_span = name_a.find("span", itemprop="name")
                if name_span:
                    name = name_span.get_text(strip=True)
            description = "Нет описания"
            desc_ul = node.find("ul", class_="info")
            if desc_ul:
                description = "; ".join(li.get_text(strip=True) for li in desc_ul.find_all("li"))
            else:
                meta_desc = node.find("meta", itemprop="description")
                if meta_desc and meta_desc.get("content"):
                    description = meta_desc["content"].strip()
            price = "Цена не указана"
            p1 = node.select_one("span.Price__count")
            if p1:
                p2 = node.select_one("span.Price__penny")
                kop = p2.get_text(strip=True) if p2 else "00"
                price = f"{p1.get_text(strip=True)},{kop}"
            else:
                low = node.select_one('span[itemprop="lowPrice"]')
                if low:
                    price = low.get_text(strip=True)
                else:
                    wrap = node.select_one("span.classPrice.js-PriceWrap, span.Price.js-PriceWrap")
                    if wrap:
                        inner = wrap.find_all("span")
                        if inner:
                            price = inner[-1].get_text(strip=True)
            amount = "Количество не указано"
            amount_node = node.select_one(
                "p.src-components-Text-Text__text.src-components-Product-ProductBalance-ProductBalance__restAmount_productList"
            )
            if amount_node:
                txt = amount_node.get_text()
                amount = txt
            image_url = "Фото не найдено"
            img = node.select_one("img.src-components-Image-Image__preview")
            if img:
                for attr in ("src", "data-src", "data-lazy", "data-original", "data-srcset", "srcset"):
                    val = img.get(attr)
                    if val:
                        if attr == "srcset":
                            val = val.split(",")[0].strip().split(" ")[0]
                        image_url = val
                        break
            product_url = page_url
            link_tag = node.select_one("a.listItemPhoto__link") or node.select_one("a[itemprop='url']")
            if link_tag and link_tag.get("href"):
                product_url = f"https://kancleroptshilovo.ru{link_tag.get('href')}"
            if product_url in products:
                continue
            products[product_url] = {
                "name": name,
                "description": description,
                "price": price,
                "amount": amount,
                "image_url": image_url,
                "product_url": product_url,
            }
        except Exception:
            continue
    return products


def is_field_valid(value: str) -> bool:
    if not value:
        return False
    v = value.strip().lower()
    bad = {
        "неизвестно",
        "нет описания",
        "цена не указана",
        "фото не найдено",
        "количество не указано",
        "#",
    }
    return not any(b in v for b in bad)


def page_has_all_required_fields(products: Dict[str, Dict]) -> bool:
    if not products:
        return False
    for p in products.values():
        if not (is_field_valid(p.get("name", "")) and
                is_field_valid(p.get("description", "")) and
                is_field_valid(p.get("price", "")) and
                is_field_valid(p.get("amount", "")) and
                is_field_valid(p.get("image_url", "")) and
                is_field_valid(p.get("product_url", ""))):
            return False
    return True


def parse_products_page(driver: webdriver.Chrome, section_name: str, url: str) -> Dict[str, Dict]:
    try:
        driver.get(url)
    except Exception:
        return {}
    wait_until_products_stable(driver)
    ensure_images_loaded(driver)
    soup = BeautifulSoup(driver.page_source, "html.parser")
    products = parse_products_from_soup(soup, page_url=url)
    retries = 0
    while retries < PAGE_FILL_RETRIES and not page_has_all_required_fields(products):
        retries += 1
        safe_scroll(driver, 1200)
        time.sleep(PAGE_FILL_WAIT)
        ensure_images_loaded(driver, per_node_timeout=1.0, per_step_sleep=0.05)
        wait_until_products_stable(driver, min_wait=0.2, max_wait=6)
        soup = BeautifulSoup(driver.page_source, "html.parser")
        products = parse_products_from_soup(soup, page_url=url)
    cleaned = {
        k: v for k, v in products.items()
        if is_field_valid(v["name"]) and is_field_valid(v["description"])
        and is_field_valid(v["price"]) and is_field_valid(v["amount"])
        and is_field_valid(v["image_url"]) and is_field_valid(v["product_url"])
    }
    return cleaned if cleaned else products


def _is_out_of_stock(amount: str) -> bool:
    if not amount:
        return False
    a = amount.strip().lower()
    return "нет в наличии" in a


def save_products_batch(section_name: str, products: Dict[str, Dict], table_name: str = "kancleroptshilovo_products") -> int:
    if not products:
        return 0
    filtered = [
        p for p in products.values()
        if not _is_out_of_stock(p.get("amount", ""))
    ]
    if not filtered:
        return 0
    rows = [
        (section_name, p["name"], p["description"], p["price"], p["amount"], p["image_url"], p["product_url"])
        for p in filtered
    ]
    with DB_LOCK:
        conn = sqlite3.connect(DB_FILE, timeout=DB_WRITE_TIMEOUT)
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
                product_url TEXT UNIQUE
            )
        """)
        cur.executemany(f"""
            INSERT OR IGNORE INTO {table_name}
            (category, name, description, price, amount, image_url, product_url)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, rows)
        conn.commit()
        conn.close()
    return len(rows)


def parse_section(section_name: str, section_url: str) -> int:
    driver = create_driver()
    total_added = 0
    try:
        page = 1
        while True:
            page_url = section_url.replace("/catalog-list", "/catalog") + f"?limit=108&p={page}"
            products = parse_products_page(driver, section_name, page_url)
            if not products:
                break
            added = save_products_batch(section_name, products)
            total_added += added
            page += 1
    finally:
        try:
            driver.quit()
        except Exception:
            pass
    return total_added


def build_catalog_multithread(base_url: str, max_threads: int = MAX_THREADS) -> None:
    discovery_driver = create_driver()
    try:
        all_sections = discover_subsections(discovery_driver, base_url)
    finally:
        try:
            discovery_driver.quit()
        except Exception:
            pass
    if not all_sections:
        return
    total_attempts = 0
    with ThreadPoolExecutor(max_workers=max_threads) as executor, tqdm(total=len(all_sections), desc="Sections") as pbar:
        future_to_name = {}
        for idx, (name, url) in enumerate(all_sections, start=1):
            fut = executor.submit(parse_section, name, url)
            future_to_name[fut] = name
        for fut in as_completed(future_to_name):
            try:
                added = fut.result()
                total_attempts += added
            except Exception:
                pass
            pbar.update(1)

if __name__ == "__main__":
    BASE_URL = "https://kancleroptshilovo.ru/catalog-list"
    build_catalog_multithread(BASE_URL, max_threads=4)