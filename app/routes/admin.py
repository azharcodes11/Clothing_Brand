import csv
import io
import secrets
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_user, logout_user
from sqlalchemy import func, or_
from werkzeug.utils import secure_filename

from ..extensions import db
from ..models import (
    ContactMessage, Coupon, InventoryLog, NewsletterSubscriber, Order,
    OrderItem, OrderStatusHistory, Product, Review, SiteSetting, User,
)


admin_bp = Blueprint("admin", __name__, url_prefix="/admin")
ALLOWED_IMAGES = {"png", "jpg", "jpeg", "webp"}
ORDER_STATUSES = ["Pending", "Confirmed", "Processing", "Shipped", "Delivered", "Cancelled", "Returned"]


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def save_image(file):
    if not file or not file.filename:
        return None
    extension = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if extension not in ALLOWED_IMAGES:
        raise ValueError("Only PNG, JPG, JPEG and WEBP files are allowed.")
    filename = f"{secrets.token_hex(8)}-{secure_filename(file.filename)}"
    file.save(Path(current_app.root_path, "static", "uploads", filename))
    return f"uploads/{filename}"


def product_from_form(product=None):
    product = product or Product()
    old_stock = product.stock or 0
    product.name = request.form.get("name", "").strip()
    product.slug = request.form.get("slug", "").strip().lower().replace(" ", "-")
    product.sku = request.form.get("sku", "").strip().upper()
    product.category = request.form.get("category", "").strip()
    product.gender = request.form.get("gender", "Unisex").strip()
    product.collection = request.form.get("collection", "Signature").strip()
    product.short_description = request.form.get("short_description", "").strip()
    product.description = request.form.get("description", "").strip()
    product.material = request.form.get("material", "").strip()
    product.price = max(0, request.form.get("price", 0, type=float))
    product.original_price = request.form.get("original_price", type=float)
    product.stock = max(0, request.form.get("stock", 0, type=int))
    product.low_stock_threshold = max(0, request.form.get("low_stock_threshold", 5, type=int))
    product.sizes = request.form.get("sizes", "S,M,L,XL").strip()
    product.colors = request.form.get("colors", "Black,Ivory,Beige").strip()
    product.featured = bool(request.form.get("featured"))
    product.new_arrival = bool(request.form.get("new_arrival"))
    product.best_seller = bool(request.form.get("best_seller"))
    product.active = bool(request.form.get("active"))
    uploaded = save_image(request.files.get("image"))
    if uploaded:
        product.image = uploaded
    if product.id and old_stock != product.stock:
        db.session.add(InventoryLog(product_id=product.id, change=product.stock - old_stock, reason="Manual admin adjustment"))
    return product


@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated and current_user.is_admin:
        return redirect(url_for("admin.dashboard"))
    if request.method == "POST":
        user = User.query.filter_by(email=request.form.get("email", "").strip().lower(), is_admin=True).first()
        if user and user.active and user.check_password(request.form.get("password", "")):
            login_user(user)
            return redirect(url_for("admin.dashboard"))
        flash("Invalid administrator credentials.", "error")
    return render_template("admin/login.html")


@admin_bp.post("/logout")
@admin_required
def logout():
    logout_user()
    return redirect(url_for("admin.login"))


@admin_bp.get("/")
@admin_required
def dashboard():
    total_revenue = db.session.query(func.coalesce(func.sum(Order.total), 0)).filter(Order.status != "Cancelled").scalar()
    today_revenue = db.session.query(func.coalesce(func.sum(Order.total), 0)).filter(
        func.date(Order.created_at) == datetime.now(timezone.utc).date(), Order.status != "Cancelled"
    ).scalar()
    status_rows = db.session.query(Order.status, func.count(Order.id)).group_by(Order.status).all()
    status_counts = {status: count for status, count in status_rows}
    best_sellers = db.session.query(Product, func.coalesce(func.sum(OrderItem.quantity), 0).label("sold")).outerjoin(
        OrderItem, Product.id == OrderItem.product_id
    ).group_by(Product.id).order_by(db.desc("sold")).limit(5).all()
    stats = {
        "total_revenue": total_revenue, "today_revenue": today_revenue,
        "orders": Order.query.count(), "pending": status_counts.get("Pending", 0),
        "completed": status_counts.get("Delivered", 0), "cancelled": status_counts.get("Cancelled", 0),
        "customers": User.query.filter_by(is_admin=False).count(), "products": Product.query.count(),
        "low_stock": Product.query.filter(Product.stock > 0, Product.stock <= Product.low_stock_threshold).count(),
        "out_stock": Product.query.filter_by(stock=0).count(), "subscribers": NewsletterSubscriber.query.count(),
    }
    max_status = max(status_counts.values(), default=1)
    return render_template("admin/dashboard.html", stats=stats, status_counts=status_counts,
                           max_status=max_status, best_sellers=best_sellers,
                           recent_orders=Order.query.order_by(Order.created_at.desc()).limit(6).all(),
                           low_products=Product.query.filter(Product.stock <= Product.low_stock_threshold).order_by(Product.stock).limit(6).all())


@admin_bp.get("/products")
@admin_required
def products():
    query = Product.query
    q = request.args.get("q", "").strip()
    if q:
        query = query.filter(or_(Product.name.ilike(f"%{q}%"), Product.sku.ilike(f"%{q}%")))
    return render_template("admin/products.html", products=query.order_by(Product.created_at.desc()).all())


@admin_bp.route("/products/new", methods=["GET", "POST"])
@admin_required
def product_new():
    if request.method == "POST":
        try:
            product = product_from_form()
            if not all([product.name, product.slug, product.sku, product.category]):
                raise ValueError("Name, slug, SKU and category are required.")
            db.session.add(product)
            db.session.commit()
            flash("Product created.", "success")
            return redirect(url_for("admin.products"))
        except (ValueError, TypeError) as error:
            db.session.rollback()
            flash(str(error), "error")
        except Exception:
            db.session.rollback()
            flash("Slug and SKU must be unique.", "error")
    return render_template("admin/product_form.html", product=None)


@admin_bp.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
@admin_required
def product_edit(product_id):
    product = db.session.get(Product, product_id) or abort(404)
    if request.method == "POST":
        try:
            product_from_form(product)
            db.session.commit()
            flash("Product updated.", "success")
            return redirect(url_for("admin.products"))
        except ValueError as error:
            db.session.rollback()
            flash(str(error), "error")
    return render_template("admin/product_form.html", product=product)


@admin_bp.post("/products/<int:product_id>/duplicate")
@admin_required
def product_duplicate(product_id):
    source = db.session.get(Product, product_id) or abort(404)
    copy = Product(name=f"{source.name} Copy", slug=f"{source.slug}-copy-{secrets.token_hex(2)}",
                   sku=f"{source.sku}-COPY-{secrets.token_hex(2).upper()}", category=source.category,
                   gender=source.gender, collection=source.collection, short_description=source.short_description,
                   description=source.description, material=source.material, price=source.price,
                   original_price=source.original_price, stock=source.stock, sizes=source.sizes,
                   colors=source.colors, image=source.image, active=False)
    db.session.add(copy)
    db.session.commit()
    flash("Draft copy created.", "success")
    return redirect(url_for("admin.product_edit", product_id=copy.id))


@admin_bp.post("/products/<int:product_id>/archive")
@admin_required
def product_archive(product_id):
    product = db.session.get(Product, product_id) or abort(404)
    product.active = not product.active
    db.session.commit()
    flash("Product status updated.", "success")
    return redirect(url_for("admin.products"))


@admin_bp.get("/orders")
@admin_required
def orders():
    query = Order.query
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "")
    if q:
        query = query.filter(or_(Order.order_number.ilike(f"%{q}%"), Order.customer_name.ilike(f"%{q}%")))
    if status:
        query = query.filter_by(status=status)
    return render_template("admin/orders.html", orders=query.order_by(Order.created_at.desc()).all(), statuses=ORDER_STATUSES)


@admin_bp.post("/orders/<int:order_id>/update")
@admin_required
def order_update(order_id):
    order = db.session.get(Order, order_id) or abort(404)
    new_status = request.form.get("status")
    if new_status not in ORDER_STATUSES:
        abort(400)
    if new_status != order.status:
        order.status = new_status
        db.session.add(OrderStatusHistory(order_id=order.id, status=new_status))
    order.payment_status = request.form.get("payment_status", order.payment_status)
    order.admin_notes = request.form.get("admin_notes", "").strip()
    db.session.commit()
    flash("Order updated.", "success")
    return redirect(url_for("admin.orders"))


@admin_bp.get("/orders/export.csv")
@admin_required
def export_orders():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Order", "Customer", "Email", "Status", "Payment", "Total", "Date"])
    for order in Order.query.order_by(Order.created_at.desc()):
        writer.writerow([order.order_number, order.customer_name, order.email, order.status,
                         order.payment_status, order.total, order.created_at.isoformat()])
    memory = io.BytesIO(output.getvalue().encode("utf-8-sig"))
    return send_file(memory, mimetype="text/csv", as_attachment=True, download_name="auren-orders.csv")


@admin_bp.get("/customers")
@admin_required
def customers():
    users = User.query.filter_by(is_admin=False).order_by(User.created_at.desc()).all()
    spending = dict(db.session.query(Order.user_id, func.coalesce(func.sum(Order.total), 0)).filter(
        Order.status != "Cancelled", Order.user_id.isnot(None)
    ).group_by(Order.user_id).all())
    return render_template("admin/customers.html", users=users, spending=spending)


@admin_bp.post("/customers/<int:user_id>/toggle")
@admin_required
def customer_toggle(user_id):
    user = User.query.filter_by(id=user_id, is_admin=False).first_or_404()
    user.active = not user.active
    db.session.commit()
    flash("Customer access updated.", "success")
    return redirect(url_for("admin.customers"))


@admin_bp.route("/coupons", methods=["GET", "POST"])
@admin_required
def coupons():
    if request.method == "POST":
        code = request.form.get("code", "").strip().upper()
        if not code or Coupon.query.filter_by(code=code).first():
            flash("Enter a unique coupon code.", "error")
        else:
            coupon = Coupon(code=code, discount_type=request.form.get("discount_type", "percent"),
                            value=max(0, request.form.get("value", 0, type=float)),
                            min_order=max(0, request.form.get("min_order", 0, type=float)),
                            max_discount=request.form.get("max_discount", type=float),
                            usage_limit=max(1, request.form.get("usage_limit", 100, type=int)), active=True)
            db.session.add(coupon)
            db.session.commit()
            flash("Coupon created.", "success")
            return redirect(url_for("admin.coupons"))
    return render_template("admin/coupons.html", coupons=Coupon.query.order_by(Coupon.id.desc()).all())


@admin_bp.post("/coupons/<int:coupon_id>/toggle")
@admin_required
def coupon_toggle(coupon_id):
    coupon = db.session.get(Coupon, coupon_id) or abort(404)
    coupon.active = not coupon.active
    db.session.commit()
    return redirect(url_for("admin.coupons"))


@admin_bp.route("/settings", methods=["GET", "POST"])
@admin_required
def settings():
    keys = ["announcement", "hero_title", "hero_subtitle", "free_delivery_threshold", "contact_email", "contact_phone", "instagram"]
    if request.method == "POST":
        for key in keys:
            row = SiteSetting.query.filter_by(key=key).first() or SiteSetting(key=key)
            row.value = request.form.get(key, "").strip()
            db.session.add(row)
        db.session.commit()
        flash("Website settings updated.", "success")
    values = {key: (SiteSetting.query.filter_by(key=key).first().value if SiteSetting.query.filter_by(key=key).first() else "") for key in keys}
    return render_template("admin/settings.html", values=values)


@admin_bp.get("/messages")
@admin_required
def messages():
    return render_template("admin/messages.html",
                           messages=ContactMessage.query.order_by(ContactMessage.created_at.desc()).all(),
                           reviews=Review.query.order_by(Review.created_at.desc()).all())


@admin_bp.post("/messages/<int:message_id>/read")
@admin_required
def message_read(message_id):
    message = db.session.get(ContactMessage, message_id) or abort(404)
    message.read = True
    db.session.commit()
    return redirect(url_for("admin.messages"))


@admin_bp.post("/reviews/<int:review_id>/<action>")
@admin_required
def review_action(review_id, action):
    review = db.session.get(Review, review_id) or abort(404)
    if action == "approve":
        review.approved = True
    elif action == "reject":
        review.approved = False
    elif action == "delete":
        db.session.delete(review)
    else:
        abort(400)
    db.session.commit()
    return redirect(url_for("admin.messages"))
