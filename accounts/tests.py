from django.contrib.auth.models import Group, User
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.roles import ADMIN, OPERATOR, get_role


def make_user(username, role, password='pass12345'):
    user = User.objects.create_user(username=username, password=password)
    user.groups.add(Group.objects.get_or_create(name=role)[0])
    return user


class AuthTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = make_user('admin1', ADMIN)

    def test_login_returns_token_and_role(self):
        r = self.client.post('/api/auth/login/', {
            'username': 'admin1', 'password': 'pass12345',
        }, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertIn('access', r.data)
        self.assertIn('refresh', r.data)
        self.assertEqual(r.data['user']['role'], ADMIN)

    def test_login_bad_credentials(self):
        r = self.client.post('/api/auth/login/', {
            'username': 'admin1', 'password': 'wrong',
        }, format='json')
        self.assertEqual(r.status_code, 401)

    def test_me_requires_auth(self):
        self.assertEqual(self.client.get('/api/auth/me/').status_code, 401)

    def test_me_returns_current_user(self):
        self.client.force_authenticate(self.admin)
        r = self.client.get('/api/auth/me/')
        self.assertEqual(r.data['username'], 'admin1')


class UserManagementTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = make_user('admin1', ADMIN)
        self.operator = make_user('op1', OPERATOR)

    def test_operator_cannot_list_users(self):
        self.client.force_authenticate(self.operator)
        self.assertEqual(self.client.get('/api/users/').status_code, 403)

    def test_admin_creates_operator(self):
        self.client.force_authenticate(self.admin)
        r = self.client.post('/api/users/', {
            'username': 'newop', 'email': 'op@x.com', 'password': 'secret123',
            'role': OPERATOR,
        }, format='json')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(get_role(User.objects.get(username='newop')), OPERATOR)

    def test_admin_deactivate_user(self):
        self.client.force_authenticate(self.admin)
        r = self.client.delete(f'/api/users/{self.operator.id}/')
        self.assertEqual(r.status_code, 204)
        self.operator.refresh_from_db()
        self.assertFalse(self.operator.is_active)

    def test_admin_cannot_deactivate_self(self):
        self.client.force_authenticate(self.admin)
        r = self.client.delete(f'/api/users/{self.admin.id}/')
        self.assertEqual(r.status_code, 400)


class ChangePasswordTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = make_user('op1', OPERATOR, password='oldpass12345')

    def test_requires_auth(self):
        r = self.client.post('/api/auth/change-password/', {}, format='json')
        self.assertEqual(r.status_code, 401)

    def test_change_password_success(self):
        self.client.force_authenticate(self.user)
        r = self.client.post('/api/auth/change-password/', {
            'current_password': 'oldpass12345', 'new_password': 'brandNew98765',
        }, format='json')
        self.assertEqual(r.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('brandNew98765'))

    def test_wrong_current_password_rejected(self):
        self.client.force_authenticate(self.user)
        r = self.client.post('/api/auth/change-password/', {
            'current_password': 'WRONG', 'new_password': 'brandNew98765',
        }, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('current_password', r.data)

    def test_weak_new_password_rejected(self):
        self.client.force_authenticate(self.user)
        r = self.client.post('/api/auth/change-password/', {
            'current_password': 'oldpass12345', 'new_password': '123',
        }, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('new_password', r.data)


class SiteConfigTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = make_user('admin1', ADMIN)
        self.operator = make_user('op1', OPERATOR)

    def test_config_is_public(self):
        r = self.client.get('/api/config/')
        self.assertEqual(r.status_code, 200)
        self.assertIn('app_name', r.data)

    def test_operator_cannot_update_config(self):
        self.client.force_authenticate(self.operator)
        r = self.client.patch('/api/config/', {'app_name': 'Hack'}, format='json')
        self.assertEqual(r.status_code, 403)

    def test_admin_updates_config(self):
        self.client.force_authenticate(self.admin)
        r = self.client.patch('/api/config/', {'app_name': 'AcmeVerify', 'accent_color': '#00aaff'}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['app_name'], 'AcmeVerify')


class AuditLogTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = make_user('admin1', ADMIN)
        self.operator = make_user('op1', OPERATOR)

    def test_action_is_logged_and_listed(self):
        self.client.force_authenticate(self.admin)
        self.client.post('/api/users/', {
            'username': 'newop', 'email': 'n@x.com', 'password': 'secret123', 'role': OPERATOR,
        }, format='json')
        r = self.client.get('/api/audit/')
        self.assertEqual(r.status_code, 200)
        actions = [row['action'] for row in r.data['results']]
        self.assertIn('user.create', actions)

    def test_operator_cannot_view_audit(self):
        self.client.force_authenticate(self.operator)
        self.assertEqual(self.client.get('/api/audit/').status_code, 403)


class LockoutTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        make_user('admin1', ADMIN, password='rightpass123')

    def test_lockout_after_failed_attempts(self):
        for _ in range(5):
            self.client.post('/api/auth/login/', {'username': 'admin1', 'password': 'wrong'}, format='json')
        # Even the correct password is now rejected with a lockout.
        r = self.client.post('/api/auth/login/', {'username': 'admin1', 'password': 'rightpass123'}, format='json')
        self.assertEqual(r.status_code, 403)
        self.assertIn('locked', r.data['detail'].lower())


class TwoFactorTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = make_user('admin1', ADMIN, password='rightpass123')

    def test_setup_and_enable_then_login_requires_otp(self):
        import pyotp
        self.client.force_authenticate(self.user)
        setup = self.client.post('/api/auth/2fa/setup/', {}, format='json')
        self.assertEqual(setup.status_code, 200)
        secret = setup.data['secret']
        code = pyotp.TOTP(secret).now()
        enable = self.client.post('/api/auth/2fa/enable/', {'code': code}, format='json')
        self.assertEqual(enable.status_code, 200)

        # Fresh client: password alone is not enough anymore.
        anon = APIClient()
        r = anon.post('/api/auth/login/', {'username': 'admin1', 'password': 'rightpass123'}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('otp', r.data)

        # With a valid OTP it succeeds.
        r2 = anon.post('/api/auth/login/', {
            'username': 'admin1', 'password': 'rightpass123', 'otp': pyotp.TOTP(secret).now(),
        }, format='json')
        self.assertEqual(r2.status_code, 200)
        self.assertIn('access', r2.data)
