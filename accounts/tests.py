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
