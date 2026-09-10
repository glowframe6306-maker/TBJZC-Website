import unittest
import io
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

    def test_admin_session_can_access_dashboard_data(self):
        login = self.client.post('/api/admin/login', json={
            'username': 'admin',
            'password': 'admin123'
        })
        self.assertEqual(login.status_code, 200, login.get_data(as_text=True))

        me = self.client.get('/api/admin/me')
        self.assertEqual(me.status_code, 200)
        self.assertTrue(me.get_json()['logged_in'])

        response = self.client.get('/api/admin/recent-activity')
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.get_json(), list)

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
            'username': f'pending_{suffix}',
            'email': pending_email,
            'role': 'ADMIN',
            'password': password,
            'confirm_password': password,
        })
        self.assertEqual(registration.status_code, 202)
        self.assertEqual(user_client.post('/api/admin/login', json={
            'username': f'pending_{suffix}',
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
            'username': f'pending_{suffix}',
            'password': password,
        }).status_code, 200)
        self.assertEqual(user_client.post('/api/admin/logout').status_code, 200)

        denied_client = app.test_client()
        self.assertEqual(denied_client.post('/api/register', json={
            'username': f'denied_{suffix}',
            'email': denied_email,
            'role': 'DEVELOPER',
            'password': password,
            'confirm_password': password,
        }).status_code, 202)
        denied = super_client.get('/api/admin/pending-approvals').get_json()
        denied_id = next(item['id'] for item in denied if item['email'] == denied_email)
        self.assertEqual(super_client.post(f'/api/admin/login-requests/{denied_id}/deny').status_code, 200)
        self.assertEqual(denied_client.post('/api/admin/login', json={
            'username': f'denied_{suffix}',
            'password': password,
        }).status_code, 403)

        direct = super_client.post('/api/admin/users', json={
            'username': f'direct_{suffix}',
            'email': direct_email,
            'role': 'MAIN ADMIN',
            'password': password,
            'confirm_password': password,
        })
        self.assertEqual(direct.status_code, 201)
        direct_client = app.test_client()
        self.assertEqual(direct_client.post('/api/admin/login', json={
            'username': f'direct_{suffix}',
            'password': password,
        }).status_code, 200)
        unauthorized_create = direct_client.post('/api/admin/users', json={
            'username': f'blocked_{suffix}',
            'email': f'blocked_{suffix}@example.com',
            'role': 'ADMIN',
            'password': password,
            'confirm_password': password,
        })
        self.assertEqual(unauthorized_create.status_code, 403)
        self.assertIsNone(next((item for item in super_client.get('/api/admin/users').get_json() if item['username'] == f'blocked_{suffix}'), None))
        self.assertEqual(direct_client.post(f'/api/admin/login-requests/{denied_id}/approve').status_code, 403)
        self.assertEqual(super_client.get('/api/admin/alerts').status_code, 200)
        activities = super_client.get('/api/admin/recent-activity').get_json()
        activity_names = {item['action'] for item in activities}
        self.assertIn('user_login', activity_names)
        self.assertIn('user_logout', activity_names)
        self.assertIn('account_approved', activity_names)
        self.assertIn('account_denied', activity_names)
        self.assertIn('user_created', activity_names)

    def test_posts_use_validated_sections_and_public_filters(self):
        sections = self.client.get('/api/post-sections')
        self.assertEqual(sections.status_code, 200)
        values = {item['value'] for item in sections.get_json()}
        self.assertIn('sports', values)
        self.assertIn('achievements', values)
        self.assertIn('latest-news', values)
        self.assertNotIn('about-us', values)
        self.assertNotIn('academic-staff', values)
        self.assertNotIn('visions-and-missions', values)
        self.assertNotIn('examination-results', values)
        self.assertNotIn('feedback-and-suggestions', values)

        login = self.client.post('/api/admin/login', json={
            'username': 'admin',
            'password': 'admin123',
        })
        self.assertEqual(login.status_code, 200)
        suffix = uuid.uuid4().hex[:8]
        sports_post = self.client.post('/api/admin/posts', data={
            'section': 'sports',
            'title': f'Sports Test {suffix}',
            'description': 'Sports description',
            'photos': (io.BytesIO(b'not-a-real-image'), 'test.txt'),
        }, content_type='multipart/form-data')
        self.assertEqual(sports_post.status_code, 400)

        sports_post = self.client.post('/api/admin/posts', json={
            'section': 'sports',
            'title': f'Sports Test {suffix}',
            'description': 'Sports description',
        })
        self.assertEqual(sports_post.status_code, 201)
        sports_payload = sports_post.get_json()
        self.assertEqual(sports_payload['section'], 'sports')
        valid_png = bytes.fromhex(
            '89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489'
            '0000000d49444154789c6360606000000004000100fefb3d0000000049454e44ae426082'
        )
        image_post = self.client.post('/api/admin/posts', data={
            'section': 'sports',
            'title': f'Image Test {suffix}',
            'description': 'Image description',
            'photos': (io.BytesIO(valid_png), 'image-test.png'),
        }, content_type='multipart/form-data')
        self.assertEqual(image_post.status_code, 201)
        image_url = image_post.get_json()['images'][0]
        self.assertEqual(self.client.get(image_url).status_code, 200)
        achievement_post = self.client.post('/api/admin/posts', json={
            'section': 'achievements',
            'title': f'Achievement Test {suffix}',
            'description': 'Achievement description',
        })
        self.assertEqual(achievement_post.status_code, 201)
        excluded = self.client.post('/api/admin/posts', json={
            'section': 'about-us',
            'title': 'Invalid destination',
            'description': 'Should be rejected',
        })
        self.assertEqual(excluded.status_code, 400)

        sports = self.client.get('/api/posts?section=sports').get_json()
        achievements = self.client.get('/api/posts?section=achievements').get_json()
        sports_titles = {post['title'] for post in sports}
        achievement_titles = {post['title'] for post in achievements}
        self.assertIn(f'Sports Test {suffix}', sports_titles)
        self.assertNotIn(f'Sports Test {suffix}', achievement_titles)
        self.assertIn(f'Achievement Test {suffix}', achievement_titles)
        self.assertNotIn(f'Achievement Test {suffix}', sports_titles)

        stored = self.client.get('/api/admin/posts').get_json()
        stored_sports = next(post for post in stored if post['id'] == sports_payload['id'])
        self.assertEqual(stored_sports['section'], 'sports')
        self.assertEqual(stored_sports['author'], 'admin')

    def test_post_create_delete_survives_refresh_and_relogin(self):
        login = self.client.post('/api/admin/login', json={
            'username': 'admin',
            'password': 'admin123',
        })
        self.assertEqual(login.status_code, 200)
        suffix = uuid.uuid4().hex[:8]
        valid_png = bytes.fromhex(
            '89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489'
            '0000000d49444154789c6360606000000004000100fefb3d0000000049454e44ae426082'
        )
        post_a = self.client.post('/api/admin/posts', data={
            'section': 'sports',
            'title': f'Permanent A {suffix}',
            'description': 'Post A',
            'photos': (io.BytesIO(valid_png), 'post-a.png'),
        }, content_type='multipart/form-data')
        post_b = self.client.post('/api/admin/posts', json={
            'section': 'sports',
            'title': f'Permanent B {suffix}',
            'description': 'Post B',
        })
        self.assertEqual(post_a.status_code, 201)
        self.assertEqual(post_b.status_code, 201)
        post_a_id = post_a.get_json()['id']
        post_b_id = post_b.get_json()['id']
        post_a_image = post_a.get_json()['images'][0]
        self.assertEqual(self.client.get(post_a_image).status_code, 200)

        refreshed = {post['id'] for post in self.client.get('/api/admin/posts').get_json()}
        self.assertIn(post_a_id, refreshed)
        self.assertIn(post_b_id, refreshed)

        deleted = self.client.delete(f'/api/admin/posts/{post_a_id}')
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(self.client.get(post_a_image).status_code, 404)
        after_delete = {post['id'] for post in self.client.get('/api/admin/posts').get_json()}
        self.assertNotIn(post_a_id, after_delete)
        self.assertIn(post_b_id, after_delete)

        self.assertEqual(self.client.post('/api/admin/logout').status_code, 200)
        self.assertEqual(self.client.post('/api/admin/login', json={
            'username': 'admin',
            'password': 'admin123',
        }).status_code, 200)
        after_relogin = {post['id'] for post in self.client.get('/api/admin/posts').get_json()}
        self.assertNotIn(post_a_id, after_relogin)
        self.assertIn(post_b_id, after_relogin)


if __name__ == '__main__':
    unittest.main()
