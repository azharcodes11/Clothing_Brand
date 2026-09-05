from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


def now_utc():
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(180), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(30))
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=now_utc, nullable=False)

    cart_items = db.relationship("CartItem", backref="user", cascade="all, delete-orphan")
    wishlist_items = db.relationship("WishlistItem", backref="user", cascade="all, delete-orphan")
    orders = db.relationship("Order", backref="customer", lazy=True)

    @property
    def is_active(self):
        return self.active

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    slug = db.Column(db.String(180), unique=True, nullable=False, index=True)
    sku = db.Column(db.String(60), unique=True, nullable=False, index=True)
    category = db.Column(db.String(80), nullable=False, index=True)
    gender = db.Column(db.String(20), nullable=False, index=True)
    collection = db.Column(db.String(80), default="Signature")
    short_description = db.Column(db.String(255), default="")
    description = db.Column(db.Text, default="")
    material = db.Column(db.Text, default="Premium fabric. Gentle care recommended.")
    price = db.Column(db.Float, nullable=False)
    original_price = db.Column(db.Float)
    stock = db.Column(db.Integer, default=0, nullable=False)
    low_stock_threshold = db.Column(db.Integer, default=5, nullable=False)
    sizes = db.Column(db.String(120), default="S,M,L,XL")
    colors = db.Column(db.String(160), default="Black,Ivory,Beige")
    image = db.Column(db.String(255), default="images/menswear.png")
    featured = db.Column(db.Boolean, default=False, nullable=False)
    new_arrival = db.Column(db.Boolean, default=False, nullable=False)
    best_seller = db.Column(db.Boolean, default=False, nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=now_utc, nullable=False)

    order_items = db.relationship("OrderItem", backref="product", lazy=True)

    @property
    def discount_percent(self):
        if self.original_price and self.original_price > self.price:
            return round((1 - self.price / self.original_price) * 100)
        return 0

    @property
    def size_list(self):
        return [value.strip() for value in self.sizes.split(",") if value.strip()]

    @property
    def color_list(self):
        return [value.strip() for value in self.colors.split(",") if value.strip()]


class CartItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    size = db.Column(db.String(30), nullable=False)
    color = db.Column(db.String(40), nullable=False)
    quantity = db.Column(db.Integer, default=1, nullable=False)
    product = db.relationship("Product")
    __table_args__ = (db.UniqueConstraint("user_id", "product_id", "size", "color"),)


class WishlistItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    product = db.relationship("Product")
    __table_args__ = (db.UniqueConstraint("user_id", "product_id"),)


class Coupon(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(40), unique=True, nullable=False, index=True)
    discount_type = db.Column(db.String(20), default="percent", nullable=False)
    value = db.Column(db.Float, nullable=False)
    min_order = db.Column(db.Float, default=0, nullable=False)
    max_discount = db.Column(db.Float)
    usage_limit = db.Column(db.Integer, default=100, nullable=False)
    used_count = db.Column(db.Integer, default=0, nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    expires_at = db.Column(db.DateTime(timezone=True))

    def calculate(self, subtotal):
        if not self.active or subtotal < self.min_order or self.used_count >= self.usage_limit:
            return 0
        discount = subtotal * self.value / 100 if self.discount_type == "percent" else self.value
        if self.max_discount:
            discount = min(discount, self.max_discount)
        return round(min(discount, subtotal), 2)


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(40), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True)
    customer_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(180), nullable=False)
    phone = db.Column(db.String(30), nullable=False)
    address = db.Column(db.String(240), nullable=False)
    city = db.Column(db.String(80), nullable=False)
    province = db.Column(db.String(80), nullable=False)
    postal_code = db.Column(db.String(20), nullable=False)
    country = db.Column(db.String(80), default="Pakistan")
    delivery_method = db.Column(db.String(30), default="standard")
    payment_method = db.Column(db.String(30), default="cod")
    status = db.Column(db.String(30), default="Pending", nullable=False, index=True)
    payment_status = db.Column(db.String(30), default="Unpaid", nullable=False)
    admin_notes = db.Column(db.Text, default="")
    subtotal = db.Column(db.Float, nullable=False)
    shipping = db.Column(db.Float, nullable=False)
    discount = db.Column(db.Float, default=0, nullable=False)
    total = db.Column(db.Float, nullable=False)
    coupon_code = db.Column(db.String(40))
    created_at = db.Column(db.DateTime(timezone=True), default=now_utc, nullable=False)
    items = db.relationship("OrderItem", backref="order", cascade="all, delete-orphan")
    history = db.relationship("OrderStatusHistory", backref="order", cascade="all, delete-orphan")


class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"))
    product_name = db.Column(db.String(160), nullable=False)
    product_sku = db.Column(db.String(60), nullable=False)
    size = db.Column(db.String(30), nullable=False)
    color = db.Column(db.String(40), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Float, nullable=False)


class OrderStatusHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"), nullable=False)
    status = db.Column(db.String(30), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=now_utc, nullable=False)


class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text, nullable=False)
    approved = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=now_utc, nullable=False)
    user = db.relationship("User")
    product = db.relationship("Product")


class NewsletterSubscriber(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(180), unique=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime(timezone=True), default=now_utc, nullable=False)


class ContactMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(180), nullable=False)
    phone = db.Column(db.String(30))
    subject = db.Column(db.String(180), nullable=False)
    message = db.Column(db.Text, nullable=False)
    read = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=now_utc, nullable=False)


class SiteSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(80), unique=True, nullable=False, index=True)
    value = db.Column(db.Text, default="")


class InventoryLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    change = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(180), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=now_utc, nullable=False)
    product = db.relationship("Product")

