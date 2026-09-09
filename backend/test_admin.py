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

        response = self.client.get('/api/admin/dashboard/summary')
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIn('stats', payload)
        self.assertIn('recent_activity', payload)


if __name__ == '__main__':
    unittest.main()
