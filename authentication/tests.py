from django.contrib.auth.models import Group, User
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.roles import ADMIN, OPERATOR
from products.models import Product
from products.qr import make_signature
from .models import ScanRecord


def make_user(username, role, password='pass12345'):
    user = User.objects.create_user(username=username, password=password)
    user.groups.add(Group.objects.get_or_create(name=role)[0])
    return user


class VerifyFlowTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = make_user('admin1', ADMIN)
        self.product = Product.objects.create(
            product_name='Mustard Oil',
            batch_number='B-0001',
            manufactured_date='2026-01-01',
        )
        self.sig = make_signature(self.product.id)

    def _verify(self, email='cust@example.com', name='Cust', sig=None):
        sig = self.sig if sig is None else sig
        return self.client.post(
            f'/api/verify/{self.product.id}/?sig={sig}',
            {'email': email, 'name': name}, format='json',
        )

    def test_printed_product_is_not_activated(self):
        r = self._verify()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['status'], 'not_activated')
        self.product.refresh_from_db()
        self.assertEqual(self.product.status, Product.STATUS_PRINTED)

    def test_activated_product_verifies_genuine_then_suspicious(self):
        self.product.status = Product.STATUS_ACTIVE
        self.product.save()

        r1 = self._verify(email='real@example.com')
        self.assertEqual(r1.data['status'], 'genuine')
        self.product.refresh_from_db()
        self.assertEqual(self.product.status, Product.STATUS_VERIFIED)

        r2 = self._verify(email='faker@example.com')
        self.assertEqual(r2.data['status'], 'suspicious')
        self.assertEqual(r2.data['first_scanned_by'], 'r***@example.com')
        self.product.refresh_from_db()
        self.assertEqual(self.product.status, Product.STATUS_FLAGGED)

    def test_only_one_genuine_scan_exists(self):
        self.product.status = Product.STATUS_ACTIVE
        self.product.save()
        self._verify()
        self._verify(email='b@example.com')
        self._verify(email='c@example.com')
        genuine = ScanRecord.objects.filter(product=self.product, is_first_scan=True)
        self.assertEqual(genuine.count(), 1)

    def test_disabled_product_is_suspicious(self):
        self.product.status = Product.STATUS_ACTIVE
        self.product.is_active = False
        self.product.save()
        r = self._verify()
        self.assertEqual(r.data['status'], 'suspicious')

    def test_invalid_signature_rejected(self):
        self.product.status = Product.STATUS_ACTIVE
        self.product.save()
        r = self._verify(sig='deadbeef')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(ScanRecord.objects.count(), 0)

    def test_missing_signature_rejected(self):
        r = self.client.post(
            f'/api/verify/{self.product.id}/',
            {'email': 'a@b.com', 'name': 'x'}, format='json',
        )
        self.assertEqual(r.status_code, 400)

    def test_unknown_product_returns_404(self):
        import uuid
        pid = uuid.uuid4()
        r = self.client.post(
            f'/api/verify/{pid}/?sig={make_signature(pid)}',
            {'email': 'a@b.com', 'name': 'x'}, format='json',
        )
        self.assertEqual(r.status_code, 404)

    def test_check_does_not_record_scan(self):
        self.product.status = Product.STATUS_ACTIVE
        self.product.save()
        r = self.client.get(f'/api/check/{self.product.id}/?sig={self.sig}')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data['scan_status']['is_activated'])
        self.assertEqual(ScanRecord.objects.count(), 0)


class ReadEndpointAuthTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_scans_require_auth(self):
        self.assertEqual(self.client.get('/api/scans/').status_code, 401)

    def test_stats_require_auth(self):
        self.assertEqual(self.client.get('/api/stats/').status_code, 401)

    def test_operator_can_read_stats(self):
        make_user('op1', OPERATOR)
        self.client.force_authenticate(user=User.objects.get(username='op1'))
        self.assertEqual(self.client.get('/api/stats/').status_code, 200)
