# POS + Shop Website Demo

Demo project implementing a point-of-sale owner panel and a customer-facing shop website on top of the **same SQLite database**.

## Features implemented

### Product module
- Add / edit / delete product
- Product fields: item name, description, multi-barcode text, category, family, season, brand, cost, price1, price2, opening stock, active/inactive, service item, image URL
- Add category/family/brand/season
- Search by barcode/item/category/brand/family/season
- Filter by category/brand/family/season

### Stock module
- Stock page lists quantity, cost, and total cost value
- Edit stock quantity
- Stock history (sales/inventory, filter by transaction type and product)
- Quantity filters: negative / zero / positive

### Customers & Suppliers
- Add customer and supplier (name, phone1, phone2, address, country, active/inactive)
- Search by any field

### Purchase
- Add purchase document (reference, supplier, invoice number, auto date)
- Edit/delete endpoints are available in API

### Reports
- Daily report, cash report, products, customer report, purchase report (aggregated in reports endpoint)

### Website orders + owner notification
- Customers place orders from the website
- Orders write to the same DB used by POS
- Stock decreases for non-service items
- Owner receives an automatic order notification:
  - Uses SMTP if environment variables are provided
  - Otherwise writes to `data/order_notifications.log` as demo fallback

## Run

```bash
python3 app.py
```

Then open:
- Shop website: `http://localhost:8000/`
- POS owner panel: `http://localhost:8000/pos`

## Optional SMTP env vars

- `OWNER_EMAIL`
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USER`
- `SMTP_PASSWORD`
- `SMTP_FROM`
