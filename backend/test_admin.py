import unittest

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


if __name__ == '__main__':
    unittest.main()
