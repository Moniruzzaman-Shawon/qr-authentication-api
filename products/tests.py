from django.contrib.auth.models import Group, User
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.roles import ADMIN, OPERATOR
from .models import CatalogProduct, Product


def make_user(username, role, password='pass12345'):
    user = User.objects.create_user(username=username, password=password)
    user.groups.add(Group.objects.get_or_create(name=role)[0])
    return user


class ProductPermissionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = make_user('admin1', ADMIN)
        self.operator = make_user('op1', OPERATOR)
        self.product = Product.objects.create(
            product_name='Oil', batch_number='B-1', manufactured_date='2026-01-01',
        )

    def test_list_requires_auth(self):
        self.assertEqual(self.client.get('/api/products/').status_code, 401)

    def test_operator_can_list(self):
        self.client.force_authenticate(self.operator)
        self.assertEqual(self.client.get('/api/products/').status_code, 200)

    def test_operator_cannot_create(self):
        self.client.force_authenticate(self.operator)
        r = self.client.post('/api/products/', {
            'product_name': 'X', 'batch_number': 'B-2', 'manufactured_date': '2026-01-01',
        }, format='json')
        self.assertEqual(r.status_code, 403)

    def test_admin_can_create_and_gets_printed_status(self):
        self.client.force_authenticate(self.admin)
        r = self.client.post('/api/products/', {
            'product_name': 'X', 'batch_number': 'B-2', 'manufactured_date': '2026-01-01',
        }, format='json')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data['status'], Product.STATUS_PRINTED)

    def test_operator_cannot_delete(self):
        self.client.force_authenticate(self.operator)
        r = self.client.delete(f'/api/products/{self.product.id}/')
        self.assertEqual(r.status_code, 403)

    def test_admin_can_delete(self):
        self.client.force_authenticate(self.admin)
        r = self.client.delete(f'/api/products/{self.product.id}/')
        self.assertEqual(r.status_code, 204)


class ActivationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.operator = make_user('op1', OPERATOR)
        self.product = Product.objects.create(
            product_name='Oil', batch_number='B-1', manufactured_date='2026-01-01',
        )

    def test_operator_can_activate(self):
        self.client.force_authenticate(self.operator)
        r = self.client.post(f'/api/products/{self.product.id}/activate/', {}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['status'], Product.STATUS_ACTIVE)
        self.product.refresh_from_db()
        self.assertEqual(self.product.activated_by, self.operator)
        self.assertIsNotNone(self.product.activated_at)

    def test_activation_requires_auth(self):
        r = self.client.post(f'/api/products/{self.product.id}/activate/', {}, format='json')
        self.assertEqual(r.status_code, 401)

    def test_cannot_activate_twice(self):
        self.client.force_authenticate(self.operator)
        self.client.post(f'/api/products/{self.product.id}/activate/', {}, format='json')
        r = self.client.post(f'/api/products/{self.product.id}/activate/', {}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_bulk_activate(self):
        p2 = Product.objects.create(
            product_name='Oil2', batch_number='B-2', manufactured_date='2026-01-01',
        )
        self.client.force_authenticate(self.operator)
        r = self.client.post('/api/products/bulk-activate/', {
            'ids': [str(self.product.id), str(p2.id)],
        }, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['activated_count'], 2)


class CatalogTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = make_user('admin1', ADMIN)
        self.operator = make_user('op1', OPERATOR)

    def test_admin_creates_catalog_product(self):
        self.client.force_authenticate(self.admin)
        r = self.client.post('/api/catalog/', {
            'name': 'Engine Oil 5W-30', 'brand': 'RT',
        }, format='json')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data['name'], 'Engine Oil 5W-30')

    def test_operator_cannot_create_catalog(self):
        self.client.force_authenticate(self.operator)
        r = self.client.post('/api/catalog/', {'name': 'X'}, format='json')
        self.assertEqual(r.status_code, 403)

    def test_operator_can_list_catalog(self):
        CatalogProduct.objects.create(name='Brake Fluid DOT4')
        self.client.force_authenticate(self.operator)
        r = self.client.get('/api/catalog/')
        self.assertEqual(r.status_code, 200)

    def test_bulk_create_from_catalog_copies_name(self):
        cat = CatalogProduct.objects.create(name='Gear Oil 80W-90', brand='RT')
        self.client.force_authenticate(self.admin)
        r = self.client.post('/api/products/bulk-create/', {
            'catalog': cat.id, 'batch_prefix': 'B', 'manufactured_date': '2026-01-01',
            'quantity': 3,
        }, format='json')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data['count'], 3)
        self.assertEqual(r.data['products'][0]['product_name'], 'Gear Oil 80W-90')
        self.assertEqual(r.data['products'][0]['catalog'], cat.id)

    def test_bulk_create_without_name_or_catalog_fails(self):
        self.client.force_authenticate(self.admin)
        r = self.client.post('/api/products/bulk-create/', {
            'batch_prefix': 'B', 'manufactured_date': '2026-01-01', 'quantity': 2,
        }, format='json')
        self.assertEqual(r.status_code, 400)

    def test_single_create_from_catalog(self):
        cat = CatalogProduct.objects.create(name='Coolant', brand='RT')
        self.client.force_authenticate(self.admin)
        r = self.client.post('/api/products/', {
            'catalog': cat.id, 'batch_number': 'B-1', 'manufactured_date': '2026-01-01',
        }, format='json')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data['product_name'], 'Coolant')

    def test_deleting_catalog_keeps_units(self):
        cat = CatalogProduct.objects.create(name='Wax', brand='RT')
        unit = Product.objects.create(
            catalog=cat, product_name='Wax', batch_number='B-1',
            manufactured_date='2026-01-01',
        )
        self.client.force_authenticate(self.admin)
        r = self.client.delete(f'/api/catalog/{cat.id}/')
        self.assertEqual(r.status_code, 204)
        unit.refresh_from_db()
        self.assertIsNone(unit.catalog)
        self.assertEqual(unit.product_name, 'Wax')  # name preserved
