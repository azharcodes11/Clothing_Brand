import tempfile
import unittest
from pathlib import Path

from app import create_app
from app.extensions import db
from app.models import Product, User
from seed import seed_catalog


class TestConfig:
    TESTING = True
    WTF_CSRF_ENABLED = False
    SECRET_KEY = "test"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False


class AurenTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.client = self.app.test_client()
        with self.app.app_context():
            db.create_all()
            seed_catalog()
            admin = User(name="Admin", email="admin@test.local", is_admin=True)
            admin.set_password("secure-test-pass")
            customer = User(name="Client", email="client@test.local")
            customer.set_password("secure-test-pass")
            db.session.add_all([admin, customer])
            db.session.commit()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def test_public_pages_and_products(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        response = self.client.get("/shop?gender=Men&sort=price_low")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Signature Overshirt", response.data)

    def test_guest_cart_and_checkout(self):
        with self.app.app_context():
            product = Product.query.first()
            product_id, slug = product.id, product.slug
        response = self.client.post(f"/cart/add/{product_id}", data={"size": "S", "color": "Black", "quantity": 2})
        self.assertEqual(response.status_code, 302)
        self.assertIn(b"Signature Overshirt", self.client.get("/cart").data)
        checkout = self.client.post("/checkout", data={"name":"Test Client","email":"test@example.com","phone":"03001234567","address":"Street 1","city":"Hyderabad","province":"Sindh","postal_code":"71000","delivery_method":"standard","payment_method":"cod","coupon":"AUREN10"}, follow_redirects=True)
        self.assertEqual(checkout.status_code, 200)
        self.assertIn(b"ORDER RECEIVED", checkout.data)

    def test_customer_and_admin_authorization(self):
        self.client.post("/login", data={"email":"client@test.local","password":"secure-test-pass"})
        self.assertEqual(self.client.get("/profile").status_code, 200)
        self.assertEqual(self.client.get("/admin/").status_code, 403)
        self.client.post("/logout")
        self.client.post("/admin/login", data={"email":"admin@test.local","password":"secure-test-pass"})
        self.assertEqual(self.client.get("/admin/").status_code, 200)


if __name__ == "__main__":
    unittest.main()
