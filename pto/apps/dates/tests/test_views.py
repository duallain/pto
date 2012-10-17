# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import re
import time
import csv
import random
from urlparse import urlparse
from collections import defaultdict
import datetime
from django.test.client import RequestFactory
from django.test.utils import override_settings
from django.conf import settings
from django.core.urlresolvers import reverse
from django.contrib.auth.models import User
from django.utils import simplejson as json
from django.core import mail
from pto.apps.dates.models import (
  Entry,
  Hours,
  BlacklistedUser,
  FollowingUser,
  UserKey
)
from nose.tools import eq_, ok_
from test_utils import TestCase
from mock import Mock
import ldap
from pto.apps.users.utils import ldap_lookup
from pto.apps.users.utils.ldap_mock import MockLDAP


def unicode_csv_reader(unicode_csv_data,
                       encoding='utf-8',
                       **kwargs):
    # csv.py doesn't do Unicode; encode temporarily as UTF-8:
    csv_reader = csv.reader(utf_8_encoder(unicode_csv_data, encoding),
                             **kwargs)
    for row in csv_reader:
        # decode UTF-8 back to Unicode, cell by cell:
        yield [unicode(cell, encoding) for cell in row]


def utf_8_encoder(unicode_csv_data, encoding):
    for line in unicode_csv_data:
        yield line.encode(encoding)

_THIS_YEAR = datetime.date.today().year

class ViewsTestMixin(object):
    def _login(self, user=None):
        if not user:
            user = User.objects.create(
              username='peter',
              email='pbengtsson@mozilla.com',
              first_name='Peter',
              last_name='Bengtsson',
            )
        user.set_password('secret')
        user.save()
        assert self.client.login(username=user.username, password='secret')
        return user

    def _create_hr_manager(self, username='jill', email='jill@mozilla.com'):
        user = User.objects.create(
          username=username,
          email=email
        )
        profile = user.get_profile()
        profile.hr_manager = True
        profile.save()
        return user

    def _create_entry_hours(self, entry, *hours):
        date = entry.start
        i = 0
        while date <= entry.end:
            try:
                h = hours[i]
            except IndexError:
                h = 8
            Hours.objects.create(
              entry=entry,
              date=date,
              hours=h,
            )
            i += 1
            date += datetime.timedelta(days=1)


class ViewsTest(TestCase, ViewsTestMixin):

    def setUp(self):
        super(ViewsTest, self).setUp()
        # A must when code in this app relies on cache
        settings.CACHE_BACKEND = 'locmem:///'

        ldap.open = Mock('ldap.open')
        ldap.open.mock_returns = Mock('ldap_connection')
        ldap.set_option = Mock(return_value=None)

        boss = [
          ('mail=boss@mozilla.com,o=com,dc=mozilla',
           {'cn': ['Hugo Boss'],
            'givenName': ['Hugo'],
            'mail': ['boss@mozilla.com'],
            'sn': ['Boss'],
            'uid': ['hugo'],
            })
        ]

        ldap.initialize = Mock(return_value=MockLDAP({
          '(mail=boss@mozilla.com)': boss,
          },
          credentials={
            settings.AUTH_LDAP_BIND_DN: settings.AUTH_LDAP_BIND_PASSWORD,
          }))

    def _make_manager(self, user, manager):
        profile = user.get_profile()
        profile.manager_user = manager
        profile.save()

    def test_404_page(self):
        url = '/ojsfpijweofpjwf/qpijf/'
        response = self.client.get(url)
        eq_(response.status_code, 404)
        ok_('Page not found' in response.content)

    @override_settings(TRACEBACKS_ON_500=True)
    def test_500_page_with_traceback(self):

        root_urlconf = __import__(settings.ROOT_URLCONF,
                                  globals(), locals(), ['urls'], -1)
        # ...so that we can access the 'handler500' defined in there
        par, end = root_urlconf.handler500.rsplit('.', 1)
        # ...which is an importable reference to the real handler500 function
        views = __import__(par, globals(), locals(), [end], -1)
        # ...and finally we the handler500 function at hand
        handler500 = getattr(views, end)

        # to make a mock call to the django view functions you need a request
        fake_request = RequestFactory().request(**{'wsgi.input': None})

        # the reason for first causing an exception to be raised is because
        # the handler500 function is only called by django when an exception
        # has been raised which means sys.exc_info() is something.
        try:
            raise NameError("sloppy code!")
        except NameError:
            # do this inside a frame that has a sys.exc_info()
            response = handler500(fake_request)
            eq_(response.status_code, 500)
            ok_('NameError' in response.content)

    def test_500_page_without_traceback(self):
        # TRACEBACKS_ON_500 is (and should be) by default False
        root_urlconf = __import__(settings.ROOT_URLCONF,
                                  globals(), locals(), ['urls'], -1)
        # ...so that we can access the 'handler500' defined in there
        par, end = root_urlconf.handler500.rsplit('.', 1)
        # ...which is an importable reference to the real handler500 function
        views = __import__(par, globals(), locals(), [end], -1)
        # ...and finally we the handler500 function at hand
        handler500 = getattr(views, end)

        # to make a mock call to the django view functions you need a request
        fake_request = RequestFactory().request(**{'wsgi.input': None})

        # the reason for first causing an exception to be raised is because
        # the handler500 function is only called by django when an exception
        # has been raised which means sys.exc_info() is something.
        try:
            raise NameError("sloppy code!")
        except NameError:
            # do this inside a frame that has a sys.exc_info()
            response = handler500(fake_request)
            eq_(response.status_code, 500)
            ok_('NameError' not in response.content)

    def test_notify_basics(self):
        url = reverse('dates.notify')
        response = self.client.get(url)
        eq_(response.status_code, 302)
        path = urlparse(response['location']).path
        eq_(path, settings.LOGIN_URL)

        peter = User.objects.create(
          username='peter',
          email='pbengtsson@mozilla.com',
          first_name='Peter',
          last_name='Bengtsson',
        )
        peter.set_password('secret')
        peter.save()

        assert self.client.login(username='peter', password='secret')
        response = self.client.get(url)
        eq_(response.status_code, 200)

        monday = datetime.date(2018, 1, 1)  # I know this is a Monday
        wednesday = monday + datetime.timedelta(days=2)
        response = self.client.post(url, {'start': wednesday,
                                          'end': monday})
        eq_(response.status_code, 200)

        details = 'Going on a cruise'
        response = self.client.post(url, {'start': monday,
                                          'end': wednesday,
                                          'details': details})
        eq_(response.status_code, 302)

        entry, = Entry.objects.all()
        eq_(entry.user, peter)
        eq_(entry.start, monday)
        eq_(entry.end, wednesday)
        eq_(entry.total_hours, None)

        url = reverse('dates.hours', args=[entry.pk])
        eq_(urlparse(response['location']).path, url)

        response = self.client.get(url)
        eq_(response.status_code, 200)

        # expect an estimate of the total number of hours
        # xxx This is an ugly test!
        ok_('<h5 id="date_discriminator_hours">3</h5>' in response.content)

        # you can expect to see every date laid out
        ok_(monday.strftime(settings.DEFAULT_DATE_FORMAT)
            in response.content)
        tuesday = monday + datetime.timedelta(days=1)
        ok_(tuesday.strftime(settings.DEFAULT_DATE_FORMAT)
            in response.content)
        ok_(wednesday.strftime(settings.DEFAULT_DATE_FORMAT)
            in response.content)

        # check that the default WORK_DAY radio inputs are checked
        radio_inputs = self._get_inputs(response.content, type="radio")
        for name, attrs in radio_inputs.items():
            if attrs['value'] == str(settings.WORK_DAY):
                ok_(attrs['checked'])
            else:
                ok_('checked' not in attrs)

        data = {}
        # let's enter 8 hours on the Monday
        data['d-20180101'] = str(settings.WORK_DAY)
        # 0 on the tuesday
        data['d-20180102'] = str(0)
        # and a half day on Wednesday
        data['d-20180103'] = str(settings.WORK_DAY / 2)

        response = self.client.post(url, data)
        eq_(response.status_code, 200)

        # 0 on the tuesday wasn't an option
        data['d-20180102'] = '-1'  # birthday
        response = self.client.post(url, data)
        eq_(response.status_code, 302)

        entry = Entry.objects.get(pk=entry.pk)
        eq_(entry.total_hours, settings.WORK_DAY + settings.WORK_DAY / 2)

        eq_(Hours.objects.all().count(), 3)
        hour1 = Hours.objects.get(date=monday, entry=entry)
        eq_(hour1.hours, settings.WORK_DAY)
        hour2 = Hours.objects.get(date=tuesday, entry=entry)
        eq_(hour2.hours, 0)
        hour3 = Hours.objects.get(date=wednesday, entry=entry)
        eq_(hour3.hours, settings.WORK_DAY / 2)

        # expect it also to have sent a bunch of emails
        assert len(mail.outbox)
        email = mail.outbox[-1]
        #eq_(email.to, [peter.email])
        ok_(email.to)
        eq_(email.from_email, peter.email)
        ok_(peter.first_name in email.subject)
        ok_(peter.last_name in email.subject)
        ok_(peter.first_name in email.body)
        ok_(peter.last_name in email.body)
        ok_(entry.details in email.body)
        ok_(entry.start.strftime(settings.DEFAULT_DATE_FORMAT)
            in email.body)
        ok_('submitted 1.5 days of vacation' in email.body)

        eq_(email.cc, [peter.email])
        ok_('--\n%s' % settings.EMAIL_SIGNATURE in email.body)

    def test_overlap_dates_errors(self):
        return  # Obsolete now

        monday = datetime.date(2011, 7, 25)
        tuesday = monday + datetime.timedelta(days=1)
        wednesday = monday + datetime.timedelta(days=2)
        thursday = monday + datetime.timedelta(days=3)
        friday = monday + datetime.timedelta(days=4)

        peter = User.objects.create(
          username='peter',
          email='pbengtsson@mozilla.com',
          first_name='Peter',
          last_name='Bengtsson',
        )

        entry = Entry.objects.create(
          user=peter,
          start=monday,
          end=tuesday,
          total_hours=16,
        )
        Hours.objects.create(
          entry=entry,
          date=monday,
          hours=8,
        )
        Hours.objects.create(
          entry=entry,
          date=tuesday,
          hours=8,
        )

        entry2 = Entry.objects.create(
          user=peter,
          start=friday,
          end=friday,
          total_hours=8,
        )
        Hours.objects.create(
          entry=entry2,
          date=friday,
          hours=8,
        )

        url = reverse('dates.notify')
        peter.set_password('secret')
        peter.save()
        assert self.client.login(username='peter', password='secret')
        response = self.client.get(url)
        eq_(response.status_code, 200)

        # make it start BEFORE monday and end on the monday
        response = self.client.post(url, {
          'start': monday - datetime.timedelta(days=3),
          'end': monday,
          'details': 'Going on a cruise',
        })
        eq_(response.status_code, 200)
        ok_('errorlist' in response.content)
        ok_('overlaps' in response.content)

        response = self.client.post(url, {
          'start': thursday,
          'end': friday,
          'details': 'Going on a cruise',
        })
        eq_(response.status_code, 200)
        ok_('errorlist' in response.content)
        ok_('overlaps' in response.content)

        response = self.client.post(url, {
          'start': tuesday,
          'end': wednesday,
          'details': 'Going on a cruise',
        })
        eq_(response.status_code, 200)
        ok_('errorlist' in response.content)
        ok_('overlaps' in response.content)

        response = self.client.post(url, {
          'start': friday,
          'end': friday,
          'details': 'Going on a cruise',
        })
        eq_(response.status_code, 200)
        ok_('errorlist' in response.content)
        ok_('overlaps' in response.content)

        response = self.client.post(url, {
          'start': friday,
          'end': friday + datetime.timedelta(days=7),
          'details': 'Going on a cruise',
        })
        eq_(response.status_code, 200)
        ok_('errorlist' in response.content)
        ok_('overlaps' in response.content)

        assert Entry.objects.all().count() == 2
        # add an entry with total_hours=None
        Entry.objects.create(
          user=peter,
          start=thursday,
          end=thursday,
          total_hours=None
        )
        assert Entry.objects.all().count() == 3

        response = self.client.post(url, {
          'start': wednesday,
          'end': thursday,
          'details': 'Going on a cruise',
        })
        eq_(response.status_code, 302)

        # added one and deleted one
        assert Entry.objects.all().count() == 3

    def _get_inputs(self, html, multiple=False, tag='input', **filters):
        _input_regex = re.compile('<%s (.*?)>' % tag, re.M | re.DOTALL)
        _attrs_regex = re.compile('(\w+)="([^"]+)"')
        if multiple:
            all_attrs = defaultdict(list)
        else:
            all_attrs = {}
        for input in _input_regex.findall(html):
            attrs = dict(_attrs_regex.findall(input))
            name = attrs.get('name', attrs.get('id', ''))
            for k, v in filters.items():
                if attrs.get(k, None) != v:
                    name = None
                    break
            if name:
                if multiple:
                    all_attrs[name].append(attrs)
                else:
                    all_attrs[name] = attrs
        return all_attrs

    def test_forbidden_access(self):
        bob = User.objects.create(
          username='bob',
        )
        today = datetime.date.today()
        entry = Entry.objects.create(
          user=bob,
          total_hours=8,
          start=today,
          end=today
        )

        peter = User.objects.create(
          username='peter',
          email='pbengtsson@mozilla.com',
          first_name='Peter',
          last_name='Bengtsson',
        )
        peter.set_password('secret')
        peter.save()
        assert self.client.login(username='peter', password='secret')
        url1 = reverse('dates.hours', args=[entry.pk])
        response = self.client.get(url1)
        eq_(response.status_code, 403)  # forbidden

        url2 = reverse('dates.emails_sent', args=[entry.pk])
        response = self.client.get(url2)
        eq_(response.status_code, 403)  # forbidden

        peter.is_staff = True
        peter.save()

        response = self.client.get(url1)
        eq_(response.status_code, 200)
        response = self.client.get(url2)
        eq_(response.status_code, 200)

    def test_calendar_events(self):
        url = reverse('dates.calendar_events')
        response = self.client.get(url)
        eq_(response.status_code, 403)

        peter = User.objects.create(
          username='peter',
          email='pbengtsson@mozilla.com',
          first_name='Peter',
          last_name='Bengtsson',
        )
        peter.set_password('secret')
        peter.save()
        assert self.client.login(username=peter.email, password='secret')

        response = self.client.get(url)
        eq_(response.status_code, 400)
        _start = datetime.datetime(2011, 7, 1)
        data = {'start': time.mktime(_start.timetuple())}
        response = self.client.get(url, data)
        eq_(response.status_code, 400)
        _end = datetime.datetime(2011, 8, 1) - datetime.timedelta(days=1)
        data['end'] = 'x' * 12
        response = self.client.get(url, data)
        eq_(response.status_code, 400)
        data['end'] = time.mktime(_end.timetuple())
        response = self.client.get(url, data)
        eq_(response.status_code, 200)
        struct = json.loads(response.content)
        eq_(struct, {'colors': [], 'events': []})

        # add some entries
        entry1 = Entry.objects.create(
          user=peter,
          start=datetime.date(2011, 7, 2),
          end=datetime.date(2011, 7, 2),
          total_hours=8,
        )

        entry2 = Entry.objects.create(
          user=peter,
          start=datetime.date(2011, 6, 30),
          end=datetime.date(2011, 7, 1),
          total_hours=8 * 2,
        )

        entry3 = Entry.objects.create(
          user=peter,
          start=datetime.date(2011, 7, 31),
          end=datetime.date(2011, 8, 1),
          total_hours=8 * 2,
        )

        response = self.client.get(url, data)
        eq_(response.status_code, 200)
        struct = json.loads(response.content)
        events = struct['events']
        eq_(len(events), 3)
        eq_(set([x['id'] for x in events]),
            set([entry1.pk, entry2.pk, entry3.pk]))

        # add some that are outside the search range and should not be returned
        entry4 = Entry.objects.create(
          user=peter,
          start=datetime.date(2011, 6, 30),
          end=datetime.date(2011, 6, 30),
          total_hours=8,
        )

        entry5 = Entry.objects.create(
          user=peter,
          start=datetime.date(2011, 8, 1),
          end=datetime.date(2011, 8, 1),
          total_hours=8,
        )

        response = self.client.get(url, data)
        eq_(response.status_code, 200)
        struct = json.loads(response.content)
        events = struct['events']
        eq_(len(events), 3)
        # unchanged
        eq_(set([x['id'] for x in events]),
            set([entry1.pk, entry2.pk, entry3.pk]))

        # add a curve-ball that spans the whole range
        entry6 = Entry.objects.create(
          user=peter,
          start=datetime.date(2011, 6, 30),
          end=datetime.date(2011, 8, 1),
          total_hours=8 * 30,
        )

        response = self.client.get(url, data)
        eq_(response.status_code, 200)
        struct = json.loads(response.content)
        events = struct['events']
        eq_(len(events), 4)
        # one more now
        eq_(set([x['id'] for x in events]),
            set([entry1.pk, entry2.pk, entry3.pk, entry6.pk]))

    def test_calendar_events_summation(self):
        url = reverse('dates.calendar_events')

        peter = User.objects.create(
          username='peter',
          email='pbengtsson@mozilla.com',
          first_name='Peter',
          last_name='Bengtsson',
        )
        peter.set_password('secret')
        peter.save()
        assert self.client.login(username=peter.email, password='secret')

        # add some entries
        entry = Entry.objects.create(
          user=peter,
          start=datetime.date(2011, 7, 2),
          end=datetime.date(2011, 7, 4),
          total_hours=8 + 4 + 8,
        )

        Hours.objects.create(
          entry=entry,
          date=datetime.date(2011, 7, 2),
          hours=8
        )

        Hours.objects.create(
          entry=entry,
          date=datetime.date(2011, 7, 3),
          hours=4
        )

        Hours.objects.create(
          entry=entry,
          date=datetime.date(2011, 7, 4),
          hours=8
        )

        _start = datetime.datetime(2011, 7, 1)
        _end = datetime.datetime(2011, 8, 1) - datetime.timedelta(days=1)
        data = {
          'start': time.mktime(_start.timetuple()),
          'end': time.mktime(_end.timetuple())
        }
        response = self.client.get(url, data)
        eq_(response.status_code, 200)
        struct = json.loads(response.content)
        events = struct['events']
        event = events[0]
        eq_(event['title'], '2.5 days')

        Hours.objects.all().delete()
        entry.end = datetime.date(2011, 7, 2)
        entry.total_hours = 8
        entry.save()
        self._create_entry_hours(entry)

        response = self.client.get(url, data)
        eq_(response.status_code, 200)
        struct = json.loads(response.content)
        events = struct['events']
        event = events[0]
        eq_(event['title'], '1 day')

        Hours.objects.all().delete()
        entry.end = datetime.date(2011, 7, 2)
        entry.total_hours = 4
        entry.save()
        self._create_entry_hours(entry, 4)

        response = self.client.get(url, data)
        eq_(response.status_code, 200)
        struct = json.loads(response.content)
        events = struct['events']
        event = events[0]
        eq_(event['title'], '4 hours')

    def test_calendar_event_title(self):
        url = reverse('dates.calendar_events')
        peter = User.objects.create(
          username='peter',
          email='pbengtsson@mozilla.com',
          first_name='Peter',
          last_name='Bengtsson',
        )
        peter.set_password('secret')
        peter.save()
        assert self.client.login(username=peter.email, password='secret')

        entry = Entry.objects.create(
          user=peter,
          start=datetime.date(2011, 7, 14),
          end=datetime.date(2011, 7, 14),
          total_hours=4,
          details=''
        )

        _start = datetime.datetime(2011, 7, 1)
        _end = datetime.datetime(2011, 8, 1) - datetime.timedelta(days=1)
        data = {
          'start': time.mktime(_start.timetuple()),
          'end': time.mktime(_end.timetuple())
        }
        response = self.client.get(url, data)
        eq_(response.status_code, 200)
        struct = json.loads(response.content)
        eq_(len(struct), 2)
        events = struct['events']
        eq_(len(events), 1)
        eq_(events[0]['title'], '4 hours')
        colors = struct['colors']
        eq_(len(colors), 1)
        ok_(colors[0]['color'])
        ok_(colors[0]['name'])

        entry.end += datetime.timedelta(days=5)
        entry.total_hours += 8 * 5
        entry.save()

        self._create_entry_hours(entry)

        response = self.client.get(url, data)
        eq_(response.status_code, 200)
        struct = json.loads(response.content)
        eq_(len(struct), 2)
        events = struct['events']
        eq_(len(events), 1)
        eq_(events[0]['title'], '6 days')

        umpa = User.objects.create(
          username='umpa',
          email='umpa@mozilla.com',
          first_name='Umpa',
          last_name='Lumpa',
        )
        entry.user = umpa
        entry.save()

        umpa_profile = umpa.get_profile()
        umpa_profile.manager = 'pbengtsson@mozilla.com'
        umpa_profile.save()

        response = self.client.get(url, data)
        eq_(response.status_code, 200)
        struct = json.loads(response.content)
        eq_(len(struct), 2)
        events = struct['events']
        eq_(struct['colors'][0]['name'], 'Umpa Lumpa')
        eq_(len(events), 1)
        eq_(events[0]['title'], 'Umpa Lumpa - 6 days')

        umpa.first_name = ''
        umpa.last_name = ''
        umpa.save()

        response = self.client.get(url, data)
        eq_(response.status_code, 200)
        struct = json.loads(response.content)
        eq_(len(struct), 2)
        events = struct['events']
        eq_(len(events), 1)
        eq_(events[0]['title'], 'umpa - 6 days')

        entry.details = 'Short'
        entry.save()
        response = self.client.get(url, data)
        eq_(response.status_code, 200)
        struct = json.loads(response.content)
        eq_(len(struct), 2)
        events = struct['events']
        eq_(len(events), 1)
        eq_(events[0]['title'], 'umpa - 6 days, Short')

        entry.details = "This time it's going to be a really long one to test"
        entry.save()
        response = self.client.get(url, data)
        eq_(response.status_code, 200)
        struct = json.loads(response.content)
        eq_(len(struct), 2)
        events = struct['events']
        eq_(len(events), 1)
        ok_(events[0]['title'].startswith('umpa - 6 days, This time'))
        ok_(events[0]['title'].endswith('...'))

        Hours.objects.create(
          entry=entry,
          date=entry.start,
          hours=8,
          birthday=True
        )
        response = self.client.get(url, data)
        eq_(response.status_code, 200)
        struct = json.loads(response.content)
        eq_(len(struct), 2)
        events = struct['events']
        eq_(len(events), 1)
        ok_('birthday' in events[0]['title'])

    def test_notify_free_input(self):
        hr_manager = self._create_hr_manager()
        hr_manager2 = self._create_hr_manager(
          username='betty',
          email='betty@mozilla.com',
        )

        url = reverse('dates.notify')
        peter = User.objects.create(
          username='peter',
          email='pbengtsson@mozilla.com',
          first_name='Peter',
          last_name='Bengtsson',
        )
        peter.set_password('secret')
        peter.save()

        assert self.client.login(username='peter', password='secret')
        response = self.client.get(url)
        eq_(response.status_code, 200)

        _point = 'The following managers will be notified:'
        assert _point in response.content
        default_notified = response.content.split(_point)[1]
        default_notified = default_notified.split('</form>')[0]
        ok_(hr_manager.email in default_notified)
        ok_(hr_manager2.email in default_notified)

        monday = datetime.date(2018, 1, 1)  # I know this is a Monday
        wednesday = monday + datetime.timedelta(days=2)
        notify = """
        mail@email.com,
        foo@bar.com ;
        Peter B <ppp@bbb.com>,
        not valid@ test.com;
        Axel Test <axe l@e..com>
        """
        notify += ';%s' % settings.EMAIL_BLACKLIST[-1]
        response = self.client.post(url, {
          'start': monday,
          'end': wednesday,
          'details': "Having fun",
          'notify': notify.replace('\n', '\t')
        })
        eq_(response.status_code, 200)
        ok_('errorlist' in response.content)

        notify = notify.replace(settings.EMAIL_BLACKLIST[-1], '')
        response = self.client.post(url, {
          'start': monday,
          'end': wednesday,
          'details': "Having fun",
          'notify': notify.replace('\n', '\t')
        })
        eq_(response.status_code, 302)
        url = urlparse(response['location']).path
        response = self.client.get(url)
        eq_(response.status_code, 200)
        tuesday = monday + datetime.timedelta(days=1)
        data = {
          monday.strftime('d-%Y%m%d'): 8,
          tuesday.strftime('d-%Y%m%d'): 8,
          wednesday.strftime('d-%Y%m%d'): 8,
        }
        response = self.client.post(url, data)
        eq_(response.status_code, 302)
        response = self.client.get(response['location'])
        ok_('ppp@bbb.com' in response.content)
        ok_('mail@email.com' in response.content)
        ok_('valid@ test.com' not in response.content)
        ok_('axe l@e..com' not in response.content)
        ok_(hr_manager.email in response.content)
        ok_(hr_manager2.email in response.content)

    def test_notify_notification_attachment(self):
        url = reverse('dates.notify')
        peter = User.objects.create(
          username='peter',
          email='pbengtsson@mozilla.com',
          first_name='Peter',
          last_name='Bengtsson',
        )
        peter.set_password('secret')
        peter.save()

        assert self.client.login(username='peter', password='secret')
        monday = datetime.date(2018, 1, 1)  # I know this is a Monday
        wednesday = monday + datetime.timedelta(days=2)

        entry = Entry.objects.create(
          start=monday,
          end=wednesday,
          user=peter,
        )
        tuesday = monday + datetime.timedelta(days=1)
        data = {
          monday.strftime('d-%Y%m%d'): 8,
          tuesday.strftime('d-%Y%m%d'): 8,
          wednesday.strftime('d-%Y%m%d'): 8,
        }
        url = reverse('dates.hours', args=[entry.pk])
        response = self.client.post(url, data)
        eq_(response.status_code, 302)

        assert len(mail.outbox)
        email = mail.outbox[-1]

    def test_get_minions(self):
        from pto.apps.dates.views import get_minions
        gary = User.objects.create_user(
          'gary', 'gary@mozilla.com'
        )

        todd = User.objects.create_user(
          'todd', 'todd@mozilla.com',
        )
        profile = todd.get_profile()
        profile.manager = gary.email
        profile.save()

        mike = User.objects.create_user(
          'mike', 'mike@mozilla.com',
        )
        profile = mike.get_profile()
        profile.manager = todd.email
        profile.save()

        laura = User.objects.create_user(
          'laura', 'laura@mozilla.com',
        )
        profile = laura.get_profile()
        profile.manager = mike.email
        profile.save()

        peter = User.objects.create_user(
          'peter', 'peter@mozilla.com',
        )
        profile = peter.get_profile()
        profile.manager = laura.email
        profile.save()

        users = get_minions(gary, max_depth=1)
        eq_(users, [todd])

        users = get_minions(gary, max_depth=2)
        eq_(users, [todd, mike])

        users = get_minions(gary, max_depth=3)
        eq_(users, [todd, mike, laura])

        users = get_minions(gary, max_depth=4)
        eq_(users, [todd, mike, laura, peter])

        users = get_minions(gary, max_depth=10)
        eq_(users, [todd, mike, laura, peter])

        # from todd's perspective
        users = get_minions(todd, max_depth=1)
        eq_(users, [mike])

        users = get_minions(todd, max_depth=2)
        eq_(users, [mike, laura])

        users = get_minions(todd, max_depth=3)
        eq_(users, [mike, laura, peter])

        users = get_minions(todd, max_depth=10)
        eq_(users, [mike, laura, peter])

        # from laura's perspective
        users = get_minions(laura, max_depth=1)
        eq_(users, [peter])

        users = get_minions(laura, max_depth=99)
        eq_(users, [peter])

    def test_enter_reversal_pto(self):
        monday = datetime.date(2011, 7, 25)
        tuesday = monday + datetime.timedelta(days=1)

        peter = User.objects.create(
          username='peter',
          email='pbengtsson@mozilla.com',
          first_name='Peter',
          last_name='Bengtsson',
        )

        entry = Entry.objects.create(
          user=peter,
          start=monday,
          end=monday,
          total_hours=8,
        )
        Hours.objects.create(
          entry=entry,
          date=monday,
          hours=8,
        )

        # Suppose you now change your mind and want it to be 4 hours on Monday
        # instead
        url = reverse('dates.notify')
        peter.set_password('secret')
        peter.save()
        assert self.client.login(username='peter', password='secret')
        response = self.client.get(url)
        eq_(response.status_code, 200)

        response = self.client.post(url, {
          'start': monday,
          'end': monday,
          'details': 'Going on a cruise',
        })
        eq_(response.status_code, 302)

        assert Entry.objects.all().count() == 2
        assert Hours.objects.all().count() == 1
        second_entry = Entry.objects.get(details='Going on a cruise')
        assert second_entry.total_hours is None

        url = reverse('dates.hours', args=[second_entry.pk])
        response = self.client.get(url)
        eq_(response.status_code, 200)

        radio_inputs = self._get_inputs(response.content,
                                        type="radio",
                                        checked="checked")
        attrs = radio_inputs.values()[0]
        date_key = radio_inputs.keys()[0]
        eq_(attrs['value'], '8')

        assert date_key == monday.strftime('d-%Y%m%d')
        data = {
          date_key: 4,
        }

        response = self.client.post(url, data)
        eq_(response.status_code, 302)

        eq_(Entry.objects.all().count(), 3)
        eq_(Entry.objects.filter(user=peter).count(), 3)
        eq_(Hours.objects.all().count(), 3)

        second_entry = Entry.objects.get(pk=second_entry.pk)
        eq_(second_entry.total_hours, 4)

        total = sum(x.total_hours for x in Entry.objects.all())
        eq_(total, 4)

        ok_(Entry.objects.filter(total_hours=8))
        ok_(Entry.objects.filter(total_hours=-8))
        ok_(Entry.objects.filter(total_hours=4))

        # whilst we're at it, check that negative hours are included in the
        # list_json
        url = reverse('dates.list_json')
        response = self.client.get(url)
        eq_(response.status_code, 200)
        ok_(response['Content-Type'].startswith('application/json'))
        struct = json.loads(response.content)
        entries = struct['aaData']
        eq_(len(entries), 3)
        totals = [x[4] for x in entries]
        eq_(sum(totals), 1 + 0.5 - 1)

    def test_list_json(self):
        url = reverse('dates.list_json')

        # start with no filtering
        peter = User.objects.create(
          username='peter',
          email='peter@mozilla.com',
          first_name='Peter',
          last_name='Bengtsson',
        )
        laura = User.objects.create(
          username='laura',
          email='laura@mozilla.com',
          first_name='Laura',
          last_name='van Der Thomson',
        )

        one_day = datetime.timedelta(days=1)
        monday = datetime.date(2018, 1, 1)  # I know this is a Monday
        tuesday = monday + one_day

        e0 = Entry.objects.create(
          user=peter,
          start=monday,
          end=monday,
          total_hours=None,
          details='Peter E0 Details'
        )
        e1 = Entry.objects.create(
          user=peter,
          start=tuesday,
          end=tuesday,
          total_hours=8,
          details='Peter E1 Details'
        )
        e2 = Entry.objects.create(
          user=laura,
          start=monday,
          end=tuesday,
          total_hours=8 + 4,
          details='Laura E2 Details'
        )

        response = self.client.get(url)
        eq_(response.status_code, 302)

        peter.set_password('secret')
        peter.save()
        assert self.client.login(username='peter', password='secret')

        response = self.client.get(url)
        eq_(response.status_code, 200)
        ok_(response['Content-Type'].startswith('application/json'))
        ok_(e0.details not in response.content)
        ok_(e1.details in response.content)
        ok_(e2.details not in response.content)  # because it's hidden
        struct = json.loads(response.content)
        entries = struct['aaData']

        def parse_date(s):
            d = datetime.datetime.strptime(s, '%Y-%m-%d')
            return d.date()

        for entry in entries:
            email = entry[0]
            first_name = entry[1]
            last_name = entry[2]
            add_date = parse_date(entry[3])
            total_days = entry[4]
            start_date = parse_date(entry[5])
            end_date = parse_date(entry[6])
            city = entry[7]
            country = entry[8]
            details = entry[9]
            #...
            if email == peter.email:
                user = peter
            elif email == laura.email:
                user = laura
            else:
                raise AssertionError("unknown email")
            eq_(first_name, user.first_name)
            eq_(last_name, user.last_name)
            eq_(add_date, datetime.datetime.utcnow().date())
            ok_(total_days in (1, 1.5))
            ok_(start_date in (monday, tuesday))
            eq_(end_date, tuesday)
            ok_(details == e1.details or details == '')

        # test profile stuff
        p = peter.get_profile()
        p.city = 'London'
        p.country = 'UK'
        p.save()

        p = laura.get_profile()
        p.city = 'Washington DC'
        p.country = 'USA'
        p.save()

        response = self.client.get(url)
        struct = json.loads(response.content)
        entries = struct['aaData']
        for entry in entries:
            city = entry[7]
            ok_(city in ('London', 'Washington DC'))

            country = entry[8]
            ok_(country in ('UK', 'USA'))

        filter = {'name': 'PeteR'}
        response = self.client.get(url, filter)
        ok_('Peter' in response.content)
        ok_('Laura' not in response.content)

        filter = {'name': 'bengtssON'}
        response = self.client.get(url, filter)
        ok_('Peter' in response.content)
        ok_('Laura' not in response.content)

        filter = {'name': peter.email.capitalize()}
        response = self.client.get(url, filter)
        ok_('Peter' in response.content)
        ok_('Laura' not in response.content)

        filter = {'name': 'FOO@bar.com'}
        response = self.client.get(url, filter)
        ok_('Peter' not in response.content)
        ok_('Laura' not in response.content)

        filter = {'name': 'thomson'}
        response = self.client.get(url, filter)
        ok_('Peter' not in response.content)
        ok_('Laura' in response.content)

        filter = {'name': 'VAN DER Thomson'}
        response = self.client.get(url, filter)
        ok_('Peter' not in response.content)
        ok_('Laura' in response.content)

        filter = {'name': 'Laura VAN DER Thomson'}
        response = self.client.get(url, filter)
        ok_('Peter' not in response.content)
        ok_('Laura' in response.content)

        filter = {'name': 'Peter bengtsson'}
        response = self.client.get(url, filter)
        ok_('Peter' in response.content)
        ok_('Laura' not in response.content)

        e2.add_date -= datetime.timedelta(days=7)
        e2.save()

        today = datetime.datetime.utcnow().date()
        filter = {'date_filed_to': today}
        response = self.client.get(url, filter)
        ok_('Peter' in response.content)
        ok_('Laura' in response.content)

        filter = {'date_filed_to': (today - one_day)}
        response = self.client.get(url, filter)
        ok_('Peter' not in response.content)
        ok_('Laura' in response.content)

        filter = {'date_filed_to': (today - one_day),
                  'date_filed_from': (today -
                                    datetime.timedelta(days=3)),
                  }
        response = self.client.get(url, filter)
        ok_('Peter' not in response.content)
        ok_('Laura' not in response.content)

        filter = {'date_filed_from': today}
        response = self.client.get(url, filter)
        ok_('Peter' in response.content)
        ok_('Laura' not in response.content)

        filter = {'date_filed_from': 'invalid junk'}
        response = self.client.get(url, filter)
        ok_('Peter' not in response.content)
        ok_('Laura' not in response.content)

        # remember, ...
        # Peter's event was tuesday only
        # Laura's event was monday till tuesday
        filter = {'date_from': tuesday}
        response = self.client.get(url, filter)
        ok_('Peter' in response.content)
        ok_('Laura' in response.content)

        filter = {'date_from': monday}
        response = self.client.get(url, filter)
        ok_('Peter' in response.content)
        ok_('Laura' in response.content)

        filter = {'date_from': tuesday + one_day}
        response = self.client.get(url, filter)
        ok_('Peter' not in response.content)
        ok_('Laura' not in response.content)

        filter = {'date_to': monday}
        response = self.client.get(url, filter)
        ok_('Peter' not in response.content)
        ok_('Laura' in response.content)

        filter = {'date_to': monday - one_day}
        response = self.client.get(url, filter)
        ok_('Peter' not in response.content)
        ok_('Laura' not in response.content)

        filter = {'date_to': tuesday}
        response = self.client.get(url, filter)
        ok_('Peter' in response.content)
        ok_('Laura' in response.content)

        filter = {'date_to': tuesday + one_day}
        response = self.client.get(url, filter)
        ok_('Peter' in response.content)
        ok_('Laura' in response.content)

        filter = {'country': 'UK'}
        response = self.client.get(url, filter)
        ok_('Peter' in response.content)
        ok_('Laura' not in response.content)

        filter = {'country': 'USA'}
        response = self.client.get(url, filter)
        ok_('Peter' not in response.content)
        ok_('Laura' in response.content)

        filter = {'country': 'AUS'}
        response = self.client.get(url, filter)
        ok_('Peter' not in response.content)
        ok_('Laura' not in response.content)

    def test_list(self):
        url = reverse('dates.list')
        response = self.client.get(url)
        eq_(response.status_code, 302)

        self._login()
        peter, = User.objects.all()
        response = self.client.get(url)
        eq_(response.status_code, 200)

        p = peter.get_profile()
        p.country = 'GB'
        p.save()

        # now create some entries
        laura = User.objects.create(
          username='laura',
          email='laura@mozilla.com',
          first_name='Laura',
          last_name='van Der Thomson',
        )

        p = laura.get_profile()
        p.country = 'US'
        p.save()

        one_day = datetime.timedelta(days=1)
        monday = datetime.date(2018, 1, 1)  # I know this is a Monday
        tuesday = monday + one_day

        Entry.objects.create(
          user=peter,
          start=monday,
          end=monday,
          total_hours=None,
          details='E0 Details'
        )
        Entry.objects.create(
          user=peter,
          start=tuesday,
          end=tuesday,
          total_hours=8,
          details='E1 Details'
        )
        Entry.objects.create(
          user=laura,
          start=monday,
          end=tuesday,
          total_hours=8 + 4,
          details='E2 Details'
        )

        response = self.client.get(url)
        eq_(response.status_code, 200)

        _options = (response.content
                    .split('name="country"')[1]
                    .split('</select>')[0])
        ok_('<option value="GB">' in _options)
        ok_('<option value="US">' in _options)

# Commented out till we decide what to do with the "On PTO right now feature"
#    def test_dashboard_on_pto_right_now(self):
#        """On the dashboard we can expect to see who is on PTO right now.
#        Expect that past and future entries don't appear.
#        It should also say how many days they have left.
#        """
#
#        User.objects.create_user(
#          'jill', 'jill@mozilla.com', password='secret'
#        )
#        assert self.client.login(username='jill', password='secret')
#        response = self.client.get('/')
#        eq_(response.status_code, 200)
#
#        bobby = User.objects.create_user(
#          'bobby', 'bobby@mozilla.com',
#        )
#        freddy = User.objects.create_user(
#          'freddy', 'freddy@mozilla.com',
#        )
#        dicky = User.objects.create_user(
#          'dicky', 'dicky@mozilla.com',
#        )
#        harry = User.objects.create_user(
#          'harry', 'harry@mozilla.com',
#        )
#
#        ok_('bobby' not in response.content)
#        ok_('freddy' not in response.content)
#        ok_('dicky' not in response.content)
#        ok_('harry' not in response.content)
#
#        today = datetime.date.today()
#
#        Entry.objects.create(
#          user=bobby,
#          total_hours=16,
#          start=today - datetime.timedelta(days=2),
#          end=today - datetime.timedelta(days=1),
#        )
#        response = self.client.get('/')
#        ok_('bobby' not in response.content)
#
#        Entry.objects.create(
#          user=freddy,
#          total_hours=16,
#          start=today - datetime.timedelta(days=1),
#          end=today,
#        )
#        response = self.client.get('/')
#        ok_('freddy' in response.content)
#
#        Entry.objects.create(
#          user=dicky,
#          total_hours=4,
#          start=today,
#          end=today,
#        )
#        response = self.client.get('/')
#        ok_('dicky' in response.content)
#
#        entry = Entry.objects.create(
#          user=harry,
#          total_hours=16,
#          start=today + datetime.timedelta(days=1),
#          end=today + datetime.timedelta(days=2),
#        )
#        response = self.client.get('/')
#        ok_('harry' not in response.content)
#
#        entry.start -= datetime.timedelta(days=1)
#        entry.end -= datetime.timedelta(days=1)
#        entry.save()
#        response = self.client.get('/')
#        ok_('harry' in response.content)
#
    def test_list_csv_link(self):
        self._login()
        # if you visit the default list, expect to find a link to the csv list
        # with the replicated query string
        list_url = reverse('dates.list')
        response = self.client.get(list_url, {
          'name': 'Peter',
        })
        assert response.status_code == 200
        url = reverse('dates.list_csv')
        ok_('href="%s?name=Peter"' % url in response.content)

    def test_list_csv(self):
        url = reverse('dates.list_csv')
        response = self.client.get(url)
        eq_(response.status_code, 302)

        self._login()
        today = datetime.date.today()
        data = {
          'date_from': today,
          'name': 'peter',
        }
        response = self.client.get(url)
        eq_(response.status_code, 200)
        eq_(response['Content-Type'], 'text/csv')
        reader = unicode_csv_reader(response.content.splitlines())

        head = False
        rows = 0
        by_ids = {}
        for row in reader:
            if not head:
                head = row
                continue
            rows += 1
            by_ids[int(row[0])] = row

        eq_(rows, 0)

        # now, add entries and test again
        peter, = User.objects.all()
        profile = peter.get_profile()
        profile.city = 'London'
        profile.country = 'GB'
        profile.start_date = datetime.date(2010, 4, 1)
        profile.save()

        delta = datetime.timedelta

        entry1 = Entry.objects.create(
          user=peter,
          start=today - delta(10),
          end=today - delta(10),
          total_hours=8
        )
        entry2 = Entry.objects.create(
          user=peter,
          start=today - delta(1),
          end=today,
          total_hours=16,
          details='Sailing',
        )
        entry3 = Entry.objects.create(
          user=peter,
          start=today,
          end=today + delta(1),
          total_hours=None
        )
        entry4 = Entry.objects.create(
          user=peter,
          start=today + delta(1),
          end=today + delta(2),
          total_hours=12
        )

        # also create a user and entries for him
        bob = User.objects.create(username='bob')
        entryB = Entry.objects.create(
          user=bob,
          start=today,
          end=today,
          total_hours=8
        )

        response = self.client.get(url, data)
        reader = unicode_csv_reader(response.content.splitlines())
        head = False
        rows = 0
        by_ids = {}
        for row in reader:
            if not head:
                head = row
                continue
            assert len(head) == len(row)
            rows += 1
            by_ids[int(row[0])] = row

        eq_(rows, 2)
        ok_(entry2.pk in by_ids.keys())
        ok_(entry4.pk in by_ids.keys())
        ok_(entryB.pk not in by_ids.keys())

        row = by_ids[entry2.pk]

        def fmt(d):
            return d.strftime('%Y-%m-%d')

        eq_(row[0], str(entry2.pk))
        eq_(row[1], peter.email)
        eq_(row[2], peter.first_name)
        eq_(row[3], peter.last_name)
        eq_(row[4], fmt(entry2.add_date))
        eq_(row[5], fmt(entry2.start))
        eq_(row[6], fmt(entry2.end))
        eq_(row[7], str(entry2.total_days))
        eq_(row[8], entry2.details)
        eq_(row[9], profile.city)
        eq_(row[10], profile.country)
        eq_(row[11], fmt(profile.start_date))

    def test_adding_a_single_day_of_zero(self):
        user = self._login()
        assert user
        monday = datetime.date(2018, 1, 1)  # I know this is a Monday
        wednesday = monday + datetime.timedelta(days=2)
        friday = monday + datetime.timedelta(days=4)
        entry = Entry.objects.create(
          user=user,
          start=monday,
          end=friday,
          total_hours=settings.WORK_DAY * 5
        )
        self._create_entry_hours(entry)

        # now begin to change your mind by adding one day of zero on top
        url = reverse('dates.notify')
        data = {'start': wednesday, 'end': wednesday,
                'details': 'Change of minds'}
        response = self.client.post(url, data)
        eq_(response.status_code, 302)
        entry0 = Entry.objects.get(details=data['details'])
        url = reverse('dates.hours', args=[entry0.pk])
        response = self.client.get(url)
        assert response.status_code == 200
        ok_('Already logged 8 hours on this day' in response.content)

        data = {
          wednesday.strftime('d-%Y%m%d'): '0'
        }
        response = self.client.post(url, data)
        eq_(response.status_code, 302)

        sum_hours = sum(x.total_hours for x in Entry.objects.all())
        eq_(sum_hours, settings.WORK_DAY * 5 + 0 + -8)

    def test_get_taken_info(self):
        user = User.objects.create(username='bob')
        from pto.apps.dates.views import get_taken_info

        def function():
            return get_taken_info(user)

        result = function()
        eq_(result['taken'], '0 days')
        ok_(not result.get('unrecognized_country'))
        ok_(not result.get('country_total'))

        profile = user.get_profile()
        profile.country = 'US'
        profile.save()
        result = function()
        ok_(not result.get('unrecognized_country'))
        ok_(result.get('country_totals'))
        ok_(result.get('country'), 'US')

        profile.country = 'New Zealand'
        profile.save()
        result = function()
        ok_(result.get('unrecognized_country'))
        ok_(not result.get('country_totals'))
        ok_(result.get('country'), 'New Zealand')


        date = datetime.date(_THIS_YEAR, 11, 23)
        entry = Entry.objects.create(
          user=user,
          start=date,
          end=date,
          total_hours=settings.WORK_DAY,
        )
        self._create_entry_hours(entry)


        result = function()
        eq_(result['taken'], '1 day')

        entry.total_hours = settings.WORK_DAY / 2
        entry.save()
        result = function()
        eq_(result['taken'], '%s hours' % (settings.WORK_DAY / 2))

        one_week = datetime.timedelta(days=7)
        entry = Entry.objects.create(
          user=user,
          start=date + one_week,
          end=date + one_week,
          total_hours=settings.WORK_DAY,
        )
        self._create_entry_hours(entry)

        result = function()
        eq_(result['taken'], '1.5 days')

        entry = Entry.objects.create(
          user=user,
          start=date + one_week * 2,
          end=date + one_week * 2,
          total_hours=settings.WORK_DAY / 2,
        )
        self._create_entry_hours(entry, 4)

        result = function()
        eq_(result['taken'], '2 days')

        entry = Entry.objects.create(
          user=user,
          start=date + one_week * 3,
          end=date + one_week * 5,
          total_hours=settings.WORK_DAY * 14,
        )
        self._create_entry_hours(entry)

        result = function()
        eq_(result['taken'], '16 days')

    def test_people_in_calendar(self):

        mike = User.objects.create(username='mike')
        laura = User.objects.create(username='laura')
        peter = User.objects.create(username='peter')
        lars = User.objects.create(username='lars')
        brandon = User.objects.create(username='brandon')
        chofman = User.objects.create(username='chofman')
        axel = User.objects.create(username='axel')
        stas = User.objects.create(username='stas')

        self._make_manager(laura, mike)
        self._make_manager(peter, laura)
        self._make_manager(lars, laura)
        self._make_manager(brandon, laura)
        self._make_manager(axel, chofman)
        self._make_manager(stas, chofman)

        # make everyone have an entry
        _all = mike, laura, peter, lars, brandon, chofman, axel, stas
        today = datetime.date(2011, 11, 23)  # a Wednesday
        for user in _all:
            entry = Entry.objects.create(
              user=user,
              start=today,
              end=today,
              total_hours=settings.WORK_DAY
            )
            Hours.objects.create(
              entry=entry,
              date=today,
              hours=settings.WORK_DAY
            )

        self._login(peter)
        url = reverse('dates.calendar_events')
        _start = today - datetime.timedelta(days=1)
        _end = today + datetime.timedelta(days=1)
        data = {
          'start': time.mktime(_start.timetuple()),
          'end': time.mktime(_end.timetuple())
        }
        response = self.client.get(url, data)
        eq_(response.status_code, 200)
        struct = json.loads(response.content)
        names = [x['name'] for x in struct['colors']]
        assert 'Me myself and I' in names
        # for peter, by default, it should be manager plus "siblings"
        ok_('laura' in names)
        ok_('lars' in names)
        ok_('brandon' in names)
        ok_('chofman' not in names)
        ok_('axel' not in names)
        ok_('stas' not in names)

        # suppose I don't want to follow brandon
        BlacklistedUser.objects.create(
          observer=peter,
          observable=brandon
        )
        response = self.client.get(url, data)
        eq_(response.status_code, 200)
        struct = json.loads(response.content)
        names = [x['name'] for x in struct['colors']]
        assert 'Me myself and I' in names
        # for peter, by default, it should be manager plus "siblings"
        ok_('laura' in names)
        ok_('lars' in names)
        ok_('brandon' not in names)
        ok_('chofman' not in names)
        ok_('axel' not in names)
        ok_('stas' not in names)

        # But I explicitely now want to follow axel
        FollowingUser.objects.create(
          follower=peter,
          following=axel
        )

        response = self.client.get(url, data)
        eq_(response.status_code, 200)
        struct = json.loads(response.content)
        names = [x['name'] for x in struct['colors']]
        assert 'Me myself and I' in names
        # for peter, by default, it should be manager plus "siblings"
        ok_('laura' in names)
        ok_('lars' in names)
        ok_('brandon' not in names)
        ok_('chofman' not in names)
        ok_('axel' in names)
        ok_('stas' not in names)

    def test_manage_following(self):
        todd = User.objects.create(username='todd')
        mike = User.objects.create(username='mike')
        ben = User.objects.create(username='ben')
        laura = User.objects.create(username='laura')
        peter = User.objects.create(username='peter')
        lars = User.objects.create(username='lars')
        chofman = User.objects.create(username='chofman')
        axel = User.objects.create(username='axel')
        stas = User.objects.create(username='stas')

        self._make_manager(mike, todd)
        self._make_manager(ben, todd)
        self._make_manager(laura, mike)
        self._make_manager(peter, laura)
        self._make_manager(lars, laura)
        self._make_manager(axel, chofman)
        self._make_manager(stas, chofman)

        url = reverse('dates.following')
        response = self.client.get(url)
        eq_(response.status_code, 302)

        assert self._login(mike)

        response = self.client.get(url)
        eq_(response.status_code, 200)
        html = response.content.split('id="observed"')[1].split('</table>')[0]
        ok_('todd' in html)
        ok_('your manager' in html)
        ok_('ben' in html)
        ok_('teammate' in html)
        ok_('laura' in html)
        ok_('direct manager of' in html)
        ok_('lars' in html)
        ok_('indirect manager of' in html)
        ok_('peter' in html)
        ok_('indirect manager of' in html)

        # fire off an AJAX post to unfollow 'peter'
        unfollow_url = reverse('dates.save_unfollowing')
        response = self.client.post(unfollow_url, {'remove': 'xxx'})
        eq_(response.status_code, 400)

        response = self.client.post(unfollow_url, {'remove': str(peter.pk)})
        eq_(response.status_code, 200)
        struct = json.loads(response.content)
        eq_(struct['id'], peter.pk)
        eq_(struct['name'], peter.username)

        # add someone outside the default circles
        follow_url = reverse('dates.save_following')
        response = self.client.post(follow_url)
        eq_(response.status_code, 400)

        axel.first_name = 'Axel'
        axel.email = 'axel@mozilla.com'
        axel.save()

        response = self.client.post(follow_url, {
          'search': 'Axel Hecht <axel@mx...ozilla.com>',
        })
        eq_(response.status_code, 400)

        response = self.client.post(follow_url, {
          'search': 'Axel Hecht <axel@muzille.com>',
        })
        eq_(response.status_code, 400)

        response = self.client.post(follow_url, {
          'search': 'Axel Hecht <axel@mozilla.com>',
        })
        eq_(response.status_code, 200)
        struct = json.loads(response.content)
        eq_(struct['reason'], 'curious')
        eq_(struct['id'], axel.pk)
        eq_(struct['name'], axel.first_name)
        assert FollowingUser.objects.get(follower=mike, following=axel)

        response = self.client.post(unfollow_url, {'remove': axel.pk})
        eq_(response.status_code, 200)
        struct = json.loads(response.content)
        eq_(struct, {})
        assert not (FollowingUser.objects
                    .filter(follower=mike, following=axel)
                    .exists())

        response = self.client.post(follow_url, {
          'search': str(stas.pk * 999),
        })
        eq_(response.status_code, 400)

        response = self.client.post(follow_url, {
          'search': str(stas.pk),
        })
        eq_(response.status_code, 400)

        stas.email = 'Stanislav@mozilla.com'
        stas.save()
        response = self.client.post(follow_url, {
          'search': str(stas.pk),
        })
        eq_(response.status_code, 200)
        struct = json.loads(response.content)
        eq_(struct['reason'], 'curious')
        eq_(struct['id'], stas.pk)
        eq_(struct['name'], stas.username)

        chofman.first_name = 'Chris'
        chofman.last_name = 'Hofman'
        chofman.email = 'chofman@mozilla.com'
        chofman.save()

        ldap.open = Mock('ldap.open')
        ldap.open.mock_returns = Mock('ldap_connection')
        ldap.set_option = Mock(return_value=None)
        fake_user = [
          ('mail=mortal@mozilla.com,o=com,dc=mozilla',
           {'cn': ['Chris Hofman'],
            'givenName': ['Chris'],
            'mail': [chofman.email],
            'sn': ['Hofman'],
            'uid': ['chofman']
            }),
          ('mail=mortal@mozilla.com,o=com,dc=mozilla',
           {'cn': ['Unheard Of'],
            'givenName': ['Unheard'],
            'mail': ['unheard@of.com'],
            'sn': ['Of'],
            'uid': ['xxx']
            })
        ]

        _key = ('(|(mail=chris ho*)(givenName=chris ho*)'
                '(sn=chris ho*)(cn=chris ho*))')
        _key = ldap_lookup.account_wrap_search_filter(_key)
        ldap.initialize = Mock(return_value=MockLDAP({
          _key: fake_user,
          }
        ))

        response = self.client.post(follow_url, {
          'search': 'chris ho',
        })
        eq_(response.status_code, 200)
        struct = json.loads(response.content)
        eq_(struct['reason'], 'curious')
        eq_(struct['id'], chofman.pk)
        eq_(struct['name'], 'Chris Hofman')

        response = self.client.get(url)
        eq_(response.status_code, 200)
        html = response.content.split('id="observed"')[1].split('</table>')[0]
        ok_('Chris Hofman' in html)
        ok_('curious' in html)
        ok_('peter' not in html)

        html = (response.content
                .split('id="not-observed"')[1]
                .split('</table>')[0])
        ok_('peter' in html)
        ok_('Axel' not in html)  # curious people unfollowed aren't blacklisted

    def test_calendar_vcal(self):
        mike = User.objects.create(username='mike')
        uk = UserKey.objects.create(user=mike)
        url = reverse('dates.calendar_vcal', args=[uk.key])
        response = self.client.get(url)
        eq_(response.status_code, 200)
        eq_(response['Content-Type'], 'text/calendar;charset=utf-8')
        eq_(response['Content-Disposition'],
                     'inline; filename="%s.ics"' % (uk.key,))
        ok_(response.content.startswith('BEGIN:VCALENDAR'))
        ok_(response.content.strip().endswith('END:VCALENDAR'))

        # add some events
        today = datetime.date.today()
        yesterday = today - datetime.timedelta(days=1)
        lastweek = today - datetime.timedelta(days=7)
        nextweek = today + datetime.timedelta(days=7)
        Entry.objects.create(
          user=mike,
          start=lastweek,
          end=lastweek,
          total_hours=settings.WORK_DAY / 2,
          details='Sensitive'
        )

        Entry.objects.create(
          user=mike,
          start=today - datetime.timedelta(days=1),
          end=today,
          total_hours=settings.WORK_DAY * 2,
          details='Also sensitive'
        )

        Entry.objects.create(
          user=mike,
          start=nextweek,
          end=nextweek,
          total_hours=settings.WORK_DAY,
          details='Super sensitive'
        )

        response = self.client.get(url)
        eq_(response.status_code, 200)
        eq_(response.content.count('BEGIN:VEVENT'), 2)
        eq_(response.content.count('Log in to see the details'), 2)
        ok_(yesterday.strftime('DTSTART;VALUE=DATE:%Y%m%d')
            in response.content)
        ok_(today.strftime('DTEND;VALUE=DATE:%Y%m%d')
            in response.content)
        ok_(nextweek.strftime('DTSTART;VALUE=DATE:%Y%m%d')
            in response.content)
        ok_(nextweek.strftime('DTEND;VALUE=DATE:%Y%m%d')
            in response.content)
        ok_(-1 < response.content.find('SUMMARY:16 hours')
               < response.content.find('SUMMARY:8 hours'))
        ok_('sensitive' not in response.content.lower())

    def test_calendar_vcal_following(self):
        mike = User.objects.create(username='mike')
        axel = User.objects.create(username='axel')
        FollowingUser.objects.create(
          follower=mike,
          following=axel,
        )
        uk = UserKey.objects.create(user=mike)
        url = reverse('dates.calendar_vcal', args=[uk.key])
        response = self.client.get(url)
        eq_(response.status_code, 200)

        today = datetime.date.today()
        yesterday = today - datetime.timedelta(days=1)
        Entry.objects.create(
          user=axel,
          start=yesterday,
          end=today,
          total_hours=settings.WORK_DAY * 2,
          details='Sensitive'
        )

        response = self.client.get(url)
        eq_(response.status_code, 200)
        ok_('SUMMARY:axel - 16 hours' in response.content)

        axel.first_name = 'Axel'
        axel.last_name = 'Hecht'
        axel.email = 'axel@localhost.com'
        axel.save()

        response = self.client.get(url)
        eq_(response.status_code, 200)
        ok_('SUMMARY:Axel Hecht - 16 hours' in response.content)

        uk.delete()
        response = self.client.get(url)
        eq_(response.status_code, 200)
        ok_('Calendar expired' in response.content)

    def test_calendar_vcal_expired(self):
        key_length = UserKey.KEY_LENGTH
        url = reverse('dates.calendar_vcal', args=['x' * key_length])
        response = self.client.get(url)
        eq_(response.status_code, 200)
        eq_(response['Content-Type'], 'text/calendar;charset=utf-8')
        eq_(response['Content-Disposition'],
                     'inline; filename="%s.ics"' %
                      ('x' * key_length,))
        ok_('Calendar expired' in response.content)

    def test_reset_calendar_url(self):
        url = reverse('dates.reset_calendar_url')
        response = self.client.get(url)
        eq_(response.status_code, 302)
        ok_(settings.LOGIN_URL in response['Location'])

        mike = User.objects.create(username='mike')
        UserKey.objects.create(user=mike)
        self._login(mike)

        response = self.client.get(url)
        eq_(response.status_code, 302)
        ok_(not UserKey.objects.filter(user=mike).count())

# Commented out till we decide what to do with the "On PTO right now feature"
#    def test_loading_all_on_pto(self):
#        from string import uppercase
#        today = datetime.date.today()
#        for letter in list(uppercase):
#            username = '%sUSERNAME' % letter
#            entry = Entry.objects.create(
#              user=User.objects.create(username=username),
#              start=today,
#              end=today + datetime.timedelta(days=random.randint(0, 10)),
#              total_hours=settings.WORK_DAY,
#            )
#        last_username = username
#
#        self._login()
#        url = reverse('dates.home')
#        response = self.client.get(url)
#        ok_(last_username not in response.content)
#
#        response = self.client.get(url, {'all-rightnow': ''})
#        ok_(last_username in response.content)

    def test_cancel_notify(self):
        user = self._login()
        today = datetime.date.today()
        entry = Entry.objects.create(
          user=user,
          start=today,
          end=today,
          details='Stuck',
          total_hours=settings.WORK_DAY,
        )
        Hours.objects.create(
          entry=entry,
          date=entry.start,
          hours=entry.total_hours
        )

        Entry.objects.create(
          user=user,
          start=today,
          end=today,
          details='Incomplete',
          total_hours=None
        )

        url = reverse('dates.cancel_notify')
        response = self.client.get(url)
        eq_(response.status_code, 302)
        eq_(urlparse(response['Location']).path, reverse('dates.home'))

        eq_(Entry.objects.filter(user=user).count(), 1)
        ok_(Entry.objects.filter(user=user, details='Stuck'))

    def test_recently_created_flash_message(self):
        user = self._login()
        today = datetime.date(2011, 11, 23)  # a Wednesday
        entry = Entry.objects.create(
          user=user,
          start=today,
          end=today,
          details='This is a long message that ends on the word XYZ',
        )
        url = reverse('dates.hours', args=[entry.pk])
        data = {}
        data[today.strftime('d-%Y%m%d')] = settings.WORK_DAY
        response = self.client.post(url, data)
        eq_(response.status_code, 302)
        assert Hours.objects.filter(entry=entry)
        entry = Entry.objects.get(pk=entry.pk)
        assert entry.total_hours

        # visit the home page and expect there to be a flash message there
        response = self.client.get(reverse('dates.home'))
        ok_('class="flash"' in response.content)
        from pto.apps.dates.views import make_entry_title
        ok_(make_entry_title(entry, entry.user)[:10] in response.content)

        # do it again
        response = self.client.get(reverse('dates.home'))
        ok_('class="flash"' not in response.content)

    def test_0_hours_on_top(self):
        user = self._login()
        today = datetime.date(2011, 11, 23)  # a Wednesday
        entry = Entry.objects.create(
          user=user,
          start=today,
          end=today + datetime.timedelta(days=2),
        )
        url = reverse('dates.hours', args=[entry.pk])
        response = self.client.get(url)
        eq_(response.content.count('value="0"'), 0)
        eq_(response.content.count('value="8"'), 3)
        eq_(response.content.count('value="4"'), 3)
        eq_(response.content.count('value="-1"'), 3)

        # now pretend we have had a slot already on the thursday
        entry2 = Entry.objects.create(
          user=user,
          start=today + datetime.timedelta(days=1),
          end=today + datetime.timedelta(days=1),
          total_hours=settings.WORK_DAY,
        )
        Hours.objects.create(
          entry=entry2,
          date=today + datetime.timedelta(days=1),
          hours=settings.WORK_DAY,
        )
        url = reverse('dates.hours', args=[entry.pk])
        response = self.client.get(url)
        eq_(response.content.count('value="0"'), 1)
        eq_(response.content.count('value="8"'), 3)
        eq_(response.content.count('value="4"'), 3)
        eq_(response.content.count('value="-1"'), 3)

        # let's submit that!
        data = {}
        data[today.strftime('d-%Y%m%d')] = '8'
        data[(today + datetime.timedelta(days=1)).strftime('d-%Y%m%d')] = '0'
        data[(today + datetime.timedelta(days=2)).strftime('d-%Y%m%d')] = '8'

        response = self.client.post(url, data)
        eq_(response.status_code, 302)

        sum_totals = sum_hours = 0
        for entry in Entry.objects.filter(user=user):
            sum_totals += entry.total_hours
            for h in Hours.objects.filter(entry=entry):
                sum_hours += h.hours

        # Why 16?
        # first time, a single 8
        # second time, 8 + 0 + 8
        # that's interpreted as an edit on top, thus:
        #   Total = 8 + 8 + -8 = 16
        ok_(sum_totals == sum_hours == 16)

        url = reverse('dates.list_json')
        response = self.client.get(url)
        eq_(response.status_code, 200)
        struct = json.loads(response.content)
        entries = struct['aaData']

        days = [x[4] for x in entries]
        details = [x[-1] for x in entries]
        eq_(sum(days), 2)
        ok_('*automatic edit*' in details)
        eq_(days, [2, 1, -1])

    def test_details_withheld(self):

        todd = User.objects.create(username='todd')
        mike = User.objects.create(username='mike')
        ben = User.objects.create(username='ben')
        laura = User.objects.create(username='laura')
        peter = User.objects.create(username='peter')
        lars = User.objects.create(username='lars')
        chofman = User.objects.create(username='chofman')
        axel = User.objects.create(username='axel')
        stas = User.objects.create(username='stas')

        today = datetime.date.today()
        all_details = set()
        for u in User.objects.all():
            u.set_password('secret')
            u.save()
            entry = Entry.objects.create(
              user=u,
              start=today,
              end=today,
              total_hours=settings.WORK_DAY,
              details="%s's details" % u.username
            )
            Hours.objects.create(
              entry=entry,
              date=today,
              hours=settings.WORK_DAY,
            )
            all_details.add("%s's details" % u.username)

        admin = User.objects.create(
          username='admin',
          is_superuser=True,
          is_staff=True
        )
        admin.set_password('secret')
        admin.save()

        self._make_manager(mike, todd)
        self._make_manager(ben, todd)
        self._make_manager(laura, mike)
        self._make_manager(peter, laura)
        self._make_manager(lars, laura)
        self._make_manager(axel, chofman)

        """
        Org chart:

          * todd
            * ben
            * mike
              * laura
                * peter
              * will
          * chofman
            * axel
        """
        ## Test the list JSON
        url = reverse('dates.list_json')

        # as mike
        assert self.client.login(username='mike', password='secret')
        response = self.client.get(url)
        assert response.status_code == 200
        struct = json.loads(response.content)
        data = struct['aaData']
        details = set(x[-1] for x in data if x[-1])
        eq_(details, set(["laura's details", "mike's details"]))

        # as todd
        assert self.client.login(username='todd', password='secret')
        response = self.client.get(url)
        assert response.status_code == 200
        struct = json.loads(response.content)
        data = struct['aaData']
        details = set(x[-1] for x in data if x[-1])
        eq_(details, set(["todd's details", "mike's details", "ben's details"]))

        # as peter
        assert self.client.login(username='peter', password='secret')
        response = self.client.get(url)
        assert response.status_code == 200
        struct = json.loads(response.content)
        data = struct['aaData']
        details = set(x[-1] for x in data if x[-1])
        eq_(details, set(["peter's details"]))

        # as admin
        assert self.client.login(username='admin', password='secret')
        response = self.client.get(url)
        assert response.status_code == 200
        struct = json.loads(response.content)
        data = struct['aaData']
        details = set(x[-1] for x in data if x[-1])
        eq_(details, all_details)

        ## Test the calendar JSON
        url = reverse('dates.calendar_events')
        data = {
          'start': time.mktime(today.timetuple()),
          'end': time.mktime((today + datetime.timedelta(days=1)).timetuple())
        }

        # as mike
        assert self.client.login(username='mike', password='secret')
        response = self.client.get(url, data)
        assert response.status_code == 200
        struct = json.loads(response.content)['events']
        details = set([x['title'].split(',')[1].strip() for x in struct
                       if x['title'].count(',')])
        eq_(details, set(["laura's details", "mike's details"]))

        # as todd
        assert self.client.login(username='todd', password='secret')
        response = self.client.get(url, data)
        assert response.status_code == 200
        struct = json.loads(response.content)['events']
        details = set([x['title'].split(',')[1].strip() for x in struct
                       if x['title'].count(',')])
        eq_(details, set(["ben's details", "mike's details", "todd's details"]))

        # as peter
        assert self.client.login(username='peter', password='secret')
        response = self.client.get(url, data)
        assert response.status_code == 200
        struct = json.loads(response.content)['events']
        details = set([x['title'].split(',')[1].strip() for x in struct
                       if x['title'].count(',')])
        eq_(details, set(["peter's details"]))

        # note, admin isn't following anybody and doesn't have entries
        assert self.client.login(username='admin', password='secret')
        response = self.client.get(url, data)
        assert response.status_code == 200
        struct = json.loads(response.content)['events']
        details = set([x['title'].split(',')[1].strip() for x in struct
                       if x['title'].count(',')])
        eq_(details, set([]))
