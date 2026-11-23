"""Canonical selection, protected writes, and nondestructive legacy migration."""

from fastapi.testclient import TestClient
from sqlalchemy import event, select

from backend.database import User, Workout, XPTransaction, LoginSession
from backend.departments import DEPARTMENTS, normalize_existing_departments
from backend.main import create_app
from backend.test_helpers import ApiCase


class DepartmentTests(ApiCase):
    def test_public_catalog_matches_all_requested_codes_and_labels(self):
        response = self.client.get('/api/departments')
        self.assertEqual(response.status_code, 200)
        options = response.json()
        self.assertEqual(len(options), 30)
        self.assertEqual(len({item['value'] for item in options}), 30)
        self.assertEqual([item['value'] for item in options],
                         ['EECS', 'CS', 'EE', 'IBP', 'IPEECS', 'IMBA', 'MBA', 'EMBA',
                          'PME', 'MSE', 'CHE', 'IEEM', 'ESS', 'BMES', 'MATH', 'PHYS',
                          'CHEM', 'STAT', 'LS', 'MS', 'ECON', 'QF', 'TM', 'FLL', 'CL',
                          'HSS', 'ECE', 'EDU', 'AD', 'MUSIC'])
        self.assertEqual(options, [{'value': code, 'label': f'{code} — {name}'}
                                   for code, name in DEPARTMENTS])

    def test_registration_stores_code_and_survives_login(self):
        response = self.client.post('/api/auth/register', json={
            'username': 'department_student', 'password': 'password123', 'department': 'CS'})
        self.assertEqual(response.status_code, 201)
        self.csrf = response.json()['csrf_token']
        self.assertEqual(response.json()['department'], 'CS')
        self.assertEqual(self.client.get('/api/auth/me').json()['department'], 'CS')
        self.post('/api/auth/logout')
        login = self.client.post('/api/auth/login', json={
            'username': 'department_student', 'password': 'password123'})
        self.assertEqual(login.json()['department'], 'CS')

    def test_every_code_updates_and_clear_remains_optional(self):
        account = self.register()
        for code, _ in DEPARTMENTS:
            result = self.update(code)
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json()['department'], code)
            with self.app.state.session_factory() as db:
                self.assertEqual(db.get(User, account['id']).department, code)
        for empty in (None, '', '   '):
            self.assertIsNone(self.update(empty).json()['department'])
            self.assertIsNone(self.client.get('/api/auth/me').json()['department'])

    def update(self, value):
        return self.client.patch('/api/profile', json={'department': value},
                                 headers={'X-CSRF-Token': self.csrf})

    def test_unknown_values_rejected_without_creating_user_or_overwriting_profile(self):
        invalid = ['not-a-department', 'Computer Science', 'cs', 'CHEMISTRY', 12, [], 'X' * 101]
        for value in invalid:
            response = self.client.post('/api/auth/register', json={
                'username': 'invalid_department', 'password': 'password123', 'department': value})
            self.assertEqual(response.status_code, 422)
        with self.app.state.session_factory() as db:
            self.assertIsNone(db.scalar(select(User)))
        self.register()
        self.update('CHE')
        for value in invalid:
            self.assertEqual(self.update(value).status_code, 422)
            self.assertEqual(self.client.get('/api/auth/me').json()['department'], 'CHE')

    def test_auth_csrf_and_ownership_still_apply(self):
        self.assertEqual(self.client.patch('/api/profile', json={'department': 'CS'}).status_code, 401)
        account = self.register()
        self.assertEqual(self.client.patch('/api/profile', json={'department': 'CS'}).status_code, 403)
        with TestClient(self.app) as other:
            result = other.post('/api/auth/register', json={
                'username': 'another_student', 'password': 'password123', 'department': 'EE'})
            self.assertEqual(result.status_code, 201)
            other.patch('/api/profile', json={'department': 'MATH'},
                        headers={'X-CSRF-Token': result.json()['csrf_token']})
        with self.app.state.session_factory() as db:
            self.assertIsNone(db.get(User, account['id']).department)

    def test_startup_conversion_preserves_unknowns_workouts_credentials_and_sessions(self):
        account = self.register()
        session_id = self.start()
        with self.websocket(session_id) as socket:
            self.rep(socket)
            self.post(f'/api/workouts/{session_id}/finish')
        factory = self.app.state.session_factory
        with factory() as db:
            user = db.get(User, account['id'])
            user.department = '  computer   science  '
            password_hash = user.password_hash
            login_hash = db.scalar(select(LoginSession)).token_hash
            db.add_all([User(username='legacy_unknown', password_hash='unchanged', department='My old program'),
                        User(username='legacy_chem', password_hash='unchanged', department='chem'),
                        User(username='legacy_blank', password_hash='unchanged', department='  ')])
            db.commit()
        # Enter a new app lifespan against the same DB: the real deployment path.
        url = f'sqlite:///{self.directory.name}/test.db'
        for _ in range(2):
            with TestClient(create_app(url)) as restarted:
                restarted.cookies.update(self.client.cookies)
                self.assertEqual(restarted.get('/api/auth/me').json()['department'], 'CS')
                self.assertEqual(restarted.get('/api/workouts').json()[0]['rep_count'], 1)
        with factory() as db:
            users = {user.username: user for user in db.scalars(select(User))}
            self.assertEqual(users['legacy_unknown'].department, 'My old program')
            self.assertEqual(users['legacy_chem'].department, 'CHEM')
            self.assertIsNone(users['legacy_blank'].department)
            self.assertEqual(users['student_one'].password_hash, password_hash)
            self.assertEqual(db.scalar(select(LoginSession)).token_hash, login_hash)
            self.assertEqual(db.scalar(select(Workout)).rep_count, 1)
            self.assertEqual(db.scalar(select(XPTransaction)).amount, 10)
        self.assertEqual(normalize_existing_departments(factory), 0)

    def test_all_known_legacy_labels_names_and_codes_normalize_without_fuzzy_guessing(self):
        self.register()
        factory = self.app.state.session_factory
        expected = {}
        with factory() as db:
            for index, (code, name) in enumerate(DEPARTMENTS):
                for kind, value in enumerate((code.lower(), name, f'{code} — {name}')):
                    username = f'legacy_{index}_{kind}'
                    expected[username] = code
                    db.add(User(username=username, password_hash='unchanged', department=f' {value} '))
            db.commit()
        self.assertEqual(normalize_existing_departments(factory), 90)
        with factory() as db:
            for user in db.scalars(select(User)):
                if user.username in expected:
                    self.assertEqual(user.department, expected[user.username])
        self.assertEqual(normalize_existing_departments(factory), 0)

    def test_failed_conversion_rolls_back_every_department(self):
        self.register()
        factory = self.app.state.session_factory
        with factory() as db:
            db.scalar(select(User)).department = 'Computer Science'
            db.add(User(username='rollback_second', password_hash='unchanged', department='Electrical Engineering'))
            db.commit()
        def fail_flush(*args):
            raise RuntimeError('simulated write failure')
        # Fail after UPDATEs have been issued, proving the transaction undoes them.
        event.listen(factory.class_, 'after_flush_postexec', fail_flush)
        try:
            with self.assertRaises(RuntimeError):
                normalize_existing_departments(factory)
        finally:
            event.remove(factory.class_, 'after_flush_postexec', fail_flush)
        with factory() as db:
            values = {user.username: user.department for user in db.scalars(select(User))}
            self.assertEqual(values, {'student_one': 'Computer Science', 'rollback_second': 'Electrical Engineering'})
