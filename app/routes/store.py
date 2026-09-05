import re
import secrets
from datetime import datetime, timezone
from urllib.parse import urlsplit

from flask import (
    Blueprint, abort, flash, redirect, render_template, request, session, url_for
)
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import or_

from ..extensions import db
from ..models import (
    CartItem, ContactMessage, Coupon, InventoryLog, NewsletterSubscriber,
    Order, OrderItem, OrderStatusHistory, Product, Review, SiteSetting, User,
    WishlistItem,
)


store_bp = Blueprint("store", __name__)


def setting(key, default=""):
    row = SiteSetting.query.filter_by(key=key).first()
    return row.value if row else default


def safe_next_url(target):
    if not target:
        return None
    parsed = urlsplit(target)
    return target if not parsed.netloc and parsed.path.startswith("/") and not parsed.path.startswith("//") else None


def guest_cart():
    return session.setdefault("cart", [])


def cart_rows():
    rows = []
    source = CartItem.query.filter_by(user_id=current_user.id).all() if current_user.is_authenticated else guest_cart()
    for item in source:
        if current_user.is_authenticated:
            product, quantity, size, color, item_id = item.product, item.quantity, item.size, item.color, item.id
        else:
            product = db.session.get(Product, item.get("product_id"))
            quantity, size, color, item_id = item.get("quantity", 1), item.get("size", ""), item.get("color", ""), None
        if product and product.active:
            quantity = max(1, min(int(quantity), product.stock)) if product.stock else 0
            if quantity:
                rows.append({"id": item_id, "product": product, "quantity": quantity, "size": size,
                             "color": color, "line_total": round(product.price * quantity, 2)})
    return rows


def cart_totals(rows, coupon_code=None, delivery="standard"):
    subtotal = round(sum(row["line_total"] for row in rows), 2)
    free_threshold = float(setting("free_delivery_threshold", "5000"))
    shipping = 0 if subtotal >= free_threshold else (550 if delivery == "express" else 250)
    discount = 0
    coupon = None
    if coupon_code:
        coupon = Coupon.query.filter_by(code=coupon_code.strip().upper()).first()
        if coupon:
            if coupon.expires_at:
                expires = coupon.expires_at
                if expires.tzinfo is None:
                    expires = expires.replace(tzinfo=timezone.utc)
                if expires < datetime.now(timezone.utc):
                    coupon = None
            if coupon:
                discount = coupon.calculate(subtotal)
    return {"subtotal": subtotal, "shipping": shipping, "discount": discount,
            "total": round(subtotal + shipping - discount, 2), "coupon": coupon}


def merge_guest_cart(user):
    for guest in session.pop("cart", []):
        product = db.session.get(Product, guest.get("product_id"))
        if not product or not product.active or product.stock < 1:
            continue
        size, color = guest.get("size", ""), guest.get("color", "")
        item = CartItem.query.filter_by(user_id=user.id, product_id=product.id, size=size, color=color).first()
        quantity = max(1, min(int(guest.get("quantity", 1)), product.stock))
        if item:
            item.quantity = min(item.quantity + quantity, product.stock)
        else:
            db.session.add(CartItem(user_id=user.id, product_id=product.id, size=size, color=color, quantity=quantity))
    db.session.commit()


@store_bp.app_context_processor
def global_context():
    if current_user.is_authenticated:
        cart_count = db.session.query(db.func.coalesce(db.func.sum(CartItem.quantity), 0)).filter_by(user_id=current_user.id).scalar()
        wishlist_count = WishlistItem.query.filter_by(user_id=current_user.id).count()
    else:
        cart_count = sum(int(item.get("quantity", 0)) for item in session.get("cart", []))
        wishlist_count = 0
    return {
        "cart_count": cart_count, "wishlist_count": wishlist_count, "site_setting": setting,
        "announcement": setting("announcement", "Complimentary delivery on orders over Rs. 5,000"),
    }


@store_bp.get("/")
def home():
    featured = Product.query.filter_by(active=True, featured=True).limit(4).all()
    arrivals = Product.query.filter_by(active=True, new_arrival=True).limit(6).all()
    best = Product.query.filter_by(active=True, best_seller=True).limit(4).all()
    return render_template("customer/home.html", featured=featured, arrivals=arrivals, best=best)


@store_bp.get("/shop")
@store_bp.get("/shop/<gender>")
def shop(gender=None):
    gender = gender or request.args.get("gender")
    query = Product.query.filter_by(active=True)
    search = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    collection = request.args.get("collection", "").strip()
    size = request.args.get("size", "").strip()
    color = request.args.get("color", "").strip()
    availability = request.args.get("availability", "").strip()
    discount = request.args.get("discount", "").strip()
    min_price = request.args.get("min_price", type=float)
    max_price = request.args.get("max_price", type=float)
    if gender and gender.lower() in {"men", "women"}:
        query = query.filter(db.func.lower(Product.gender) == gender.lower())
    if search:
        query = query.filter(or_(Product.name.ilike(f"%{search}%"), Product.description.ilike(f"%{search}%"), Product.category.ilike(f"%{search}%")))
    if category:
        query = query.filter(Product.category == category)
    if collection:
        query = query.filter(Product.collection == collection)
    if size:
        query = query.filter(Product.sizes.ilike(f"%{size}%"))
    if color:
        query = query.filter(Product.colors.ilike(f"%{color}%"))
    if min_price is not None:
        query = query.filter(Product.price >= min_price)
    if max_price is not None:
        query = query.filter(Product.price <= max_price)
    if availability == "in_stock":
        query = query.filter(Product.stock > 0)
    if discount == "yes":
        query = query.filter(Product.original_price > Product.price)
    sort = request.args.get("sort", "latest")
    orders = {
        "latest": Product.created_at.desc(), "popular": Product.best_seller.desc(),
        "price_low": Product.price.asc(), "price_high": Product.price.desc(),
    }
    query = query.order_by(orders.get(sort, Product.created_at.desc()))
    page = request.args.get("page", 1, type=int)
    products = query.paginate(page=page, per_page=9, error_out=False)
    categories = [r[0] for r in db.session.query(Product.category).distinct().order_by(Product.category)]
    collections = [r[0] for r in db.session.query(Product.collection).distinct().order_by(Product.collection)]
    pagination_args = request.args.to_dict()
    pagination_args.pop("page", None)
    pagination_args.pop("gender", None)
    return render_template("customer/shop.html", products=products, categories=categories,
                           collections=collections, selected_gender=gender,
                           pagination_args=pagination_args)


@store_bp.get("/new-arrivals")
def new_arrivals():
    products = Product.query.filter_by(active=True, new_arrival=True).order_by(Product.created_at.desc()).all()
    return render_template("customer/product_listing.html", title="New Arrivals", products=products,
                           intro="The latest expressions of quiet confidence.")


@store_bp.get("/collections")
def collections():
    names = [r[0] for r in db.session.query(Product.collection).distinct().order_by(Product.collection)]
    return render_template("customer/collections.html", collections=names)


@store_bp.get("/product/<slug>")
def product_detail(slug):
    product = Product.query.filter_by(slug=slug, active=True).first_or_404()
    related = Product.query.filter(Product.id != product.id, Product.category == product.category, Product.active.is_(True)).limit(4).all()
    reviews = Review.query.filter_by(product_id=product.id, approved=True).order_by(Review.created_at.desc()).all()
    session["recent_products"] = ([product.id] + [p for p in session.get("recent_products", []) if p != product.id])[:4]
    return render_template("customer/product_detail.html", product=product, related=related, reviews=reviews)


@store_bp.post("/cart/add/<int:product_id>")
def add_to_cart(product_id):
    product = db.session.get(Product, product_id)
    if not product or not product.active:
        abort(404)
    size = request.form.get("size", product.size_list[0] if product.size_list else "One Size")
    color = request.form.get("color", product.color_list[0] if product.color_list else "Default")
    quantity = max(1, request.form.get("quantity", 1, type=int))
    if size not in product.size_list or color not in product.color_list:
        flash("Please select a valid size and colour.", "error")
        return redirect(url_for("store.product_detail", slug=product.slug))
    if product.stock < 1:
        flash("This item is currently out of stock.", "error")
        return redirect(request.referrer or url_for("store.shop"))
    quantity = min(quantity, product.stock)
    if current_user.is_authenticated:
        item = CartItem.query.filter_by(user_id=current_user.id, product_id=product.id, size=size, color=color).first()
        if item:
            item.quantity = min(item.quantity + quantity, product.stock)
        else:
            db.session.add(CartItem(user_id=current_user.id, product_id=product.id, size=size, color=color, quantity=quantity))
        db.session.commit()
    else:
        cart = guest_cart()
        item = next((i for i in cart if i["product_id"] == product.id and i["size"] == size and i["color"] == color), None)
        if item:
            item["quantity"] = min(item["quantity"] + quantity, product.stock)
        else:
            cart.append({"product_id": product.id, "size": size, "color": color, "quantity": quantity})
        session.modified = True
    flash(f"{product.name} added to your bag.", "success")
    return redirect(request.form.get("next") or request.referrer or url_for("store.cart"))


@store_bp.route("/cart", methods=["GET", "POST"])
def cart():
    if request.method == "POST":
        action = request.form.get("action")
        identifier = request.form.get("item")
        quantity = max(1, request.form.get("quantity", 1, type=int))
        if current_user.is_authenticated:
            item = CartItem.query.filter_by(id=identifier, user_id=current_user.id).first_or_404()
            if action == "remove":
                db.session.delete(item)
            else:
                item.quantity = min(quantity, item.product.stock)
            db.session.commit()
        else:
            index = int(identifier)
            guest = guest_cart()
            if 0 <= index < len(guest):
                if action == "remove":
                    guest.pop(index)
                else:
                    product = db.session.get(Product, guest[index]["product_id"])
                    guest[index]["quantity"] = min(quantity, product.stock) if product else 1
                session.modified = True
        return redirect(url_for("store.cart"))
    rows = cart_rows()
    totals = cart_totals(rows, request.args.get("coupon"))
    return render_template("customer/cart.html", rows=rows, totals=totals)


@store_bp.post("/wishlist/<int:product_id>")
@login_required
def toggle_wishlist(product_id):
    product = Product.query.filter_by(id=product_id, active=True).first_or_404()
    item = WishlistItem.query.filter_by(user_id=current_user.id, product_id=product.id).first()
    if item:
        db.session.delete(item)
        flash("Removed from wishlist.", "info")
    else:
        db.session.add(WishlistItem(user_id=current_user.id, product_id=product.id))
        flash("Saved to wishlist.", "success")
    db.session.commit()
    return redirect(request.referrer or url_for("store.wishlist"))


@store_bp.get("/wishlist")
@login_required
def wishlist():
    return render_template("customer/wishlist.html", items=WishlistItem.query.filter_by(user_id=current_user.id).all())


@store_bp.route("/checkout", methods=["GET", "POST"])
def checkout():
    rows = cart_rows()
    if not rows:
        flash("Your shopping bag is empty.", "info")
        return redirect(url_for("store.shop"))
    delivery = request.form.get("delivery_method", "standard") if request.method == "POST" else "standard"
    coupon_code = request.form.get("coupon", "")
    totals = cart_totals(rows, coupon_code, delivery)
    if request.method == "POST":
        required = ["name", "email", "phone", "address", "city", "province", "postal_code"]
        if any(not request.form.get(field, "").strip() for field in required):
            flash("Please complete all required checkout fields.", "error")
            return render_template("customer/checkout.html", rows=rows, totals=totals)
        for row in rows:
            db.session.refresh(row["product"])
            if row["quantity"] > row["product"].stock:
                flash(f"Only {row['product'].stock} units of {row['product'].name} remain.", "error")
                return redirect(url_for("store.cart"))
        order = Order(
            order_number=f"AUR-{datetime.now():%y%m%d}-{secrets.token_hex(3).upper()}",
            user_id=current_user.id if current_user.is_authenticated else None,
            customer_name=request.form["name"].strip(), email=request.form["email"].strip().lower(),
            phone=request.form["phone"].strip(), address=request.form["address"].strip(),
            city=request.form["city"].strip(), province=request.form["province"].strip(),
            postal_code=request.form["postal_code"].strip(), delivery_method=delivery,
            payment_method=request.form.get("payment_method", "cod"), subtotal=totals["subtotal"],
            shipping=totals["shipping"], discount=totals["discount"], total=totals["total"],
            coupon_code=totals["coupon"].code if totals["coupon"] else None,
        )
        db.session.add(order)
        db.session.flush()
        for row in rows:
            product = row["product"]
            product.stock -= row["quantity"]
            db.session.add(OrderItem(order_id=order.id, product_id=product.id, product_name=product.name,
                                     product_sku=product.sku, size=row["size"], color=row["color"],
                                     quantity=row["quantity"], unit_price=product.price))
            db.session.add(InventoryLog(product_id=product.id, change=-row["quantity"], reason=f"Order {order.order_number}"))
        db.session.add(OrderStatusHistory(order_id=order.id, status="Pending"))
        if totals["coupon"]:
            totals["coupon"].used_count += 1
        if current_user.is_authenticated:
            CartItem.query.filter_by(user_id=current_user.id).delete()
        else:
            session.pop("cart", None)
        db.session.commit()
        session["last_order_email"] = order.email
        return redirect(url_for("store.order_confirmation", order_number=order.order_number))
    return render_template("customer/checkout.html", rows=rows, totals=totals)


@store_bp.get("/order-confirmation/<order_number>")
def order_confirmation(order_number):
    order = Order.query.filter_by(order_number=order_number).first_or_404()
    allowed = current_user.is_authenticated and (current_user.id == order.user_id or current_user.is_admin)
    if not allowed and session.get("last_order_email") != order.email:
        abort(403)
    return render_template("customer/order_confirmation.html", order=order)


@store_bp.route("/track-order", methods=["GET", "POST"])
def track_order():
    order = None
    if request.method == "POST":
        number = request.form.get("order_number", "").strip().upper()
        email = request.form.get("email", "").strip().lower()
        order = Order.query.filter_by(order_number=number, email=email).first()
        if not order:
            flash("We could not find an order with those details.", "error")
    return render_template("customer/track_order.html", order=order)


@store_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("store.profile"))
    if request.method == "POST":
        user = User.query.filter_by(email=request.form.get("email", "").strip().lower()).first()
        if user and not user.is_admin and user.check_password(request.form.get("password", "")) and user.active:
            login_user(user, remember=bool(request.form.get("remember")))
            merge_guest_cart(user)
            flash("Welcome back to AUREN.", "success")
            return redirect(safe_next_url(request.args.get("next")) or url_for("store.profile"))
        flash("Invalid email or password.", "error")
    return render_template("customer/auth.html", mode="login")


@store_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("store.profile"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if len(name) < 2 or not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email) or len(password) < 8:
            flash("Use a valid name, email, and password of at least 8 characters.", "error")
        elif User.query.filter_by(email=email).first():
            flash("An account with this email already exists.", "error")
        else:
            user = User(name=name, email=email, phone=request.form.get("phone", "").strip())
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            merge_guest_cart(user)
            flash("Your AUREN account is ready.", "success")
            return redirect(url_for("store.profile"))
    return render_template("customer/auth.html", mode="register")


@store_bp.post("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been signed out.", "info")
    return redirect(url_for("store.home"))


@store_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        current_user.name = request.form.get("name", current_user.name).strip()
        current_user.phone = request.form.get("phone", "").strip()
        new_password = request.form.get("new_password", "")
        if new_password:
            if len(new_password) < 8:
                flash("New password must have at least 8 characters.", "error")
                return redirect(url_for("store.profile"))
            current_user.set_password(new_password)
        db.session.commit()
        flash("Profile updated.", "success")
    orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).all()
    return render_template("customer/profile.html", orders=orders)


@store_bp.post("/order/<int:order_id>/cancel")
@login_required
def cancel_order(order_id):
    order = Order.query.filter_by(id=order_id, user_id=current_user.id).first_or_404()
    if order.status not in {"Pending", "Confirmed"}:
        flash("This order can no longer be cancelled online.", "error")
    else:
        order.status = "Cancelled"
        for item in order.items:
            if item.product:
                item.product.stock += item.quantity
                db.session.add(InventoryLog(product_id=item.product.id, change=item.quantity,
                                             reason=f"Cancelled {order.order_number}"))
        db.session.add(OrderStatusHistory(order_id=order.id, status="Cancelled"))
        db.session.commit()
        flash("Order cancelled and stock restored.", "success")
    return redirect(url_for("store.profile"))


@store_bp.post("/review/<int:product_id>")
@login_required
def add_review(product_id):
    purchased = db.session.query(OrderItem).join(Order).filter(
        Order.user_id == current_user.id, Order.status == "Delivered", OrderItem.product_id == product_id
    ).first()
    if not purchased:
        flash("Reviews are available after a delivered purchase.", "error")
    else:
        rating = max(1, min(5, request.form.get("rating", 5, type=int)))
        comment = request.form.get("comment", "").strip()
        if comment:
            db.session.add(Review(product_id=product_id, user_id=current_user.id, rating=rating, comment=comment))
            db.session.commit()
            flash("Thank you. Your review is awaiting approval.", "success")
    return redirect(request.referrer or url_for("store.shop"))


@store_bp.post("/newsletter")
def newsletter():
    email = request.form.get("email", "").strip().lower()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        flash("Please enter a valid email address.", "error")
    elif NewsletterSubscriber.query.filter_by(email=email).first():
        flash("You are already on the AUREN list.", "info")
    else:
        db.session.add(NewsletterSubscriber(email=email))
        db.session.commit()
        flash("Welcome to the AUREN journal.", "success")
    return redirect(request.referrer or url_for("store.home"))


@store_bp.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        fields = {key: request.form.get(key, "").strip() for key in ["name", "email", "phone", "subject", "message"]}
        if not all(fields[key] for key in ["name", "email", "subject", "message"]):
            flash("Please complete all required fields.", "error")
        else:
            db.session.add(ContactMessage(**fields))
            db.session.commit()
            flash("Your message has been received.", "success")
            return redirect(url_for("store.contact"))
    return render_template("customer/contact.html")


@store_bp.get("/about")
def about():
    return render_template("customer/content.html", title="The AUREN Story", eyebrow="OUR PHILOSOPHY",
                           content="AUREN creates considered clothing for a confident modern life. Every collection balances precise tailoring, enduring materials and a restrained visual language. We design fewer, better pieces—made to feel relevant today and remain meaningful tomorrow.")


CONTENT_PAGES = {
    "faq": ("Frequently Asked Questions", "Find clear answers about orders, delivery, sizing and returns."),
    "size-guide": ("Size Guide", "Choose your usual size for a tailored fit. Product pages list available sizes; contact our team if you need help selecting one."),
    "shipping-returns": ("Shipping & Returns", "Standard delivery usually arrives within 3–5 business days. Unworn items with original tags may be returned within 14 days."),
    "privacy": ("Privacy Policy", "We use the information you provide only to manage your account, orders and requested updates. Sensitive card information is never stored by this application."),
    "terms": ("Terms & Conditions", "Orders are subject to stock availability and confirmation. Product colours may vary slightly by display. Your statutory consumer rights remain unaffected."),
}


@store_bp.get("/pages/<slug>")
def content_page(slug):
    if slug not in CONTENT_PAGES:
        abort(404)
    title, content = CONTENT_PAGES[slug]
    return render_template("customer/content.html", title=title, eyebrow="AUREN CLIENT CARE", content=content)


@store_bp.get("/robots.txt")
def robots():
    return "User-agent: *\nAllow: /\nSitemap: /sitemap.xml\n", 200, {"Content-Type": "text/plain"}


@store_bp.get("/sitemap.xml")
def sitemap():
    urls = [url_for("store.home", _external=True), url_for("store.shop", _external=True),
            url_for("store.about", _external=True), url_for("store.contact", _external=True)]
    urls += [url_for("store.product_detail", slug=p.slug, _external=True) for p in Product.query.filter_by(active=True).all()]
    body = "".join(f"<url><loc>{url}</loc></url>" for url in urls)
    return f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{body}</urlset>', 200, {"Content-Type": "application/xml"}
