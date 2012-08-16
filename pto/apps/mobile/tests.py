# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import datetime
from collections import defaultdict
from urlparse import urlparse
from nose.tools import eq_, ok_
from django.conf import settings
from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.utils import simplejson as json
from pto.apps.dates.tests.test_views import ViewsTestMixin
from pto.apps.dates.models import Entry, Hours
from test_utils import TestCase


class MobileViewsTest(TestCase, ViewsTestMixin):

    def xx_login(self):
        peter = User.objects.create(
          username='peter',
          email='pbengtsson@mozilla.com',
          first_name='Peter',
          last_name='Bengtsson',
        )
        peter.set_password('secret')
        peter.save()
        assert self.client.login(username='peter', password='secret')

    def test_home(self):
        url = reverse('mobile.home')
        response = self.client.get(url)
        eq_(response.status_code, 200)

        peter = User.objects.create(
          username='peter',
          email='pbengtsson@mozilla.com',
          first_name='Peter',
          last_name='Bengtsson',
        )
        peter.set_password('secret')
        peter.save()

        assert self.client.login(username='peter', password='secret')

        url = reverse('mobile.home')
        response = self.client.get(url)
        eq_(response.status_code, 200)

    def test_login(self):
        peter = User.objects.create(
          username='peter',
          email='pbengtsson@mozilla.com',
          first_name='Peter',
          last_name='Bengtsson',
        )
        peter.set_password('secret')
        peter.save()

        url = reverse('mobile.login')
        response = self.client.get(url)
        eq_(response.status_code, 200)
        ok_(not json.loads(response.content)['logged_in'])

        response = self.client.post(url, {
          'username': peter.email,
          'password': 'wrong'
        })
        eq_(response.status_code, 200)
        struct = json.loads(response.content)
        ok_(struct['form_errors']['__all__'])
        response = self.client.post(url, {
          'username': peter.email.title(),
          'password': 'secret'
        })
        eq_(response.status_code, 200)
        struct = json.loads(response.content)
        ok_(struct['ok'])

        response = self.client.get(url)
        eq_(response.status_code, 200)
        ok_(json.loads(response.content)['logged_in'])

    def test_logout(self):
        url = reverse('mobile.logout')

        self._login()
        response = self.client.get(reverse('mobile.login'))
        eq_(response.status_code, 200)
        ok_(json.loads(response.content)['logged_in'])

        response = self.client.post(url)
        eq_(response.status_code, 200)
        struct = json.loads(response.content)
        ok_(struct['ok'])

        response = self.client.get(reverse('mobile.login'))
        eq_(response.status_code, 200)
        ok_(not json.loads(response.content)['logged_in'])

    def test_right_now_json(self):
        url = reverse('mobile.right_now')
        response = self.client.get(url)
        eq_(response.status_code, 200)
        ok_(json.loads(response.content)['error'])

        bobby = User.objects.create_user(
          'bobby', 'bobby@mozilla.com',
        )
        freddy = User.objects.create_user(
          'freddy', 'freddy@mozilla.com',
        )
        dicky = User.objects.create_user(
          'dicky', 'dicky@mozilla.com',
        )
        harry = User.objects.create_user(
          'harry', 'harry@mozilla.com',
        )
        mike = User.objects.create_user(
          'mike', 'mike@mozilla.com',
        )

        today = datetime.date.today()

        Entry.objects.create(
          user=bobby,
          total_hours=16,
          start=today - datetime.timedelta(days=2),
          end=today - datetime.timedelta(days=1),
        )

        Entry.objects.create(
          user=freddy,
          total_hours=16,
          start=today - datetime.timedelta(days=1),
          end=today,
        )

        Entry.objects.create(
          user=dicky,
          total_hours=4,
          start=today,
          end=today,
        )

        Entry.objects.create(
          user=harry,
          total_hours=16,
          start=today + datetime.timedelta(days=1),
          end=today + datetime.timedelta(days=2),
        )

        user = self._login()
        response = self.client.get(url)
        eq_(response.status_code, 200)
        struct = json.loads(response.content)
        eq_(len(struct['now']), 0)
        eq_(len(struct['upcoming']), 0)

        # nothing is returned because the current isnt' following
        # these people
        profile = user.get_profile()
        profile.manager = mike.email
        profile.save()

        profile = freddy.get_profile()
        profile.manager = mike.email
        profile.save()

        profile = bobby.get_profile()
        profile.manager = mike.email
        profile.save()

        profile = dicky.get_profile()
        profile.manager = mike.email
        profile.save()

        profile = harry.get_profile()
        profile.manager = mike.email
        profile.save()

        response = self.client.get(url)
        eq_(response.status_code, 200)
        struct = json.loads(response.content)
        eq_(len(struct['now']), 2)
        eq_(len(struct['upcoming']), 1)

        names = [x['name'] for x in struct['now']]
        ok_('freddy' in names[0])
        ok_('dicky' in names[1])
        names = [x['name'] for x in struct['upcoming']]
        ok_('harry' in names[0])

    def test_taken_json(self):
        url = reverse('mobile.taken')
        response = self.client.get(url)
        eq_(response.status_code, 200)
        ok_(json.loads(response.content)['error'])

        user = self._login()
        response = self.client.get(url)
        struct = json.loads(response.content)
        eq_(struct['taken'], '0 days')

        profile = user.get_profile()
        profile.country = 'US'
        profile.save()

        response = self.client.get(url)
        struct = json.loads(response.content)
        from pto.apps.dates.views import get_taken_info
        eq_(struct, get_taken_info(user))

    def test_notify(self):
        url = reverse('mobile.notify')
        response = self.client.get(url)
        eq_(response.status_code, 405)

        response = self.client.post(url, {})
        eq_(response.status_code, 200)
        ok_(json.loads(response.content)['error'])

        self._login()
        today = datetime.date.today()
        data = {
          'start': 'xxx'
        }
        response = self.client.post(url, data)
        struct = json.loads(response.content)
        ok_(struct['form_errors']['start'])
        ok_(struct['form_errors']['end'])

        user, = User.objects.all()
        # first create an unfinished entry and notice it will be deleted
        Entry.objects.create(
          user=user,
          start=today + datetime.timedelta(days=10),
          end=today + datetime.timedelta(days=10),
          details='Unfinished'
        )
        # ...and one that won't be deleted
        Entry.objects.create(
          user=user,
          start=today + datetime.timedelta(days=12),
          end=today + datetime.timedelta(days=12),
          total_hours=8,
          details='Finished'
        )

        data = {
          'start': today,
          'end': today + datetime.timedelta(days=1),
          'details': '\tSailing!  ',
        }
        response = self.client.post(url, data)
        struct = json.loads(response.content)
        ok_(struct['entry'])
        entry = Entry.objects.get(pk=struct['entry'])
        eq_(entry.start, today)
        eq_(entry.end, today + datetime.timedelta(days=1))
        eq_(entry.total_hours, None)
        eq_(entry.details, 'Sailing!')

        ok_(Entry.objects.get(details='Finished'))
        ok_(not Entry.objects.filter(details='Unfinished').count())

    def test_save_hours(self):
        url = reverse('mobile.save_hours')
        response = self.client.get(url)
        eq_(response.status_code, 405)

        # not logged in
        response = self.client.post(url, {})
        eq_(response.status_code, 200)
        ok_(json.loads(response.content)['error'])

        self._login()
        # logged in but not providing entry ID
        response = self.client.post(url, {})
        eq_(response.status_code, 400)

        response = self.client.post(url, {'entry': 999})
        eq_(response.status_code, 404)

        # create an entry that belongs to someone else
        bob = User.objects.create(username='bob')
        bobs_entry = Entry.objects.create(
          user=bob,
          start=datetime.date.today(),
          end=datetime.date.today(),
          total_hours=8,
        )

        response = self.client.post(url, {'entry': bobs_entry.pk})
        eq_(response.status_code, 403)

        # Create an incomplete entry
        peter = User.objects.get(username='peter')  # see _login()
        today = datetime.date(2011, 11, 2)
        assert today.strftime('%A') == 'Wednesday'
        entry = Entry.objects.create(
          user=peter,
          start=today + datetime.timedelta(days=1),
          end=today + datetime.timedelta(days=2),
          details='Boo!'
        )

        data = {
          'entry': entry.pk,
        }
        response = self.client.post(url, data)
        eq_(response.status_code, 200)
        struct = json.loads(response.content)
        ok_(struct['form_errors'])

        def fmt(d):
            return d.strftime('d-%Y%m%d')

        data[fmt(today + datetime.timedelta(days=1))] = 8
        data[fmt(today + datetime.timedelta(days=2))] = 4
        response = self.client.post(url, data)
        eq_(response.status_code, 200)
        struct = json.loads(response.content)
        ok_(struct['ok'])

        entry = Entry.objects.get(pk=data['entry'])
        eq_(entry.total_hours, 8 + 4)

        hours = Hours.objects.filter(entry=entry)
        eq_(hours.count(), 2)

    def test_hours_json(self):
        url = reverse('mobile.hours')
        response = self.client.get(url)
        eq_(response.status_code, 200)
        ok_(json.loads(response.content)['error'])

        self._login()
        response = self.client.get(url, {'entry': ''})
        eq_(response.status_code, 200)
        ok_(json.loads(response.content)['error'])

        # create an entry that belongs to someone else
        bob = User.objects.create(username='bob')
        bobs_entry = Entry.objects.create(
          user=bob,
          start=datetime.date.today(),
          end=datetime.date.today(),
          total_hours=8,
        )

        response = self.client.get(url, {'entry': bobs_entry.pk})
        eq_(response.status_code, 403)

        # make a fake entry so that the current days are prefilled
        today = datetime.date(2011, 10, 25)  # a Tuesday
        peter = User.objects.get(username='peter')  # see _login()
        entry = Entry.objects.create(
          user=peter,
          start=today,
          end=today + datetime.timedelta(days=1),
        )

        other_entry = Entry.objects.create(
          user=peter,
          start=today + datetime.timedelta(days=1),
          end=today + datetime.timedelta(days=1),
          total_hours=4
        )
        other_hours = Hours.objects.create(
          entry=other_entry,
          date=today + datetime.timedelta(days=1),
          hours=4,
        )

        response = self.client.get(url, {'entry': entry.pk})
        eq_(response.status_code, 200)
        struct = json.loads(response.content)
        hours1 = struct[0]
        hours2 = struct[1]

        def fmt(d):
            return d.strftime('d-%Y%m%d')

        eq_(hours1['full_day'], today.strftime(settings.DEFAULT_DATE_FORMAT))
        eq_(hours1['value'], 8)
        eq_(hours1['key'], fmt(today))
        tomorrow = today + datetime.timedelta(days=1)
        eq_(hours2['full_day'], tomorrow.strftime(settings.DEFAULT_DATE_FORMAT))
        eq_(hours2['value'], 4)
        eq_(hours2['key'], fmt(tomorrow))


    def test_settings_json(self):
        url = reverse('mobile.settings')
        response = self.client.get(url)
        eq_(response.status_code, 200)
        ok_(json.loads(response.content)['error'])

        self._login()
        peter = User.objects.get(username='peter')
        profile = peter.get_profile()
        response = self.client.get(url)
        eq_(response.status_code, 200)
        struct = json.loads(response.content)
        eq_(struct['username'], peter.username)
        eq_(struct['email'], peter.email)
        ok_(peter.get_full_name() in struct['full_name'])
        ok_(peter.email in struct['full_name'])

        profile.country = 'GB'
        profile.city = 'London'
        profile.start_date = datetime.date(2011, 4, 1)
        profile.save()
        response = self.client.get(url)
        struct = json.loads(response.content)
        eq_(struct['start_date'], profile.start_date.strftime('%Y-%m-%d'))
        eq_(struct['country'], 'GB')
        eq_(struct['city'], 'London')

    def test_save_settings(self):
        # to be able to save country='GB' this must be a valid choice
        bob = User.objects.create(username='bob')
        bob_profile = bob.get_profile()
        bob_profile.country = 'GB'
        bob_profile.save()

        url = reverse('mobile.save_settings')
        response = self.client.get(url)
        eq_(response.status_code, 405)

        # not logged in
        response = self.client.post(url, {})
        eq_(response.status_code, 200)
        ok_(json.loads(response.content)['error'])

        self._login()
        peter = User.objects.get(username='peter')
        profile = peter.get_profile()
        data = {
          'city': 'London',
          'country': 'GB',
        }
        response = self.client.post(url, data)
        eq_(response.status_code, 200)
        struct = json.loads(response.content)
        ok_(struct['ok'])

        from pto.apps.users.models import UserProfile
        profile = UserProfile.objects.get(user__username='peter')
        eq_(profile.country, 'GB')
        eq_(profile.city, 'London')

    def test_save_settings_security_hack(self):
        bob = User.objects.create(username='bob')
        bob_profile = bob.get_profile()
        bob_profile.city = 'Mountain View'
        bob_profile.country = 'United States'
        bob_profile.save()

        url = reverse('mobile.save_settings')
        self._login()
        peter = User.objects.get(username='peter')
        profile = peter.get_profile()
        # The ProfileForm is a ModelForm and used like this:
        #    if form.is_valid():
        #        form.save()
        # Even though we only want to save country and city
        # we can try to fool the modelform to save other things too
        data = {
          'city': 'London',
          'country': 'GB',
          'notes': 'Hack Attack!',
        }
        response = self.client.post(url, data)
        eq_(response.status_code, 200)
        struct = json.loads(response.content)
        ok_(struct['ok'])

        from pto.apps.users.models import UserProfile
        profile = UserProfile.objects.get(user__username='peter')
        eq_(profile.country, 'GB')
        eq_(profile.city, 'London')
        eq_(profile.notes, '')

    def test_exit_mobile(self):
        self._login()
        # if you end up on the mobile pages and want out,
        # it'll set a cookie
        url = reverse('mobile.exit')
        response = self.client.get(url)
        eq_(response.status_code, 302)
        eq_(urlparse(response['location']).path, '/')
        ok_(self.client.cookies['no-mobile'].value)

        # undo that by visiting the mobile home page again
        url = reverse('mobile.home')
        response = self.client.get(url)
        eq_(response.status_code, 200)
        ok_(not self.client.cookies['no-mobile'].value)

    def test_appcache(self):
        url = reverse('mobile.appcache')
        response = self.client.get(url)
        eq_(response['Content-Type'], 'text/cache-manifest')
        lines = response.content.splitlines()

        eq_(lines[0], 'CACHE MANIFEST')
        buckets = defaultdict(list)
        for line in lines[1:]:
            if not line.strip() or line.strip().startswith('#'):
                continue
            if line.strip().endswith(':'):
                bucket = line.strip()
            else:
                buckets[bucket].append(line)

        ok_(buckets['NETWORK:'])
        ok_(buckets['CACHE:'])
