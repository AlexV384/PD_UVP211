import os
from flask import Flask, render_template, request, jsonify
import sqlite3
from user_agents import parse

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "parsers", "data.db")


def get_all_products():
    if not os.path.exists(DB_FILE):
        raise FileNotFoundError(f"SQLite база не найдена: {DB_FILE}")
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT name 
        FROM sqlite_master 
        WHERE type='table' AND name LIKE '%_products'
    """)
    tables = [row["name"] for row in cur.fetchall()]
    result = []
    for table in tables:
        cur.execute(f"SELECT * FROM {table}")
        products = cur.fetchall()
        for p in products:
            price_str = str(p["price"]).replace(" ", "").replace(",", ".") if "price" in p.keys() else "0"
            try:
                price = float(price_str)
            except ValueError:
                price = 0.0
            amount_str = str(p["amount"]) if "amount" in p.keys() else "0"
            amount = int("".join(filter(str.isdigit, amount_str))) if any(c.isdigit() for c in amount_str) else 0
            product = {
                "category": p["category"] if "category" in p.keys() else table,
                "name": p["name"] if "name" in p.keys() else "",
                "description": p["description"] if "description" in p.keys() else "",
                "price": price,
                "amount": amount,
                "image_url": p["image_url"] if "image_url" in p.keys() else "",
                "product_url": p["product_url"] if "product_url" in p.keys() else "#"
            }
            result.append(product)
    cur.close()
    conn.close()
    return result


@app.route("/")
def index():
    products = get_all_products()
    CATEGORIES = sorted(set(p["category"] for p in products))
    user_agent = parse(request.headers.get("User-Agent"))
    if user_agent.is_mobile:
        return render_template("index-mobile.html", categories=CATEGORIES)
    else:
        return render_template("index-desktop.html", categories=CATEGORIES)


@app.route("/get_products")
def get_products():
    products = get_all_products()
    selected_categories = request.args.getlist("category")
    try:
        min_price = float(request.args.get("min_price") or 0)
    except ValueError:
        min_price = 0
    try:
        max_price = float(request.args.get("max_price") or float("inf"))
    except ValueError:
        max_price = float("inf")
    search_query = request.args.get("search", "").lower()
    sort_order = request.args.get("sort", "")
    page = int(request.args.get("page", 1))
    products_per_page = 30
    start = (page - 1) * products_per_page
    end = start + products_per_page
    filtered = []
    for p in products:
        price = p.get("price", 0)
        if not (min_price <= price <= max_price):
            continue
        if selected_categories and p.get("category") not in selected_categories:
            continue
        if search_query and search_query not in p["name"].lower():
            continue
        filtered.append(p)
    if sort_order == "price_asc":
        filtered.sort(key=lambda x: x["price"])
    elif sort_order == "price_desc":
        filtered.sort(key=lambda x: -x["price"])
    elif sort_order == "name_asc":
        filtered.sort(key=lambda x: x["name"].lower())
    elif sort_order == "name_desc":
        filtered.sort(key=lambda x: x["name"].lower(), reverse=True)
    elif sort_order == "amount_asc":
        filtered.sort(key=lambda x: x["amount"])
    elif sort_order == "amount_desc":
        filtered.sort(key=lambda x: -x["amount"])
    total_pages = (len(filtered) + products_per_page - 1) // products_per_page
    paginated_products = filtered[start:end]
    return jsonify({
        "products": paginated_products,
        "total": len(filtered),
        "total_pages": total_pages
    })


if __name__ == "__main__":
    app.run(debug=True)