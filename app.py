import csv
import os
import smtplib
from datetime import datetime
from email.message import EmailMessage
from functools import wraps
from io import BytesIO, StringIO
from urllib.parse import quote

import mysql.connector
from dotenv import load_dotenv
from flask import (
    Flask,
    Response,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change-this-secret-key")

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
PER_PAGE = 8
SHOP_ADDRESS = os.getenv("SHOP_ADDRESS", "Shop Address: Add full address here")
SHOP_MOBILE = os.getenv("SHOP_MOBILE", "Mobile: +91-XXXXXXXXXX")
SHOP_EMAIL = os.getenv("SHOP_EMAIL", "Email: warketraders@example.com")
OWNER_REPORT_EMAIL = os.getenv("OWNER_REPORT_EMAIL", SHOP_EMAIL.replace("Email: ", ""))
UPLOAD_FOLDER = os.path.join(app.root_path, "static", "uploads")
ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", "Vihan@6191"),
        database=os.getenv("DB_NAME", "warke_traders_inventory"),
    )


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not session.get("logged_in"):
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped_view


def admin_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not session.get("logged_in"):
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login"))
        if session.get("role") != "admin":
            flash("Admin access required.", "danger")
            return redirect(url_for("dashboard"))
        return view(*args, **kwargs)

    return wrapped_view


def employee_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not session.get("logged_in"):
            flash("Please log in to continue.", "warning")
            return redirect(url_for("employee_login"))
        if session.get("role") not in {"admin", "employee"}:
            flash("Employee access required.", "danger")
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped_view


def is_admin():
    return session.get("role") == "admin"


def parse_positive_float(value, field_name):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a valid number.")
    if number < 0:
        raise ValueError(f"{field_name} cannot be negative.")
    return number


def parse_non_negative_int(value, field_name):
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a valid whole number.")
    if number < 0:
        raise ValueError(f"{field_name} cannot be negative.")
    return number


def parse_positive_int(value, field_name):
    number = parse_non_negative_int(value, field_name)
    if number <= 0:
        raise ValueError(f"{field_name} must be greater than zero.")
    return number


def validate_product_form(form):
    item_name = form.get("item_name", "").strip()
    if not item_name:
        raise ValueError("Item name is required.")
    if len(item_name) > 255:
        raise ValueError("Item name must be 255 characters or fewer.")

    buying_price = parse_positive_float(form.get("buying_price"), "Buying price")
    selling_price = parse_positive_float(form.get("selling_price"), "Selling price")
    stock_quantity = parse_non_negative_int(form.get("stock_quantity"), "Stock quantity")

    return {
        "item_name": item_name,
        "buying_price": buying_price,
        "selling_price": selling_price,
        "stock_quantity": stock_quantity,
    }


def validate_customer_form(form):
    name = form.get("customer_name", "").strip()
    mobile = form.get("customer_mobile", "").strip()
    email = form.get("customer_email", "").strip()
    address = form.get("customer_address", "").strip()

    if not name:
        raise ValueError("Customer name is required.")
    if not mobile:
        raise ValueError("Customer mobile number is required.")
    if email and "@" not in email:
        raise ValueError("Customer email must be valid.")

    return {
        "name": name,
        "mobile": mobile,
        "email": email,
        "address": address,
    }


def get_user_by_username(username):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT id, username, password, role FROM users WHERE username = %s",
            (username,),
        )
        return cursor.fetchone()
    except mysql.connector.Error:
        return None
    finally:
        cursor.close()
        connection.close()


def authenticate_user(username, password, expected_role):
    user = get_user_by_username(username)
    if user and user["role"] == expected_role and check_password_hash(user["password"], password):
        return user
    return None


def allowed_image(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS


def save_profile_image(file_storage):
    if not file_storage or not file_storage.filename:
        return ""
    if not allowed_image(file_storage.filename):
        raise ValueError("Profile image must be PNG, JPG, JPEG, or WEBP.")

    filename = secure_filename(file_storage.filename)
    unique_filename = f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{filename}"
    file_storage.save(os.path.join(UPLOAD_FOLDER, unique_filename))
    return f"uploads/{unique_filename}"


def validate_employee_form(form, require_password=True):
    full_name = form.get("full_name", "").strip()
    username = form.get("username", "").strip()
    password = form.get("password", "")
    mobile = form.get("mobile", "").strip()
    email = form.get("email", "").strip()
    address = form.get("address", "").strip()
    aadhaar_number = form.get("aadhaar_number", "").strip()

    if not full_name:
        raise ValueError("Full name is required.")
    if not username:
        raise ValueError("Username is required.")
    if require_password and len(password) < 6:
        raise ValueError("Password must be at least 6 characters.")
    if not mobile:
        raise ValueError("Mobile number is required.")
    if email and "@" not in email:
        raise ValueError("Employee email must be valid.")

    return {
        "full_name": full_name,
        "username": username,
        "password": password,
        "mobile": mobile,
        "email": email,
        "address": address,
        "aadhaar_number": aadhaar_number,
    }


def create_employee_user(form, files):
    employee = validate_employee_form(form, require_password=True)
    profile_image = save_profile_image(files.get("profile_image"))
    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO users
                (username, password, role, full_name, mobile, email, address, aadhaar_number, profile_image)
            VALUES (%s, %s, 'employee', %s, %s, %s, %s, %s, %s)
            """,
            (
                employee["username"],
                generate_password_hash(employee["password"]),
                employee["full_name"],
                employee["mobile"],
                employee["email"],
                employee["address"],
                employee["aadhaar_number"],
                profile_image,
            ),
        )
        connection.commit()
    except mysql.connector.IntegrityError:
        raise ValueError("That username already exists.")
    finally:
        cursor.close()
        connection.close()


def update_employee_user(user_id, form, files):
    employee = validate_employee_form(form, require_password=False)
    password = employee["password"]
    profile_image = save_profile_image(files.get("profile_image"))

    fields = [
        "username = %s",
        "full_name = %s",
        "mobile = %s",
        "email = %s",
        "address = %s",
        "aadhaar_number = %s",
    ]
    params = [
        employee["username"],
        employee["full_name"],
        employee["mobile"],
        employee["email"],
        employee["address"],
        employee["aadhaar_number"],
    ]

    if password:
        if len(password) < 6:
            raise ValueError("Password must be at least 6 characters.")
        fields.append("password = %s")
        params.append(generate_password_hash(password))
    if profile_image:
        fields.append("profile_image = %s")
        params.append(profile_image)

    params.append(user_id)
    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        cursor.execute(
            f"UPDATE users SET {', '.join(fields)} WHERE id = %s AND role = 'employee'",
            params,
        )
        connection.commit()
        if cursor.rowcount == 0:
            raise ValueError("Employee not found.")
    except mysql.connector.IntegrityError:
        raise ValueError("That username already exists.")
    finally:
        cursor.close()
        connection.close()


def get_customers():
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    cursor.execute("SELECT id, name, mobile, email, address FROM customers ORDER BY name")
    customers = cursor.fetchall()
    cursor.close()
    connection.close()
    return customers


def get_billable_products():
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT id, item_name, selling_price, stock_quantity
        FROM products
        WHERE stock_quantity > 0
        ORDER BY item_name
        """
    )
    products = cursor.fetchall()
    cursor.close()
    connection.close()
    return products


def get_invoice_details(invoice_id):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT
            i.id,
            i.total_amount,
            i.created_at,
            c.name AS customer_name,
            c.mobile AS customer_mobile,
            c.email AS customer_email,
            c.address AS customer_address
        FROM invoices i
        JOIN customers c ON c.id = i.customer_id
        WHERE i.id = %s
        """,
        (invoice_id,),
    )
    invoice = cursor.fetchone()

    if not invoice:
        cursor.close()
        connection.close()
        return None, []

    cursor.execute(
        """
        SELECT
            ii.quantity,
            ii.selling_price,
            ii.total_price,
            p.item_name
        FROM invoice_items ii
        JOIN products p ON p.id = ii.product_id
        WHERE ii.invoice_id = %s
        ORDER BY ii.id
        """,
        (invoice_id,),
    )
    items = cursor.fetchall()
    cursor.close()
    connection.close()
    return invoice, items


def validate_supplier_form(form):
    name = form.get("supplier_name", "").strip()
    mobile = form.get("supplier_mobile", "").strip()
    email = form.get("supplier_email", "").strip()
    address = form.get("supplier_address", "").strip()

    if not name:
        raise ValueError("Supplier name is required.")
    if not mobile:
        raise ValueError("Supplier mobile number is required.")
    if email and "@" not in email:
        raise ValueError("Supplier email must be valid.")

    return {
        "name": name,
        "mobile": mobile,
        "email": email,
        "address": address,
    }


def get_suppliers():
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    cursor.execute("SELECT id, name, mobile, email, address FROM suppliers ORDER BY name")
    suppliers = cursor.fetchall()
    cursor.close()
    connection.close()
    return suppliers


def get_purchase_products():
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT id, item_name, buying_price, selling_price, stock_quantity
        FROM products
        ORDER BY item_name
        """
    )
    products = cursor.fetchall()
    cursor.close()
    connection.close()
    return products


def create_purchase_from_form(form):
    selected_supplier_id = form.get("supplier_id", "").strip()
    product_ids = form.getlist("product_id[]")
    quantities = form.getlist("quantity[]")
    buying_prices = form.getlist("buying_price[]")

    if not product_ids:
        raise ValueError("Add at least one product to the purchase.")

    requested_items = []
    for product_id, quantity, buying_price in zip(product_ids, quantities, buying_prices):
        if not product_id:
            continue
        requested_items.append(
            {
                "product_id": parse_positive_int(product_id, "Product"),
                "quantity": parse_positive_int(quantity, "Quantity"),
                "buying_price": parse_positive_float(buying_price, "Buying price"),
            }
        )

    if not requested_items:
        raise ValueError("Add at least one valid purchase item.")

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        connection.start_transaction()

        if selected_supplier_id:
            supplier_id = parse_positive_int(selected_supplier_id, "Supplier")
            cursor.execute("SELECT id FROM suppliers WHERE id = %s", (supplier_id,))
            if not cursor.fetchone():
                raise ValueError("Selected supplier was not found.")
        else:
            supplier_data = validate_supplier_form(form)
            cursor.execute(
                """
                INSERT INTO suppliers (name, mobile, email, address)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    supplier_data["name"],
                    supplier_data["mobile"],
                    supplier_data["email"],
                    supplier_data["address"],
                ),
            )
            supplier_id = cursor.lastrowid

        purchase_items = []
        total_amount = 0

        for requested_item in requested_items:
            cursor.execute(
                """
                SELECT id, item_name, buying_price, stock_quantity
                FROM products
                WHERE id = %s
                FOR UPDATE
                """,
                (requested_item["product_id"],),
            )
            product = cursor.fetchone()
            if not product:
                raise ValueError("One selected product was not found.")

            item_total = requested_item["buying_price"] * requested_item["quantity"]
            total_amount += item_total
            purchase_items.append(
                {
                    "product_id": product["id"],
                    "quantity": requested_item["quantity"],
                    "buying_price": requested_item["buying_price"],
                    "total_price": item_total,
                    "current_stock": product["stock_quantity"],
                    "current_buying_price": product["buying_price"],
                }
            )

        cursor.execute(
            "INSERT INTO purchases (supplier_id, total_amount) VALUES (%s, %s)",
            (supplier_id, total_amount),
        )
        purchase_id = cursor.lastrowid

        for item in purchase_items:
            cursor.execute(
                """
                INSERT INTO purchase_items
                    (purchase_id, product_id, quantity, buying_price, total_price)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    purchase_id,
                    item["product_id"],
                    item["quantity"],
                    item["buying_price"],
                    item["total_price"],
                ),
            )
            new_stock = item["current_stock"] + item["quantity"]
            average_buying_price = (
                (item["current_buying_price"] * item["current_stock"]) + item["total_price"]
            ) / new_stock
            cursor.execute(
                """
                UPDATE products
                SET stock_quantity = %s, buying_price = %s
                WHERE id = %s
                """,
                (new_stock, average_buying_price, item["product_id"]),
            )

        connection.commit()
        return purchase_id
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


def get_purchase_details(purchase_id):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT
            p.id,
            p.total_amount,
            p.created_at,
            s.name AS supplier_name,
            s.mobile AS supplier_mobile,
            s.email AS supplier_email,
            s.address AS supplier_address
        FROM purchases p
        JOIN suppliers s ON s.id = p.supplier_id
        WHERE p.id = %s
        """,
        (purchase_id,),
    )
    purchase = cursor.fetchone()

    if not purchase:
        cursor.close()
        connection.close()
        return None, []

    cursor.execute(
        """
        SELECT
            pi.quantity,
            pi.buying_price,
            pi.total_price,
            pr.item_name
        FROM purchase_items pi
        JOIN products pr ON pr.id = pi.product_id
        WHERE pi.purchase_id = %s
        ORDER BY pi.id
        """,
        (purchase_id,),
    )
    items = cursor.fetchall()
    cursor.close()
    connection.close()
    return purchase, items


def clean_mobile_number(mobile):
    digits = "".join(character for character in mobile if character.isdigit())
    if len(digits) == 10:
        return f"91{digits}"
    return digits


def build_whatsapp_url(mobile, message):
    return f"https://wa.me/{clean_mobile_number(mobile)}?text={quote(message)}"


def build_invoice_whatsapp_url(invoice):
    message = (
        f"Hello {invoice['customer_name']}, this is Warke Traders. "
        f"Your invoice #{invoice['id']} amount is Rs. {invoice['total_amount']:.2f}. "
        f"Date: {invoice['created_at'].strftime('%d-%m-%Y %I:%M %p')}. "
        "Thank you for your business."
    )
    return build_whatsapp_url(invoice["customer_mobile"], message)


def build_purchase_whatsapp_url(purchase):
    message = (
        f"Hello {purchase['supplier_name']}, this is Warke Traders. "
        f"Purchase entry #{purchase['id']} has been recorded for Rs. {purchase['total_amount']:.2f}. "
        f"Date: {purchase['created_at'].strftime('%d-%m-%Y %I:%M %p')}. "
        "Thank you for your business."
    )
    return build_whatsapp_url(purchase["supplier_mobile"], message)


def get_report_products(report_type="all"):
    where_sql = ""
    params = []

    if report_type == "low_stock":
        where_sql = "WHERE stock_quantity > 0 AND stock_quantity <= %s"
        params.append(5)
    elif report_type == "out_of_stock":
        where_sql = "WHERE stock_quantity = 0"

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    cursor.execute(
        f"""
        SELECT item_name, buying_price, selling_price, stock_quantity, created_at
        FROM products
        {where_sql}
        ORDER BY item_name
        """,
        params,
    )
    product_rows = cursor.fetchall()
    cursor.close()
    connection.close()
    return product_rows


def build_inventory_pdf(product_rows, report_type):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    generated_at = datetime.now()
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        fontSize=22,
        leading=26,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#152238"),
        spaceAfter=4,
    )
    center_style = ParagraphStyle(
        "CenterInfo",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#4b5563"),
    )
    right_style = ParagraphStyle(
        "RightInfo",
        parent=styles["Normal"],
        alignment=TA_RIGHT,
        fontSize=9,
        textColor=colors.HexColor("#4b5563"),
    )

    report_label = {
        "all": "All Inventory Items",
        "low_stock": "Low Stock Items",
        "out_of_stock": "Out Of Stock Items",
    }.get(report_type, "All Inventory Items")

    story = [
        Paragraph("Warke Traders", title_style),
        Paragraph("Owner: Pro. Pra. Harshal Warke", center_style),
        Paragraph(SHOP_ADDRESS, center_style),
        Paragraph(f"{SHOP_MOBILE} | {SHOP_EMAIL}", center_style),
        Spacer(1, 8),
        Paragraph(f"Inventory Report: {report_label}", center_style),
        Paragraph(
            f"Date: {generated_at.strftime('%d-%m-%Y')} | Time: {generated_at.strftime('%I:%M %p')}",
            right_style,
        ),
        Spacer(1, 10),
    ]

    table_data = [
        ["Item Name", "Buying Price", "Selling Price", "Stock", "Profit/Item"],
    ]
    for product in product_rows:
        table_data.append(
            [
                product["item_name"],
                f"Rs. {product['buying_price']:.2f}",
                f"Rs. {product['selling_price']:.2f}",
                str(product["stock_quantity"]),
                f"Rs. {product['selling_price'] - product['buying_price']:.2f}",
            ]
        )

    if len(table_data) == 1:
        table_data.append(["No products found", "", "", "", ""])

    table = Table(table_data, colWidths=[62 * mm, 30 * mm, 30 * mm, 22 * mm, 32 * mm], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#152238")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                ("ALIGN", (3, 1), (3, -1), "CENTER"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(table)

    document.build(story)
    buffer.seek(0)
    return buffer


def create_invoice_from_form(form):
    selected_customer_id = form.get("customer_id", "").strip()
    product_ids = form.getlist("product_id[]")
    quantities = form.getlist("quantity[]")
    auto_send = form.get("auto_send") == "on"

    if not product_ids:
        raise ValueError("Add at least one product to the bill.")

    requested_items = []
    for product_id, quantity in zip(product_ids, quantities):
        if not product_id:
            continue
        requested_items.append(
            {
                "product_id": parse_positive_int(product_id, "Product"),
                "quantity": parse_positive_int(quantity, "Quantity"),
            }
        )

    if not requested_items:
        raise ValueError("Add at least one valid product to the bill.")

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        connection.start_transaction()

        if selected_customer_id:
            customer_id = parse_positive_int(selected_customer_id, "Customer")
            cursor.execute("SELECT id, email FROM customers WHERE id = %s", (customer_id,))
            customer = cursor.fetchone()
            if not customer:
                raise ValueError("Selected customer was not found.")
        else:
            customer_data = validate_customer_form(form)
            cursor.execute(
                """
                INSERT INTO customers (name, mobile, email, address)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    customer_data["name"],
                    customer_data["mobile"],
                    customer_data["email"],
                    customer_data["address"],
                ),
            )
            customer_id = cursor.lastrowid

        bill_items = []
        total_amount = 0

        for requested_item in requested_items:
            cursor.execute(
                """
                SELECT id, item_name, selling_price, stock_quantity
                FROM products
                WHERE id = %s
                FOR UPDATE
                """,
                (requested_item["product_id"],),
            )
            product = cursor.fetchone()
            if not product:
                raise ValueError("One selected product was not found.")
            if requested_item["quantity"] > product["stock_quantity"]:
                raise ValueError(
                    f"Only {product['stock_quantity']} units available for {product['item_name']}."
                )

            item_total = product["selling_price"] * requested_item["quantity"]
            total_amount += item_total
            bill_items.append(
                {
                    "product_id": product["id"],
                    "quantity": requested_item["quantity"],
                    "selling_price": product["selling_price"],
                    "total_price": item_total,
                }
            )

        cursor.execute(
            "INSERT INTO invoices (customer_id, total_amount, user_id) VALUES (%s, %s, %s)",
            (customer_id, total_amount, session.get("user_id")),
        )
        invoice_id = cursor.lastrowid

        for item in bill_items:
            cursor.execute(
                """
                INSERT INTO invoice_items
                    (invoice_id, product_id, quantity, selling_price, total_price)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    invoice_id,
                    item["product_id"],
                    item["quantity"],
                    item["selling_price"],
                    item["total_price"],
                ),
            )
            cursor.execute(
                """
                UPDATE products
                SET stock_quantity = stock_quantity - %s
                WHERE id = %s
                """,
                (item["quantity"], item["product_id"]),
            )

        connection.commit()
        return invoice_id, auto_send
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


def build_invoice_pdf(invoice, items):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "InvoiceTitle",
        parent=styles["Title"],
        fontSize=22,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#152238"),
    )
    center_style = ParagraphStyle("Center", parent=styles["Normal"], alignment=TA_CENTER, fontSize=9)
    right_style = ParagraphStyle("Right", parent=styles["Normal"], alignment=TA_RIGHT, fontSize=9)

    story = []
    logo_path = os.path.join(app.root_path, "static", "images", "logo.png")
    if os.path.exists(logo_path):
        logo = Image(logo_path, width=22 * mm, height=22 * mm)
        logo.hAlign = "CENTER"
        story.extend([logo, Spacer(1, 4)])

    story.extend(
        [
            Paragraph("Warke Traders", title_style),
            Paragraph("Owner: Pro. Pra. Harshal Warke", center_style),
            Paragraph(SHOP_ADDRESS, center_style),
            Paragraph(f"{SHOP_MOBILE} | {SHOP_EMAIL}", center_style),
            Spacer(1, 10),
            Paragraph(f"Invoice #{invoice['id']}", right_style),
            Paragraph(
                f"Date: {invoice['created_at'].strftime('%d-%m-%Y')} | Time: {invoice['created_at'].strftime('%I:%M %p')}",
                right_style,
            ),
            Spacer(1, 8),
        ]
    )

    customer_table = Table(
        [
            ["Bill To", ""],
            ["Name", invoice["customer_name"]],
            ["Mobile", invoice["customer_mobile"]],
            ["Address", invoice["customer_address"] or "-"],
        ],
        colWidths=[28 * mm, 148 * mm],
    )
    customer_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cbd5e1")),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.extend([customer_table, Spacer(1, 10)])

    table_data = [["Item Name", "Qty", "Selling Price", "Total"]]
    for item in items:
        table_data.append(
            [
                item["item_name"],
                str(item["quantity"]),
                f"Rs. {item['selling_price']:.2f}",
                f"Rs. {item['total_price']:.2f}",
            ]
        )
    table_data.append(["", "", "Grand Total", f"Rs. {invoice['total_amount']:.2f}"])

    items_table = Table(table_data, colWidths=[86 * mm, 20 * mm, 34 * mm, 36 * mm], repeatRows=1)
    items_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#152238")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                ("FONTNAME", (2, -1), (-1, -1), "Helvetica-Bold"),
                ("BACKGROUND", (2, -1), (-1, -1), colors.HexColor("#f8fafc")),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.extend([items_table, Spacer(1, 14), Paragraph("Thank you for your business.", center_style)])

    document.build(story)
    buffer.seek(0)
    return buffer


def build_purchase_pdf(purchase, items):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "PurchaseTitle",
        parent=styles["Title"],
        fontSize=22,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#152238"),
    )
    center_style = ParagraphStyle("PurchaseCenter", parent=styles["Normal"], alignment=TA_CENTER, fontSize=9)
    right_style = ParagraphStyle("PurchaseRight", parent=styles["Normal"], alignment=TA_RIGHT, fontSize=9)

    story = [
        Paragraph("Warke Traders", title_style),
        Paragraph("Purchase Entry", center_style),
        Paragraph("Owner: Pro. Pra. Harshal Warke", center_style),
        Paragraph(SHOP_ADDRESS, center_style),
        Paragraph(f"{SHOP_MOBILE} | {SHOP_EMAIL}", center_style),
        Spacer(1, 10),
        Paragraph(f"Purchase #{purchase['id']}", right_style),
        Paragraph(
            f"Date: {purchase['created_at'].strftime('%d-%m-%Y')} | Time: {purchase['created_at'].strftime('%I:%M %p')}",
            right_style,
        ),
        Spacer(1, 8),
    ]

    supplier_table = Table(
        [
            ["Supplier", ""],
            ["Name", purchase["supplier_name"]],
            ["Mobile", purchase["supplier_mobile"]],
            ["Address", purchase["supplier_address"] or "-"],
        ],
        colWidths=[28 * mm, 148 * mm],
    )
    supplier_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cbd5e1")),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.extend([supplier_table, Spacer(1, 10)])

    table_data = [["Item Name", "Qty", "Buying Price", "Total"]]
    for item in items:
        table_data.append(
            [
                item["item_name"],
                str(item["quantity"]),
                f"Rs. {item['buying_price']:.2f}",
                f"Rs. {item['total_price']:.2f}",
            ]
        )
    table_data.append(["", "", "Grand Total", f"Rs. {purchase['total_amount']:.2f}"])

    items_table = Table(table_data, colWidths=[86 * mm, 20 * mm, 34 * mm, 36 * mm], repeatRows=1)
    items_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#152238")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                ("FONTNAME", (2, -1), (-1, -1), "Helvetica-Bold"),
                ("BACKGROUND", (2, -1), (-1, -1), colors.HexColor("#f8fafc")),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(items_table)
    document.build(story)
    buffer.seek(0)
    return buffer


def get_billing_report(start_date=None, end_date=None):
    where_clauses = []
    params = []
    if start_date:
        where_clauses.append("DATE(i.created_at) >= %s")
        params.append(start_date)
    if end_date:
        where_clauses.append("DATE(i.created_at) <= %s")
        params.append(end_date)
    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    cursor.execute(
        f"""
        SELECT
            COUNT(*) AS invoice_count,
            COALESCE(SUM(i.total_amount), 0) AS total_sales
        FROM invoices i
        {where_sql}
        """,
        params,
    )
    stats = cursor.fetchone()
    cursor.execute(
        f"""
        SELECT DATE(i.created_at) AS sale_date, COALESCE(SUM(i.total_amount), 0) AS total_sales
        FROM invoices i
        {where_sql}
        GROUP BY DATE(i.created_at)
        ORDER BY sale_date DESC
        LIMIT 10
        """,
        params,
    )
    daily_sales = cursor.fetchall()
    cursor.execute(
        f"""
        SELECT p.item_name, SUM(ii.quantity) AS total_quantity, SUM(ii.total_price) AS total_sales
        FROM invoice_items ii
        JOIN invoices i ON i.id = ii.invoice_id
        JOIN products p ON p.id = ii.product_id
        {where_sql}
        GROUP BY p.id, p.item_name
        ORDER BY total_quantity DESC
        LIMIT 10
        """,
        params,
    )
    top_items = cursor.fetchall()
    cursor.close()
    connection.close()
    return stats, daily_sales, top_items


def get_purchase_report(start_date=None, end_date=None):
    where_clauses = []
    params = []
    if start_date:
        where_clauses.append("DATE(p.created_at) >= %s")
        params.append(start_date)
    if end_date:
        where_clauses.append("DATE(p.created_at) <= %s")
        params.append(end_date)
    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    cursor.execute(
        f"""
        SELECT COUNT(*) AS purchase_count, COALESCE(SUM(p.total_amount), 0) AS total_purchases
        FROM purchases p
        {where_sql}
        """,
        params,
    )
    stats = cursor.fetchone()
    cursor.execute(
        f"""
        SELECT DATE(p.created_at) AS purchase_date, COALESCE(SUM(p.total_amount), 0) AS total_purchases
        FROM purchases p
        {where_sql}
        GROUP BY DATE(p.created_at)
        ORDER BY purchase_date DESC
        LIMIT 10
        """,
        params,
    )
    daily_purchases = cursor.fetchall()
    cursor.execute(
        f"""
        SELECT s.name AS supplier_name, COUNT(p.id) AS purchase_count, COALESCE(SUM(p.total_amount), 0) AS total_purchases
        FROM purchases p
        JOIN suppliers s ON s.id = p.supplier_id
        {where_sql}
        GROUP BY s.id, s.name
        ORDER BY total_purchases DESC
        LIMIT 10
        """,
        params,
    )
    supplier_purchases = cursor.fetchall()
    cursor.close()
    connection.close()
    return stats, daily_purchases, supplier_purchases


def build_billing_report_pdf(stats, daily_sales, top_items, start_date=None, end_date=None):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    generated_at = datetime.now()
    buffer = BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=15 * mm, leftMargin=15 * mm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "BillingReportTitle",
        parent=styles["Title"],
        fontSize=22,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#152238"),
    )
    center_style = ParagraphStyle("ReportCenter", parent=styles["Normal"], alignment=TA_CENTER, fontSize=9)
    story = [
        Paragraph("Warke Traders", title_style),
        Paragraph("Billing Sales Report", center_style),
        Paragraph(f"Generated: {generated_at.strftime('%d-%m-%Y %I:%M %p')}", center_style),
        Paragraph(f"Period: {start_date or 'Beginning'} to {end_date or 'Today'}", center_style),
        Spacer(1, 10),
    ]

    summary = Table(
        [
            ["Total Invoices", "Total Sales"],
            [str(stats["invoice_count"]), f"Rs. {stats['total_sales']:.2f}"],
        ],
        colWidths=[88 * mm, 88 * mm],
    )
    summary.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#152238")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.extend([summary, Spacer(1, 12), Paragraph("Top Selling Items", styles["Heading3"])])

    top_table_data = [["Item Name", "Quantity", "Sales"]]
    for item in top_items:
        top_table_data.append([item["item_name"], str(item["total_quantity"]), f"Rs. {item['total_sales']:.2f}"])
    if len(top_table_data) == 1:
        top_table_data.append(["No sales found", "", ""])
    top_table = Table(top_table_data, colWidths=[100 * mm, 30 * mm, 46 * mm])
    top_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#152238")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ]
        )
    )
    story.extend([top_table, Spacer(1, 12), Paragraph("Date-wise Sales", styles["Heading3"])])

    daily_table_data = [["Date", "Sales"]]
    for sale in daily_sales:
        daily_table_data.append([sale["sale_date"].strftime("%d-%m-%Y"), f"Rs. {sale['total_sales']:.2f}"])
    if len(daily_table_data) == 1:
        daily_table_data.append(["No sales found", ""])
    daily_table = Table(daily_table_data, colWidths=[88 * mm, 88 * mm])
    daily_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#152238")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ]
        )
    )
    story.append(daily_table)
    document.build(story)
    buffer.seek(0)
    return buffer


def send_email_with_attachment(to_email, subject, body, pdf_file, filename="attachment.pdf"):
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    sender_email = os.getenv("SMTP_FROM_EMAIL", smtp_user)

    if not smtp_user or not smtp_password or not sender_email:
        raise ValueError("SMTP_USER, SMTP_PASSWORD, and SMTP_FROM_EMAIL must be configured in .env.")

    message = EmailMessage()
    message["From"] = sender_email
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)
    message.add_attachment(
        pdf_file.getvalue(),
        maintype="application",
        subtype="pdf",
        filename=filename,
    )

    with smtplib.SMTP(smtp_host, smtp_port) as smtp:
        smtp.starttls()
        smtp.login(smtp_user, smtp_password)
        smtp.send_message(message)


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("logged_in"):
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        admin_user = authenticate_user(username, password, "admin")
        if admin_user or (username == ADMIN_USERNAME and password == ADMIN_PASSWORD):
            session.clear()
            session["logged_in"] = True
            session["username"] = username
            session["role"] = "admin"
            session["user_id"] = admin_user["id"] if admin_user else None
            flash("Welcome back to Warke Traders.", "success")
            return redirect(url_for("dashboard"))

        flash("Invalid username or password.", "danger")

    return render_template("login.html")


@app.route("/employee_login", methods=["GET", "POST"])
def employee_login():
    if session.get("logged_in"):
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        employee = authenticate_user(username, password, "employee")

        if employee:
            session.clear()
            session["logged_in"] = True
            session["username"] = employee["username"]
            session["role"] = "employee"
            session["user_id"] = employee["id"]
            flash("Employee login successful.", "success")
            return redirect(url_for("dashboard"))

        flash("Invalid employee username or password.", "danger")

    return render_template("employee_login.html")


@app.route("/logout")
@login_required
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


@app.route("/add_employee", methods=["GET", "POST"])
@admin_required
def add_employee():
    if request.method == "POST":
        try:
            password = request.form.get("password", "")
            confirm_password = request.form.get("confirm_password", "")
            if password != confirm_password:
                raise ValueError("Passwords do not match.")
            create_employee_user(request.form, request.files)
            flash("Employee account created successfully.", "success")
            return redirect(url_for("employees"))
        except ValueError as error:
            flash(str(error), "danger")
        except mysql.connector.Error as error:
            flash(f"Database error: {error}", "danger")

    return render_template("add_employee.html")


@app.route("/employees")
@admin_required
def employees():
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT id, username, full_name, mobile, email, address, aadhaar_number, profile_image, created_at
        FROM users
        WHERE role = 'employee'
        ORDER BY created_at DESC
        """
    )
    employee_rows = cursor.fetchall()
    cursor.close()
    connection.close()
    return render_template("employees.html", employees=employee_rows)


@app.route("/employees/<int:user_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_employee(user_id):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT id, username, full_name, mobile, email, address, aadhaar_number, profile_image
        FROM users
        WHERE id = %s AND role = 'employee'
        """,
        (user_id,),
    )
    employee = cursor.fetchone()
    cursor.close()
    connection.close()

    if not employee:
        flash("Employee not found.", "danger")
        return redirect(url_for("employees"))

    if request.method == "POST":
        try:
            update_employee_user(user_id, request.form, request.files)
            flash("Employee updated successfully.", "success")
            return redirect(url_for("employees"))
        except ValueError as error:
            flash(str(error), "danger")
        except mysql.connector.Error as error:
            flash(f"Database error: {error}", "danger")

    return render_template("edit_employee.html", employee=employee)


@app.route("/employees/<int:user_id>/delete", methods=["POST"])
@admin_required
def delete_employee(user_id):
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute("DELETE FROM users WHERE id = %s AND role = 'employee'", (user_id,))
    connection.commit()
    deleted_count = cursor.rowcount
    cursor.close()
    connection.close()

    if deleted_count:
        flash("Employee deleted successfully.", "success")
    else:
        flash("Employee not found.", "danger")
    return redirect(url_for("employees"))


@app.route("/employee_sales")
@admin_required
def employee_sales():
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT
            u.id,
            u.full_name,
            u.username,
            u.mobile,
            u.profile_image,
            COUNT(i.id) AS invoice_count,
            COALESCE(SUM(i.total_amount), 0) AS total_sales
        FROM users u
        LEFT JOIN invoices i ON i.user_id = u.id
        WHERE u.role = 'employee'
        GROUP BY u.id, u.full_name, u.username, u.mobile, u.profile_image
        ORDER BY total_sales DESC
        """
    )
    sales_rows = cursor.fetchall()
    cursor.close()
    connection.close()
    return render_template("employee_sales.html", employees=sales_rows)


@app.route("/employee/<int:user_id>/sales")
@admin_required
def employee_sales_detail(user_id):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT id, username, full_name, mobile, email, profile_image
        FROM users
        WHERE id = %s AND role = 'employee'
        """,
        (user_id,),
    )
    employee = cursor.fetchone()
    if not employee:
        cursor.close()
        connection.close()
        flash("Employee not found.", "danger")
        return redirect(url_for("employee_sales"))

    cursor.execute(
        """
        SELECT i.id, i.total_amount, i.created_at, c.name AS customer_name, c.mobile AS customer_mobile
        FROM invoices i
        JOIN customers c ON c.id = i.customer_id
        WHERE i.user_id = %s
        ORDER BY i.created_at DESC
        """,
        (user_id,),
    )
    invoices_rows = cursor.fetchall()
    cursor.close()
    connection.close()
    return render_template("employee_sales_detail.html", employee=employee, invoices=invoices_rows)


@app.route("/")
@app.route("/dashboard")
@login_required
def dashboard():
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    if is_admin():
        cursor.execute(
            """
            SELECT
                COUNT(*) AS total_products,
                COALESCE(SUM(stock_quantity), 0) AS total_stock,
                COALESCE(SUM(buying_price * stock_quantity), 0) AS total_investment,
                COALESCE(SUM((selling_price - buying_price) * stock_quantity), 0) AS potential_profit
            FROM products
            """
        )
    else:
        cursor.execute(
            """
            SELECT
                COUNT(*) AS total_products,
                COALESCE(SUM(stock_quantity), 0) AS total_stock
            FROM products
            """
        )
    stats = cursor.fetchone()

    cursor.execute(
        """
        SELECT id, item_name, buying_price, selling_price, stock_quantity
        FROM products
        ORDER BY created_at DESC
        LIMIT 5
        """
    )
    recent_products = cursor.fetchall()
    employee_stats = None
    if session.get("role") == "employee":
        cursor.execute(
            """
            SELECT
                COUNT(*) AS invoice_count,
                COALESCE(SUM(total_amount), 0) AS total_sales
            FROM invoices
            WHERE user_id = %s
            """,
            (session.get("user_id"),),
        )
        employee_stats = cursor.fetchone()

    cursor.close()
    connection.close()

    return render_template(
        "dashboard.html",
        stats=stats,
        recent_products=recent_products,
        employee_stats=employee_stats,
    )


@app.route("/products")
@admin_required
def products():
    search = request.args.get("search", "").strip()
    min_price = request.args.get("min_price", "").strip()
    max_price = request.args.get("max_price", "").strip()
    stock_filter = request.args.get("stock_filter", "").strip()
    page = request.args.get("page", 1, type=int)
    page = max(page, 1)

    where_clauses = []
    params = []

    if search:
        where_clauses.append("item_name LIKE %s")
        params.append(f"%{search}%")

    if min_price:
        try:
            where_clauses.append("selling_price >= %s")
            params.append(parse_positive_float(min_price, "Minimum price"))
        except ValueError as error:
            flash(str(error), "danger")

    if max_price:
        try:
            where_clauses.append("selling_price <= %s")
            params.append(parse_positive_float(max_price, "Maximum price"))
        except ValueError as error:
            flash(str(error), "danger")

    if stock_filter == "in_stock":
        where_clauses.append("stock_quantity > 0")
    elif stock_filter == "low_stock":
        where_clauses.append("stock_quantity > 0 AND stock_quantity <= 5")
    elif stock_filter == "out_of_stock":
        where_clauses.append("stock_quantity = 0")

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    offset = (page - 1) * PER_PAGE

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute(f"SELECT COUNT(*) AS total FROM products {where_sql}", params)
    total = cursor.fetchone()["total"]
    total_pages = max((total + PER_PAGE - 1) // PER_PAGE, 1)

    cursor.execute(
        f"""
        SELECT id, item_name, buying_price, selling_price, stock_quantity, created_at
        FROM products
        {where_sql}
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
        """,
        params + [PER_PAGE, offset],
    )
    product_rows = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "products.html",
        products=product_rows,
        search=search,
        min_price=min_price,
        max_price=max_price,
        stock_filter=stock_filter,
        page=page,
        total_pages=total_pages,
        total=total,
    )


@app.route("/billing", methods=["GET", "POST"])
@employee_required
def billing():
    if request.method == "POST":
        try:
            invoice_id, auto_send = create_invoice_from_form(request.form)
            flash("Invoice generated and stock updated successfully.", "success")
            if auto_send:
                try:
                    invoice, items = get_invoice_details(invoice_id)
                    if invoice and invoice["customer_email"]:
                        pdf_buffer = build_invoice_pdf(invoice, items)
                        send_email_with_attachment(
                            invoice["customer_email"],
                            f"Warke Traders Invoice #{invoice_id}",
                            "Thank you for shopping with Warke Traders. Your invoice is attached.",
                            pdf_buffer,
                            f"warke_traders_invoice_{invoice_id}.pdf",
                        )
                        flash("Invoice emailed to customer.", "success")
                    else:
                        flash("Invoice was created, but customer email is missing.", "warning")
                except ModuleNotFoundError:
                    flash("Invoice was created, but ReportLab is not installed for PDF email.", "warning")
                except Exception as error:
                    flash(f"Invoice was created, but email failed: {error}", "warning")
            return redirect(url_for("invoice_detail", invoice_id=invoice_id))
        except ValueError as error:
            flash(str(error), "danger")
        except mysql.connector.Error as error:
            flash(f"Database error: {error}", "danger")

    return render_template(
        "billing.html",
        customers=get_customers(),
        products=get_billable_products(),
    )


@app.route("/purchase", methods=["GET", "POST"])
@admin_required
def purchase():
    if request.method == "POST":
        try:
            purchase_id = create_purchase_from_form(request.form)
            flash("Purchase saved and stock updated successfully.", "success")
            return redirect(url_for("purchase_detail", purchase_id=purchase_id))
        except ValueError as error:
            flash(str(error), "danger")
        except mysql.connector.Error as error:
            flash(f"Database error: {error}", "danger")

    return render_template(
        "purchase.html",
        suppliers=get_suppliers(),
        products=get_purchase_products(),
    )


@app.route("/products/add", methods=["GET", "POST"])
@admin_required
def add_product():
    if request.method == "POST":
        try:
            product = validate_product_form(request.form)
            connection = get_db_connection()
            cursor = connection.cursor()
            cursor.execute(
                """
                INSERT INTO products (item_name, buying_price, selling_price, stock_quantity)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    product["item_name"],
                    product["buying_price"],
                    product["selling_price"],
                    product["stock_quantity"],
                ),
            )
            connection.commit()
            cursor.close()
            connection.close()
            flash("Product added successfully.", "success")
            return redirect(url_for("products"))
        except ValueError as error:
            flash(str(error), "danger")
        except mysql.connector.Error as error:
            flash(f"Database error: {error}", "danger")

    return render_template("product_form.html", product=None, form_title="Add Product")


@app.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_product(product_id):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("SELECT * FROM products WHERE id = %s", (product_id,))
    product = cursor.fetchone()

    if not product:
        cursor.close()
        connection.close()
        flash("Product not found.", "danger")
        return redirect(url_for("products"))

    if request.method == "POST":
        try:
            updated_product = validate_product_form(request.form)
            cursor.execute(
                """
                UPDATE products
                SET item_name = %s, buying_price = %s, selling_price = %s, stock_quantity = %s
                WHERE id = %s
                """,
                (
                    updated_product["item_name"],
                    updated_product["buying_price"],
                    updated_product["selling_price"],
                    updated_product["stock_quantity"],
                    product_id,
                ),
            )
            connection.commit()
            flash("Product updated successfully.", "success")
            cursor.close()
            connection.close()
            return redirect(url_for("products"))
        except ValueError as error:
            flash(str(error), "danger")
        except mysql.connector.Error as error:
            flash(f"Database error: {error}", "danger")

    cursor.close()
    connection.close()
    return render_template("product_form.html", product=product, form_title="Edit Product")


@app.route("/products/<int:product_id>/delete", methods=["POST"])
@admin_required
def delete_product(product_id):
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute("DELETE FROM products WHERE id = %s", (product_id,))
    connection.commit()
    deleted_count = cursor.rowcount
    cursor.close()
    connection.close()

    if deleted_count:
        flash("Product deleted successfully.", "success")
    else:
        flash("Product not found.", "danger")
    return redirect(url_for("products"))


@app.route("/products/export")
@admin_required
def export_products():
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT item_name, buying_price, selling_price, stock_quantity, created_at
        FROM products
        ORDER BY item_name
        """
    )
    product_rows = cursor.fetchall()
    cursor.close()
    connection.close()

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "Item Name",
            "Buying Price",
            "Selling Price",
            "Profit Per Item",
            "Stock Quantity",
            "Created At",
        ]
    )
    for product in product_rows:
        writer.writerow(
            [
                product["item_name"],
                product["buying_price"],
                product["selling_price"],
                product["selling_price"] - product["buying_price"],
                product["stock_quantity"],
                product["created_at"],
            ]
        )

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=warke_traders_products.csv"},
    )


@app.route("/invoices")
@employee_required
def invoices():
    search = request.args.get("search", "").strip()
    invoice_date = request.args.get("invoice_date", "").strip()
    where_clauses = []
    params = []

    if search:
        where_clauses.append("(c.name LIKE %s OR c.mobile LIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])
    if invoice_date:
        where_clauses.append("DATE(i.created_at) = %s")
        params.append(invoice_date)

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    cursor.execute(
        f"""
        SELECT
            i.id,
            i.total_amount,
            i.created_at,
            c.name AS customer_name,
            c.mobile AS customer_mobile,
            c.email AS customer_email
        FROM invoices i
        JOIN customers c ON c.id = i.customer_id
        {where_sql}
        ORDER BY i.created_at DESC
        """,
        params,
    )
    invoice_rows = cursor.fetchall()
    cursor.close()
    connection.close()

    return render_template(
        "invoices.html",
        invoices=invoice_rows,
        search=search,
        invoice_date=invoice_date,
    )


@app.route("/invoice/<int:invoice_id>")
@employee_required
def invoice_detail(invoice_id):
    invoice, items = get_invoice_details(invoice_id)
    if not invoice:
        flash("Invoice not found.", "danger")
        return redirect(url_for("invoices"))

    return render_template(
        "invoice.html",
        invoice=invoice,
        items=items,
        shop_address=SHOP_ADDRESS,
        shop_mobile=SHOP_MOBILE,
        shop_email=SHOP_EMAIL,
        whatsapp_url=build_invoice_whatsapp_url(invoice),
    )


@app.route("/invoice/<int:invoice_id>/pdf")
@employee_required
def invoice_pdf(invoice_id):
    invoice, items = get_invoice_details(invoice_id)
    if not invoice:
        flash("Invoice not found.", "danger")
        return redirect(url_for("invoices"))

    try:
        pdf_buffer = build_invoice_pdf(invoice, items)
    except ModuleNotFoundError:
        flash("ReportLab is not installed. Run: pip install -r requirements.txt", "danger")
        return redirect(url_for("invoice_detail", invoice_id=invoice_id))

    return Response(
        pdf_buffer.getvalue(),
        mimetype="application/pdf",
        headers={"Content-Disposition": f"inline; filename=warke_traders_invoice_{invoice_id}.pdf"},
    )


@app.route("/invoice/<int:invoice_id>/email", methods=["POST"])
@employee_required
def email_invoice(invoice_id):
    invoice, items = get_invoice_details(invoice_id)
    if not invoice:
        flash("Invoice not found.", "danger")
        return redirect(url_for("invoices"))
    if not invoice["customer_email"]:
        flash("Customer email is missing.", "warning")
        return redirect(url_for("invoice_detail", invoice_id=invoice_id))

    try:
        pdf_buffer = build_invoice_pdf(invoice, items)
        send_email_with_attachment(
            invoice["customer_email"],
            f"Warke Traders Invoice #{invoice_id}",
            "Thank you for shopping with Warke Traders. Your invoice PDF is attached.",
            pdf_buffer,
            f"warke_traders_invoice_{invoice_id}.pdf",
        )
        flash("Invoice emailed to customer successfully.", "success")
    except ModuleNotFoundError:
        flash("ReportLab is not installed. Run: pip install -r requirements.txt", "danger")
    except Exception as error:
        flash(f"Email failed: {error}", "danger")

    return redirect(url_for("invoice_detail", invoice_id=invoice_id))


@app.route("/purchases")
@admin_required
def purchases():
    search = request.args.get("search", "").strip()
    purchase_date = request.args.get("purchase_date", "").strip()
    where_clauses = []
    params = []

    if search:
        where_clauses.append("(s.name LIKE %s OR s.mobile LIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])
    if purchase_date:
        where_clauses.append("DATE(p.created_at) = %s")
        params.append(purchase_date)

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    cursor.execute(
        f"""
        SELECT
            p.id,
            p.total_amount,
            p.created_at,
            s.name AS supplier_name,
            s.mobile AS supplier_mobile
        FROM purchases p
        JOIN suppliers s ON s.id = p.supplier_id
        {where_sql}
        ORDER BY p.created_at DESC
        """,
        params,
    )
    purchase_rows = cursor.fetchall()
    cursor.close()
    connection.close()

    return render_template(
        "purchases.html",
        purchases=purchase_rows,
        search=search,
        purchase_date=purchase_date,
    )


@app.route("/purchase/<int:purchase_id>")
@admin_required
def purchase_detail(purchase_id):
    purchase_record, items = get_purchase_details(purchase_id)
    if not purchase_record:
        flash("Purchase not found.", "danger")
        return redirect(url_for("purchases"))

    return render_template(
        "purchase_detail.html",
        purchase=purchase_record,
        items=items,
        shop_address=SHOP_ADDRESS,
        shop_mobile=SHOP_MOBILE,
        shop_email=SHOP_EMAIL,
        whatsapp_url=build_purchase_whatsapp_url(purchase_record),
    )


@app.route("/purchase/<int:purchase_id>/pdf")
@admin_required
def purchase_pdf(purchase_id):
    purchase_record, items = get_purchase_details(purchase_id)
    if not purchase_record:
        flash("Purchase not found.", "danger")
        return redirect(url_for("purchases"))

    try:
        pdf_buffer = build_purchase_pdf(purchase_record, items)
    except ModuleNotFoundError:
        flash("ReportLab is not installed. Run: pip install -r requirements.txt", "danger")
        return redirect(url_for("purchase_detail", purchase_id=purchase_id))

    return Response(
        pdf_buffer.getvalue(),
        mimetype="application/pdf",
        headers={"Content-Disposition": f"inline; filename=warke_traders_purchase_{purchase_id}.pdf"},
    )


@app.route("/reports")
@admin_required
def reports():
    report_type = request.args.get("report_type", "all")
    if report_type not in {"all", "low_stock", "out_of_stock"}:
        report_type = "all"
    start_date = request.args.get("start_date", "").strip()
    end_date = request.args.get("end_date", "").strip()

    product_rows = get_report_products(report_type)
    billing_stats, daily_sales, top_items = get_billing_report(start_date, end_date)
    purchase_stats, daily_purchases, supplier_purchases = get_purchase_report(start_date, end_date)
    generated_at = datetime.now()

    return render_template(
        "reports.html",
        products=product_rows,
        report_type=report_type,
        start_date=start_date,
        end_date=end_date,
        billing_stats=billing_stats,
        daily_sales=daily_sales,
        top_items=top_items,
        purchase_stats=purchase_stats,
        daily_purchases=daily_purchases,
        supplier_purchases=supplier_purchases,
        generated_at=generated_at,
        shop_address=SHOP_ADDRESS,
        shop_mobile=SHOP_MOBILE,
        shop_email=SHOP_EMAIL,
    )


@app.route("/reports/pdf")
@admin_required
def reports_pdf():
    report_type = request.args.get("report_type", "all")
    if report_type not in {"all", "low_stock", "out_of_stock"}:
        report_type = "all"

    product_rows = get_report_products(report_type)
    try:
        pdf_buffer = build_inventory_pdf(product_rows, report_type)
    except ModuleNotFoundError:
        flash("ReportLab is not installed. Run: pip install -r requirements.txt", "danger")
        return redirect(url_for("reports", report_type=report_type))

    return Response(
        pdf_buffer.getvalue(),
        mimetype="application/pdf",
        headers={
            "Content-Disposition": "inline; filename=warke_traders_inventory_report.pdf",
        },
    )


@app.route("/reports/billing/pdf")
@admin_required
def billing_report_pdf():
    start_date = request.args.get("start_date", "").strip()
    end_date = request.args.get("end_date", "").strip()
    stats, daily_sales, top_items = get_billing_report(start_date, end_date)

    try:
        pdf_buffer = build_billing_report_pdf(stats, daily_sales, top_items, start_date, end_date)
    except ModuleNotFoundError:
        flash("ReportLab is not installed. Run: pip install -r requirements.txt", "danger")
        return redirect(url_for("reports", start_date=start_date, end_date=end_date))

    return Response(
        pdf_buffer.getvalue(),
        mimetype="application/pdf",
        headers={"Content-Disposition": "inline; filename=warke_traders_billing_report.pdf"},
    )


@app.route("/reports/billing/email", methods=["POST"])
@admin_required
def email_billing_report():
    start_date = request.form.get("start_date", "").strip()
    end_date = request.form.get("end_date", "").strip()
    stats, daily_sales, top_items = get_billing_report(start_date, end_date)

    try:
        pdf_buffer = build_billing_report_pdf(stats, daily_sales, top_items, start_date, end_date)
        send_email_with_attachment(
            OWNER_REPORT_EMAIL,
            "Warke Traders Daily Billing Report",
            "Please find the Warke Traders billing report attached.",
            pdf_buffer,
            "warke_traders_billing_report.pdf",
        )
        flash("Billing report emailed to shop owner.", "success")
    except ModuleNotFoundError:
        flash("ReportLab is not installed. Run: pip install -r requirements.txt", "danger")
    except Exception as error:
        flash(f"Email failed: {error}", "danger")

    return redirect(url_for("reports", start_date=start_date, end_date=end_date))


if __name__ == "__main__":
    app.run(debug=True)
