import unittest
import uuid

from backend.app import app


class AdminAuthTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def test_login_rejects_invalid_credentials(self):
        response = self.client.post('/api/admin/login', json={
            'username': 'admin',
            'password': 'wrong-password'
        })
        self.assertEqual(response.status_code, 401)
        self.assertIn('error', response.get_json())

    def test_admin_session_can_access_summary(self):
        login = self.client.post('/api/admin/login', json={
            'username': 'admin',
            'password': 'admin123'
        })
        self.assertEqual(login.status_code, 200, login.get_data(as_text=True))

        me = self.client.get('/api/admin/me')
        self.assertEqual(me.status_code, 200)
        self.assertTrue(me.get_json()['logged_in'])

        response = self.client.get('/api/admin/dashboard/summary')
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIn('stats', payload)
        self.assertIn('recent_activity', payload)

    def test_session_cookie_survives_refresh_and_logout_clears_access(self):
        login = self.client.post('/api/admin/login', json={
            'username': 'admin',
            'password': 'admin123'
        })
        self.assertEqual(login.status_code, 200)
        set_cookie = login.headers.get('Set-Cookie', '')
        self.assertIn('HttpOnly', set_cookie)
        self.assertIn('Path=/', set_cookie)
        self.assertIn('SameSite=Lax', set_cookie)

        refreshed = self.client.get('/api/admin/me')
        self.assertEqual(refreshed.status_code, 200)
        self.assertTrue(refreshed.get_json()['logged_in'])

        logout = self.client.post('/api/admin/logout')
        self.assertEqual(logout.status_code, 200)
        after_logout = self.client.get('/api/admin/me')
        self.assertEqual(after_logout.status_code, 401)
        self.assertEqual(after_logout.get_json()['error'], 'Authentication required.')

    def test_registration_approval_denial_and_security_records(self):
        suffix = uuid.uuid4().hex[:8]
        pending_email = f'pending_{suffix}@example.com'
        denied_email = f'denied_{suffix}@example.com'
        direct_email = f'direct_{suffix}@example.com'
        password = 'Password123!'
        super_client = app.test_client()
        user_client = app.test_client()

        registration = user_client.post('/api/register', json={
            'name': 'Pending User',
            'email': pending_email,
            'role': 'ADMIN',
            'password': password,
            'confirm_password': password,
        })
        self.assertEqual(registration.status_code, 202)
        self.assertEqual(user_client.post('/api/admin/login', json={
            'username': pending_email,
            'password': password,
        }).status_code, 403)

        self.assertEqual(super_client.post('/api/admin/login', json={
            'username': 'admin',
            'password': 'admin123',
        }).status_code, 200)
        pending = super_client.get('/api/admin/pending-approvals').get_json()
        request_id = next(item['id'] for item in pending if item['email'] == pending_email)
        self.assertEqual(super_client.post(f'/api/admin/login-requests/{request_id}/approve').status_code, 200)
        self.assertEqual(user_client.post('/api/admin/login', json={
            'username': pending_email,
            'password': password,
        }).status_code, 200)
        self.assertEqual(user_client.post('/api/admin/logout').status_code, 200)

        denied_client = app.test_client()
        self.assertEqual(denied_client.post('/api/register', json={
            'name': 'Denied User',
            'email': denied_email,
            'role': 'DEVELOPER',
            'password': password,
            'confirm_password': password,
        }).status_code, 202)
        denied = super_client.get('/api/admin/pending-approvals').get_json()
        denied_id = next(item['id'] for item in denied if item['email'] == denied_email)
        self.assertEqual(super_client.post(f'/api/admin/login-requests/{denied_id}/deny').status_code, 200)
        self.assertEqual(denied_client.post('/api/admin/login', json={
            'username': denied_email,
            'password': password,
        }).status_code, 403)

        direct = super_client.post('/api/admin/users', json={
            'name': 'Direct User',
            'email': direct_email,
            'role': 'MAIN ADMIN',
            'password': password,
            'confirm_password': password,
        })
        self.assertEqual(direct.status_code, 201)
        direct_client = app.test_client()
        self.assertEqual(direct_client.post('/api/admin/login', json={
            'username': direct_email,
            'password': password,
        }).status_code, 200)
        self.assertEqual(direct_client.post(f'/api/admin/login-requests/{denied_id}/approve').status_code, 403)
        self.assertEqual(super_client.get('/api/admin/alerts').status_code, 200)
        activities = super_client.get('/api/admin/recent-activity').get_json()
        activity_names = {item['action'] for item in activities}
        self.assertIn('user_login', activity_names)
        self.assertIn('user_logout', activity_names)
        self.assertIn('account_approved', activity_names)
        self.assertIn('account_denied', activity_names)
        self.assertIn('user_created', activity_names)


if __name__ == '__main__':
    unittest.main()
