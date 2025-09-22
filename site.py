import glob
from flask import Flask, render_template, request, jsonify
import json
import re
from user_agents import parse

app = Flask(__name__)

PRODUCTS = []

for filepath in glob.glob("data/*.json"):
    with open(filepath, "r", encoding="utf-8") as f:
        try:
            raw_data = json.load(f)
        except Exception as e:
            print(f"⚠️ Не удалось загрузить {filepath}: {e}")
            continue

        for category, items in raw_data.items():
            for url, info in items.items():
                price_str = info.get("price", "0").replace(" ", "").replace(",", ".")
                try:
                    price = float(price_str)
                except ValueError:
                    price = 0.0

                amount_str = info.get("amount", "0")
                match = re.search(r"\d+", amount_str)
                amount = int(match.group()) if match else 0

                product = {
                    "category": category,
                    "name": info.get("name", ""),
                    "description": info.get("description", ""),
                    "price": price,
                    "amount": amount,
                    "image_url": info.get("image_url", ""),
                    "product_url": info.get("product_url", url),
                }
                PRODUCTS.append(product)

CATEGORIES = sorted(set(p["category"] for p in PRODUCTS))

@app.route("/")
def index():
    user_agent = parse(request.headers.get('User-Agent'))
    if user_agent.is_mobile:
        return render_template("index-mobile.html", categories=CATEGORIES)
    else:
        return render_template("index-desktop.html", categories=CATEGORIES)


@app.route("/get_products")
def get_products():
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
    for p in PRODUCTS:
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

app.run(debug=True)