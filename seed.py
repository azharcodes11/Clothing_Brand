import argparse

from app import create_app
from app.extensions import db
from app.models import Coupon, Product, SiteSetting, User


PRODUCTS = [
    ("Signature Overshirt", "signature-overshirt", "AUR-M-001", "Shirts", "Men", "Essential Forms", 6490, 7490, 18, "menswear.png"),
    ("Ivory Knit Polo", "ivory-knit-polo", "AUR-M-002", "T-Shirts", "Men", "Essential Forms", 4290, None, 24, "menswear.png"),
    ("Architect Trouser", "architect-trouser", "AUR-M-003", "Trousers", "Men", "Quiet Form", 5990, 6990, 15, "menswear.png"),
    ("Stone Harrington", "stone-harrington", "AUR-M-004", "Jackets", "Men", "Quiet Form", 11990, 13990, 7, "menswear.png"),
    ("Noir Essential Tee", "noir-essential-tee", "AUR-M-005", "T-Shirts", "Men", "Monochrome", 2990, None, 30, "menswear.png"),
    ("Structure Hoodie", "structure-hoodie", "AUR-M-006", "Hoodies", "Men", "Monochrome", 7490, 8490, 11, "menswear.png"),
    ("Ivory Column Dress", "ivory-column-dress", "AUR-W-001", "Dresses", "Women", "Quiet Form", 10490, 12490, 12, "womenswear.png"),
    ("Sculpted Beige Coat", "sculpted-beige-coat", "AUR-W-002", "Jackets", "Women", "Quiet Form", 14990, 16990, 5, "womenswear.png"),
    ("Charcoal Drape Blouse", "charcoal-drape-blouse", "AUR-W-003", "Shirts", "Women", "Essential Forms", 5490, None, 19, "womenswear.png"),
    ("Atelier Wide Trouser", "atelier-wide-trouser", "AUR-W-004", "Trousers", "Women", "Essential Forms", 6290, 6990, 9, "womenswear.png"),
    ("Form Mini Bag", "form-mini-bag", "AUR-A-001", "Accessories", "Women", "Objects", 7990, None, 14, "womenswear.png"),
    ("Merino Studio Scarf", "merino-studio-scarf", "AUR-A-002", "Accessories", "Unisex", "Objects", 3490, 3990, 20, "womenswear.png"),
]


def seed_catalog():
    for index, data in enumerate(PRODUCTS):
        name, slug, sku, category, gender, collection, price, original, stock, image = data
        if not Product.query.filter_by(slug=slug).first():
            db.session.add(Product(
                name=name, slug=slug, sku=sku, category=category, gender=gender,
                collection=collection, price=price, original_price=original, stock=stock,
                image=f"images/{image}", short_description="A refined wardrobe essential with a confident, architectural silhouette.",
                description="Designed in the AUREN studio with balanced proportions, clean construction and considered details for everyday wear.",
                material="Premium blended fabric. Dry clean or gentle cold care as indicated. Store away from direct sunlight.",
                sizes="XS,S,M,L,XL" if gender == "Women" else "S,M,L,XL",
                colors="Black,Ivory,Beige,Charcoal", featured=index < 4,
                new_arrival=index in {0, 1, 3, 6, 7, 9}, best_seller=index in {0, 2, 6, 8}, active=True,
            ))
    if not Coupon.query.filter_by(code="AUREN10").first():
        db.session.add(Coupon(code="AUREN10", discount_type="percent", value=10, min_order=4000, max_discount=1500, usage_limit=200))
    defaults = {
        "announcement": "Complimentary delivery on orders over Rs. 5,000",
        "hero_title": "Wear Your Presence.",
        "hero_subtitle": "Contemporary tailoring, quiet confidence, and pieces designed to remain.",
        "free_delivery_threshold": "5000", "contact_email": "care@auren.pk",
        "contact_phone": "+92 300 0000000", "instagram": "https://instagram.com/auren",
    }
    for key, value in defaults.items():
        if not SiteSetting.query.filter_by(key=key).first():
            db.session.add(SiteSetting(key=key, value=value))
    db.session.commit()


def create_admin(email, password, name):
    if len(password) < 10:
        raise ValueError("Admin password must contain at least 10 characters.")
    admin = User.query.filter_by(email=email.lower()).first()
    if not admin:
        admin = User(name=name, email=email.lower(), is_admin=True)
        db.session.add(admin)
    admin.name, admin.is_admin, admin.active = name, True, True
    admin.set_password(password)
    db.session.commit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed AUREN sample data and optionally create an administrator.")
    parser.add_argument("--admin-email")
    parser.add_argument("--admin-password")
    parser.add_argument("--admin-name", default="AUREN Admin")
    args = parser.parse_args()
    app = create_app()
    with app.app_context():
        seed_catalog()
        if args.admin_email or args.admin_password:
            if not args.admin_email or not args.admin_password:
                parser.error("Both --admin-email and --admin-password are required together.")
            create_admin(args.admin_email, args.admin_password, args.admin_name)
            print("Catalogue seeded and administrator created.")
        else:
            print("Catalogue seeded. Add --admin-email and --admin-password to create an administrator.")

