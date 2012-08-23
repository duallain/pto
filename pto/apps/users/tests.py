# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import re
from urlparse import urlparse
import datetime
from django.core.urlresolvers import reverse
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth import REDIRECT_FIELD_NAME
from nose.tools import eq_, ok_
from test_utils import TestCase
from mock import Mock

import ldap
from pto.apps.users.auth.backends import MozillaLDAPBackend
from pto.apps.users.utils.ldap_mock import MockLDAP
from pto.apps.users.models import UserProfile
from pto.apps.users.utils import ldap_lookup

RaiseInvalidCredentials = object()


class LDAPLookupTests(TestCase):

    def setUp(self):
        super(LDAPLookupTests, self).setUp()
        ldap.open = Mock('ldap.open')
        ldap.open.mock_returns = Mock('ldap_connection')
        ldap.set_option = Mock(return_value=None)
        from django.core.cache import cache
        assert cache.__class__.__name__ == 'LocMemCache', cache.__class__.__name__

    def tearDown(self):
        super(LDAPLookupTests, self).tearDown()
        from django.core.cache import cache
        cache.clear()

    def test_fetch_user_details(self):
        func = ldap_lookup.fetch_user_details
        fake_user = [
          ('mail=mortal@mozilla.com,o=com,dc=mozilla',
           {'cn': ['Peter Bengtsson'],
            'givenName': ['Pet\xc3\xa3r'],  # utf-8 encoded
            'mail': ['test@example.com'],
            'sn': ['Bengtss\xc2\xa2n'],
            'uid': ['pbengtsson']
            })
        ]

        _key = 'mail=mortal@mozilla.com'
        _key = ldap_lookup.account_wrap_search_filter(_key)
        ldap.initialize = Mock(return_value=MockLDAP({
          _key: fake_user,
          }
        ))

        details = func('xxx')
        ok_(not details)

        details = func('mortal@mozilla.com')
        assert details

        eq_(details['givenName'], u'Pet\xe3r')

        different_fake_user = [
          ('mail=mortal,o=com,dc=mozilla',
           {'cn': ['Peter Bengtsson'],
            'givenName': ['Different'],  # utf-8 encoded
            'mail': ['test@example.com'],
            'sn': ['Bengtss\xc2\xa2n'],
            'uid': ['pbengtsson']
            })
        ]

        ldap.initialize = Mock(return_value=MockLDAP({
          _key: different_fake_user,
          }
        ))

        details = func('mortal@mozilla.com')
        eq_(details['givenName'], u'Pet\xe3r')

        details = func('mortal@mozilla.com', force_refresh=True)
        eq_(details['givenName'], u'Different')

    def test_search_users_uid_search(self):
        func = ldap_lookup.search_users
        fake_user = [
          ('mail=mortal@mozilla.com,o=com,dc=mozilla',
           {'cn': ['Peter Bengtsson'],
            'givenName': ['Pet\xc3\xa3r'],  # utf-8 encoded
            'mail': ['test@example.com'],
            'sn': ['Bengtss\xc2\xa2n'],
            'uid': ['pbengtsson']
            })
        ]

        key = 'mail=mortal@mozilla.com'
        _wrapper = ldap_lookup.account_wrap_search_filter
        ldap.initialize = Mock(return_value=MockLDAP({
          _wrapper(key): fake_user,
          }
        ))

        # search by uid
        result = func(':pbengtsson', 1)
        ok_(not result)

        ldap.initialize = Mock(return_value=MockLDAP({
          _wrapper(key): fake_user,
          _wrapper('uid=pbengtsson'): fake_user,
          }
        ))

        result = func(':pbengtsson', 1)
        ok_(result)
        eq_(result[0]['uid'], 'pbengtsson')

        ldap.initialize = Mock(return_value=MockLDAP({
          _wrapper(key): fake_user,
          _wrapper('uid=pbeng*'): fake_user,
          }
        ))

        result = func(':pbeng', 1, autocomplete=True)
        ok_(result)
        eq_(result[0]['uid'], 'pbengtsson')

    def test_search_users_canonical_search(self):
        func = ldap_lookup.search_users
        fake_user = [
          ('mail=mortal@mozilla.com,o=com,dc=mozilla',
           {'cn': ['Peter Bengtsson'],
            'givenName': ['Pet\xc3\xa3r'],  # utf-8 encoded
            'mail': ['test@example.com'],
            'sn': ['Bengtss\xc2\xa2n'],
            'uid': ['pbengtsson']
            })
        ]

        key = 'mail=mortal@mozilla.com'
        _wrapper = ldap_lookup.account_wrap_search_filter
        ldap.initialize = Mock(return_value=MockLDAP({
          _wrapper(key): fake_user,
          }
        ))

        # search by uid
        result = func('Peter bengtsson', 1)
        ok_(not result)

        ldap.initialize = Mock(return_value=MockLDAP({
          _wrapper(key): fake_user,
          _wrapper('cn=*PETER BENGTSSON*'): fake_user,
          }
        ))

        result = func('PETER BENGTSSON', 1)
        ok_(result)
        eq_(result[0]['cn'], 'Peter Bengtsson')

        ldap.initialize = Mock(return_value=MockLDAP({
          _wrapper(key): fake_user,
          _wrapper('(|(mail=PETER BENGT*)(givenName=PETER BENGT*)(sn=PETER '
                   'BENGT*)(cn=PETER BENGT*))'): fake_user,
          }
        ))

        result = func('PETER BENGT', 1, autocomplete=True)
        ok_(result)
        eq_(result[0]['cn'], 'Peter Bengtsson')

    def test_fetch_user_details_lists_expanded(self):
        func = ldap_lookup.fetch_user_details
        fake_user = [
          ('mail=mortal@mozilla.com,o=com,dc=mozilla',
           {'cn': ['Peter Bengtsson'],
            'givenName': ['Pet\xc3\xa3r', 'Two'],  # utf-8 encoded
            'mail': ['test@example.com'],
            'sn': [],
            'uid': ['pbengtsson']
            })
        ]

        key = 'mail=mortal@mozilla.com'
        _wrapper = ldap_lookup.account_wrap_search_filter
        ldap.initialize = Mock(return_value=MockLDAP({
          _wrapper(key): fake_user,
          }
        ))

        # search by uid
        result = func('mortal@mozilla.com')
        assert result
        eq_(result['givenName'], [u'Pet\xe3r', u'Two'])
        ok_(isinstance(result['givenName'][0], unicode))
        ok_(isinstance(result['givenName'][1], unicode))
        eq_(result['sn'], u'')

    def test_search_users_invalid_email(self):
        func = ldap_lookup.search_users
        fake_user = [
          ('mail=mortal@mozilla.com,o=com,dc=mozilla',
           {'cn': ['Peter Bengtsson'],
            'givenName': ['Pet\xc3\xa3r'],  # utf-8 encoded
            'mail': ['test@example.com'],
            'sn': ['Bengtss\xc2\xa2n'],
            'uid': ['pbengtsson']
            })
        ]

        key = 'mail=mortal@mozilla.com'
        _wrapper = ldap_lookup.account_wrap_search_filter
        ldap.initialize = Mock(return_value=MockLDAP({
          _wrapper(key): fake_user,
          }
        ))
        result = func('mortal@m@..ozilla.com', 10)
        ok_(not result)


class UsersTests(TestCase):

    def setUp(self):
        super(UsersTests, self).setUp()
        ldap.open = Mock('ldap.open')
        ldap.open.mock_returns = Mock('ldap_connection')
        ldap.set_option = Mock(return_value=None)

    def test_login_with_local_django_user(self):
        ldap.initialize = Mock(return_value=MockLDAP({
          '(mail=mortal@mozilla.com)': 'anything',
          },
          credentials={
            'mail=mortal,o=com,dc=mozilla': 'secret',
          }))

        url = reverse('users.login')
        response = self.client.get(url)
        eq_(response.status_code, 200)

        mortal = User.objects.create(
          username='mortal',
          first_name='Mortal',
          last_name='Joe'
        )
        mortal.set_password('secret')
        mortal.save()

        response = self.client.post(url, {'username': 'mortal',
                                          'password': 'wrong'})
        eq_(response.status_code, 200)
        ok_('errorlist' in response.content)

        response = self.client.post(url, {'username': 'mortal',
                                          'password': 'secret'})
        eq_(response.status_code, 302)
        path = urlparse(response['location']).path
        eq_(path, settings.LOGIN_REDIRECT_URL)

        response = self.client.get('/')
        eq_(response.status_code, 200)
        ok_('Mortal' in response.content)

        url = reverse('users.logout')
        response = self.client.get(url)
        eq_(response.status_code, 302)
        path = urlparse(response['location']).path
        eq_(path, settings.LOGOUT_REDIRECT_URL)

        response = self.client.get('/')
        path = urlparse(response['location']).path
        eq_(path, settings.LOGIN_URL)
        eq_(response.status_code, 302)

        response = self.client.get(settings.LOGIN_URL)
        eq_(response.status_code, 200)
        ok_('Mortal' not in response.content)

    def test_login_with_ldap_user(self):
        fake_user = [
          ('mail=mortal,o=com,dc=mozilla',
           {'cn': ['Mortal Bengtsson'],
            'givenName': ['Mortal'],
            'mail': ['mortal@mozilla.com'],
            'sn': ['Bengtss\xc2\xa2n'],
            'uid': ['mortal'],
            })
        ]

        fake_user_plus = [
          ('mail=mortal,o=com,dc=mozilla',
           {'cn': ['Mortal Bengtsson'],
            'givenName': ['Mortal'],
            'mail': ['mortal@mozilla.com'],
            'sn': ['Bengtss\xc2\xa2n'],
            'uid': ['mortal'],
            'manager': ['mail=lthom@mozilla.com,dc=foo'],
            'physicalDeliveryOfficeName': ['London:::GB'],
            })
        ]

        ldap.initialize = Mock(return_value=MockLDAP({
          'mail=mortal@mozilla.com,o=com,dc=mozilla': fake_user,
          '(mail=mortal@mozilla.com)': fake_user_plus,
          },
          credentials={
            'mail=mortal@mozilla.com,o=com,dc=mozilla': 'secret',
          }))

        url = reverse('users.login')
        response = self.client.get(url)
        eq_(response.status_code, 200)

        response = self.client.post(url, {'username': 'mortal@mozilla.com',
                                          'password': 'wrong'})
        eq_(response.status_code, 200)
        ok_('errorlist' in response.content)

        response = self.client.post(url, {'username': 'mortal@mozilla.com',
                                          'password': 'secret'})
        eq_(response.status_code, 302)
        path = urlparse(response['location']).path
        eq_(path, settings.LOGIN_REDIRECT_URL)

        response = self.client.get('/')
        eq_(response.status_code, 200)
        ok_('Mortal' in response.content)

        user, = User.objects.all()
        eq_(user.email, 'mortal@mozilla.com')
        eq_(user.username, 'mortal')
        eq_(user.first_name, u'Mortal')
        eq_(user.last_name, u'Bengtss\xa2n')

        profile = user.get_profile()
        eq_(profile.manager, 'lthom@mozilla.com')
        eq_(profile.office, u'London:::GB')
        eq_(profile.country, u'GB')
        eq_(profile.city, u'London')

        url = reverse('users.logout')
        response = self.client.get(url)
        eq_(response.status_code, 302)
        path = urlparse(response['location']).path
        eq_(path, settings.LOGOUT_REDIRECT_URL)

        response = self.client.get('/')
        path = urlparse(response['location']).path
        eq_(path, settings.LOGIN_URL)
        eq_(response.status_code, 302)

        response = self.client.get(settings.LOGIN_URL)
        eq_(response.status_code, 200)
        ok_('Mortal' not in response.content)

    def _get_all_inputs(self, html):
        _input_regex = re.compile('<input (.*?)>', re.M | re.DOTALL)
        _attrs_regex = re.compile('(\w+)="([^"]+)"')
        all_attrs = {}
        for input in _input_regex.findall(html):
            attrs = dict(_attrs_regex.findall(input))
            all_attrs[attrs.get('name', attrs.get('id', ''))] = attrs
        return all_attrs

    def test_login_next_redirect(self):
        url = reverse('users.login')
        response = self.client.get(url, {'next': '/foo/bar'})
        eq_(response.status_code, 200)
        attrs = self._get_all_inputs(response.content)
        ok_(attrs[REDIRECT_FIELD_NAME])
        eq_(attrs[REDIRECT_FIELD_NAME]['value'], '/foo/bar')

        mortal = User.objects.create_user(
          'mortal', 'mortal', password='secret'
        )
        mortal.set_password('secret')
        mortal.save()

        response = self.client.post(url, {'username': 'mortal',
                                          'password': 'secret',
                                          'next': '/foo/bar'})
        eq_(response.status_code, 302)
        path = urlparse(response['location']).path
        eq_(path, '/foo/bar')

    def test_login_failure(self):
        ldap.initialize = Mock(return_value=MockLDAP({
          '(mail=mortal@mozilla.com)': 'anything',
          },
          credentials={
            'mail=mortal,o=com,dc=mozilla': 'secret',
          }))

        url = reverse('users.login')
        mortal = User.objects.create(
          username='mortal',
          first_name='Mortal',
          last_name='Joe',
          email='mortal@mozilla.com',
        )
        mortal.set_password('secret')
        mortal.save()

        response = self.client.post(url, {'username': 'mortal',
                                          'password': 'xxx'})
        eq_(response.status_code, 200)
        ok_('errorlist' in response.content)

        response = self.client.post(url, {'username': 'xxx',
                                          'password': 'secret'})
        eq_(response.status_code, 200)
        ok_('errorlist' in response.content)

    def test_login_rememberme(self):
        url = reverse('users.login')
        mortal = User.objects.create(
          username='mortal',
          first_name='Mortal',
          last_name='Joe'
        )
        mortal.set_password('secret')
        mortal.save()

        response = self.client.post(url, {'username': 'mortal',
                                          'password': 'secret',
                                          'rememberme': ''})
        eq_(response.status_code, 302)
        expires = self.client.cookies['sessionid']['expires']
        date = ' '.join(expires.split()[1:])
        then = datetime.datetime.strptime(date, '%d-%b-%Y %H:%M:%S %Z')
        today = datetime.datetime.today()
        days = settings.SESSION_COOKIE_AGE / 24 / 3600
        try:
            eq_((then - today).days, days)
        except AssertionError:
            print "Make sure your settings.TIME_ZONE matches your OS clock"
            raise

    def test_login_by_email(self):
        url = reverse('users.login')

        mortal = User.objects.create(
          username='mortal',
          email='mortal@hotmail.com',
          first_name='Mortal',
          last_name='Joe'
        )
        mortal.set_password('secret')
        mortal.save()

        response = self.client.post(url, {'username': 'Mortal@hotmail.com',
                                          'password': 'secret'})
        eq_(response.status_code, 302)

        response = self.client.get('/')
        eq_(response.status_code, 200)
        ok_('Mortal' in response.content)

    def test_mozilla_ldap_backend_basic(self):
        back = MozillaLDAPBackend()

        class MockConnection:

            def __init__(self, mock_result):
                self.mock_result = mock_result

            def search_s(self, dn, scope, filter=None, attrs=None):
                return self.mock_result

        class LDAPUser:
            results = (['somedn', {
                  'uid': 'peter',
                  'givenName': 'Peter',
                  'sn': 'Bengtsson',
                  'mail': 'mail@peterbe.com',
                }],)

            def __init__(self, attrs):
                self.attrs = attrs

            def _get_connection(self):
                return MockConnection(self.results)

        ldap_user = LDAPUser({'mail': ['mail@peterbe.com']})

        user, created = back.get_or_create_user('peter', ldap_user)

        ok_(created)
        ok_(user)
        eq_(user.username, 'peter')

        peppe = User.objects.create_user(
          'peppe',
          'mail@peterbe.com',
        )
        user, created = back.get_or_create_user('peter', ldap_user)
        ok_(not created)
        eq_(user, peppe)

        username = back.ldap_to_django_username('mail@peterbe.com')
        eq_(username, 'peppe')
        username = back.ldap_to_django_username('lois@peterbe.com')
        eq_(username, 'lois')

    def test_login_username_form_field(self):
        url = reverse('users.login')
        response = self.client.get(url)
        eq_(response.status_code, 200)
        html = response.content.split('<form')[1].split('</form')[0]
        inputs = self._get_all_inputs(html)
        input = inputs['username']
        eq_(input['autocorrect'], 'off')
        eq_(input['spellcheck'], 'false')
        eq_(input['autocapitalize'], 'off')
        eq_(input['type'], 'email')

    def test_editing_user_profile(self):
        url = reverse('users.profile')

        mortal = User.objects.create(
          username='mortal',
          email='mortal@hotmail.com',
          first_name='Mortal',
          last_name='Joe'
        )
        mortal.set_password('secret')
        mortal.save()

        response = self.client.get(url)
        eq_(response.status_code, 302)
        assert self.client.login(username='mortal', password='secret')

        response = self.client.get(url)
        eq_(response.status_code, 200)

        data = {
                'country': 'GB',
                'city': 'London',
                }
        response = self.client.post(url, data)
        eq_(response.status_code, 302)

        profile = UserProfile.objects.get(user=mortal)
        eq_(profile.country, 'GB')
        eq_(profile.city, 'London')
