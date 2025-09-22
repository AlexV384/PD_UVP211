import json

input_file = 'products.json'
output_file = 'kancleroptshilovo_products.json'
invalid_values = {'нет', 'не найдено', 'неизвестно', '', None, 0, "0", "0 шт."}

def is_valid_product(product):
    required_fields = ['name', 'description', 'price', 'amount', 'image_url', 'product_url']
    for field in required_fields:
        value = product.get(field, '').strip().lower()
        if value in invalid_values:
            return False
    return True

def clean_data(data):
    cleaned = {}
    for category, products in data.items():
        valid_products = {
            url: info
            for url, info in products.items()
            if is_valid_product(info)
        }
        if valid_products:
            cleaned[category] = valid_products
    return cleaned

with open(input_file, 'r', encoding='utf-8') as f:
    data = json.load(f)

cleaned_data = clean_data(data)

with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(cleaned_data, f, ensure_ascii=False, indent=4)

print(f'Готово! Очищенные данные сохранены в {output_file}')