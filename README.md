HEAD
# Warke Traders Inventory Management System

A Flask, Bootstrap 5, and MySQL inventory system for Warke Traders.

## Features

- Session-based admin login
- Dashboard with total products, stock, investment, and potential profit
- Add, edit, delete, search, and filter products
- Product cards with profit and stock status
- Pagination
- CSV export
- A4 PDF inventory reports with print support
- Consumer billing with saved customers, invoices, invoice PDFs, and email support
- Invoice management with customer/date search
- Billing reports with total sales, date-wise sales, and top selling items
- Supplier purchase entry with automatic stock increase
- Purchase history, purchase details, purchase PDFs, and purchase reports
- WhatsApp bill sharing through pre-filled WhatsApp Web links
- Role-based authentication for admin and employee users
- Admin-only employee registration
- Bootstrap 5 responsive UI with Bootstrap Icons
- Backend validation and parameterized MySQL queries

## MySQL Setup

Run this query in MySQL Workbench, phpMyAdmin, or the MySQL CLI:

```sql
CREATE DATABASE IF NOT EXISTS warke_traders_inventory;

USE warke_traders_inventory;

CREATE TABLE IF NOT EXISTS products (
    id INT PRIMARY KEY AUTO_INCREMENT,
    item_name VARCHAR(255) NOT NULL,
    buying_price FLOAT NOT NULL,
    selling_price FLOAT NOT NULL,
    stock_quantity INT NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

The full setup script with products, customers, invoices, and invoice item tables is available in `schema.sql`.

For an existing database that already has the `products` table, run:

```powershell
mysql -u root -p warke_traders_inventory < billing_schema.sql
mysql -u root -p warke_traders_inventory < purchase_schema.sql
mysql -u root -p warke_traders_inventory < users_schema.sql
```

## Run The Project

1. Open a terminal in this folder.

2. Create a virtual environment:

```powershell
python -m venv venv
```

3. Activate it:

```powershell
venv\Scripts\activate
```

4. Install dependencies:

```powershell
pip install -r requirements.txt
```

5. Create your environment file:

```powershell
copy .env.example .env
```

6. Edit `.env` with your MySQL username, password, and report contact details:

```text
SHOP_ADDRESS=Shop Address: Add full address here
SHOP_MOBILE=Mobile: +91-XXXXXXXXXX
SHOP_EMAIL=Email: warketraders@example.com
OWNER_REPORT_EMAIL=warketraders@example.com
```

For Gmail invoice/report sending, create a Gmail App Password and configure:

```text
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=h8329478631@gmail.com
SMTP_PASSWORD=lrzlzuakrswitorv
SMTP_FROM_EMAIL=h8329478631@gmail.com
```

7. Import the database:

```powershell
mysql -u root -p < schema.sql
```

8. Start Flask:

```powershell
python app.py
```

9. Open:

```text
http://127.0.0.1:5000
```

Default login:

```text
Username: admin
Password: admin123
```

Change these credentials in `.env` before using the app seriously.

## Users And Roles

Run `users_schema.sql` to create the `users` table.

Admins can:

- Add, edit, and delete products
- View buying price, profit, and total investment
- Access purchases and reports
- Register employees at `http://127.0.0.1:5000/add_employee`

Employees can:

- Open dashboard
- Create bills
- View invoices
- Download/print invoice PDFs

Employees cannot view buying price, profit, investment, purchases, reports, or employee management.

Admin login remains available at:

```text
http://127.0.0.1:5000/login
```

Employee login is available at:

```text
http://127.0.0.1:5000/employee_login
```

## Reports

Open `http://127.0.0.1:5000/reports` after login.

The reports page supports:

- All items
- Low stock items only
- Out of stock items only
- Browser print using the `Print Report` button
- A dynamically generated A4 PDF using the `Download PDF` button
- Billing PDF report
- Email billing report to the owner
- Purchase total report
- Supplier-wise purchase report
- Date-wise purchase report

PDF generation uses `reportlab`, installed by:

```powershell
pip install -r requirements.txt
```

## Billing

Open `http://127.0.0.1:5000/billing` after login.

Billing supports:

- Select existing customer or add a new customer
- Add/remove multiple product rows
- Automatic price and line total calculation
- Stock validation and automatic stock reduction after billing
- Invoice redirect after bill generation
- Optional auto email to the customer

Invoice management is available at:

```text
http://127.0.0.1:5000/invoices
```

## Purchase Management

Open `http://127.0.0.1:5000/purchase` after login.

Purchase entry supports:

- Select existing supplier or add a new supplier
- Add/remove multiple product rows
- Manual buying price entry
- Automatic row total and grand total calculation
- Stock increase after purchase save
- Weighted-average buying price update
- Purchase detail page with print, PDF, and WhatsApp sharing

Purchase history is available at:

```text
http://127.0.0.1:5000/purchases
```

## WhatsApp Sharing

Invoice and purchase detail pages include `Send via WhatsApp` buttons. They open WhatsApp Web with a pre-filled message using:

```text
https://wa.me/<mobile_number>?text=<encoded_message>
```

For Indian 10-digit numbers, the app automatically prefixes `91`.

# warke-traders

