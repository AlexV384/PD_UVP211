from flask import Flask, render_template, request, jsonify
import psycopg2
from psycopg2.extras import RealDictCursor
from user_agents import parse

app = Flask(__name__)

DB_PARAMS = {
    "dbname": "mydatabase",
    "user": "myuser",
    "password": "mypassword",
    "host": "localhost",
    "port": "5432"
}

def get_all_products():
    conn = psycopg2.connect(**DB_PARAMS)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM officemag_products")
    products = cur.fetchall()
    cur.close()
    conn.close()
    result = []
    for p in products:
        price_str = p.get("price", "0").replace(" ", "").replace(",", ".")
        try:
            price = float(price_str)
        except ValueError:
            price = 0.0

        amount_str = p.get("amount", "0")
        amount = int("".join(filter(str.isdigit, amount_str))) if any(c.isdigit() for c in amount_str) else 0

        product = {
            "category": p.get("category", "Без категории"),
            "name": p.get("name", ""),
            "description": p.get("description", ""),
            "price": price,
            "amount": amount,
            "image_url": p.get("image_url", ""),
            "product_url": p.get("product_url", "#")
        }
        result.append(product)
    return result

@app.route("/")
def index():
    products = get_all_products()
    CATEGORIES = sorted(set(p["category"] for p in products))
    user_agent = parse(request.headers.get('User-Agent'))
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