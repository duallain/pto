# ***** BEGIN LICENSE BLOCK *****
# Version: MPL 1.1/GPL 2.0/LGPL 2.1
#
# The contents of this file are subject to the Mozilla Public License Version
# 1.1 (the "License"); you may not use this file except in compliance with
# the License. You may obtain a copy of the License at
# http://www.mozilla.org/MPL/
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License
# for the specific language governing rights and limitations under the
# License.
#
# The Original Code is Mozilla Sheriff Duty.
#
# The Initial Developer of the Original Code is Mozilla Corporation.
# Portions created by the Initial Developer are Copyright (C) 2011
# the Initial Developer. All Rights Reserved.
#
# Contributor(s):
#
# Alternatively, the contents of this file may be used under the terms of
# either the GNU General Public License Version 2 or later (the "GPL"), or
# the GNU Lesser General Public License Version 2.1 or later (the "LGPL"),
# in which case the provisions of the GPL or the LGPL are applicable instead
# of those above. If you wish to allow use of your version of this file only
# under the terms of either the GPL or the LGPL, and not to allow others to
# use your version of this file under the terms of the MPL, indicate your
# decision by deleting the provisions above and replace them with the notice
# and other provisions required by the GPL or the LGPL. If you do not delete
# the provisions above, a recipient may use your version of this file under
# the terms of any one of the MPL, the GPL or the LGPL.
#
# ***** END LICENSE BLOCK *****

import datetime
from urllib import urlencode
from collections import defaultdict
import jingo
from django import http
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.core.urlresolvers import reverse
from django.conf import settings
from django.shortcuts import redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Q
from django.template import Context, loader
from django.core.mail import get_connection, EmailMessage
import vobject
from models import Entry, Hours
from users.models import UserProfile
from users.utils import ldap_lookup
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from .utils import parse_datetime, DatetimeParseError
from .utils.pto_left import get_hours_left
import utils
import forms
from .decorators import json_view


def valid_email(value):
    try:
        validate_email(value)
        return True
    except ValidationError:
        return False


@login_required
def home(request):  # aka dashboard
    data = {}
    data['mobile'] = request.MOBILE  # thank you django-mobility (see settings)
    if data['mobile']:
        # unless an explicit cookie it set, redirect to /mobile/
        if not request.COOKIES.get('no-mobile', False):
            return redirect(reverse('mobile.home'))

    data['page_title'] = "Dashboard"
    profile = request.user.get_profile()
    if profile and profile.country in ('GB', 'FR', 'DE'):
        first_day = 1  # 1=Monday
    else:
        first_day = 0  # default to 0=Sunday
    data['first_day'] = first_day

    right_nows, right_now_users = get_right_nows()
    data['right_nows'] = right_nows
    data['right_now_users'] = right_now_users
    data['left'] = get_left(profile)

    return jingo.render(request, 'dates/home.html', data)

def get_right_nows():
    right_now_users = []
    right_nows = defaultdict(list)
    _today = datetime.date.today()

    for entry in (Entry.objects
                  .filter(start__lte=_today,
                          end__gte=_today,
                          total_hours__gte=0)
                  .order_by('user__first_name',
                            'user__last_name',
                            'user__username')):
        if entry.user not in right_now_users:
            right_now_users.append(entry.user)
        left = (entry.end - _today).days + 1
        right_nows[entry.user].append((left, entry))

    return right_nows, right_now_users

def get_upcomings(max_days=14):
    users = []
    upcoming = defaultdict(list)
    today = datetime.date.today()
    max_future = today + datetime.timedelta(days=max_days)

    for entry in (Entry.objects
                  .filter(start__gt=today,
                          start__lt=max_future,
                          total_hours__gte=0)
                  .order_by('user__first_name',
                            'user__last_name',
                            'user__username')):
        if entry.user not in users:
            users.append(entry.user)
        days = (entry.start - today).days + 1
        upcoming[entry.user].append((days, entry))

    return upcoming, users

def get_left(profile):
    if profile.start_date and profile.country:
        diff = datetime.date.today() - profile.start_date
        if diff.days >= 365:
            hours = get_hours_left(profile)
            days = hours / 8
            if days == 1:
                days = '1 day'
            else:
                days = '%d days' % days
            remainder = hours % 8
            if remainder:
                days += ' and %d hours' % remainder
            return {'hours': hours, 'days': days}
        else:
            return {'less_than_a_year': diff.days}
    elif profile.start_date or profile.country:
        if not profile.start_date:
            return {'missing': ['start date']}
        else:
            return {'missing': ['country']}
    else:
        return {'missing': ['country', 'start date']}


@json_view
def calendar_events(request):
    if not request.user.is_authenticated():
        return http.HttpResponseForbidden('Must be logged in')

    if not request.GET.get('start'):
        return http.HttpResponseBadRequest('Argument start missing')
    if not request.GET.get('end'):
        return http.HttpResponseBadRequest('Argument end missing')

    try:
        start = parse_datetime(request.GET['start'])
    except DatetimeParseError:
        return http.HttpResponseBadRequest('Invalid start')

    try:
        end = parse_datetime(request.GET['end'])
    except DatetimeParseError:
        return http.HttpResponseBadRequest('Invalid end')

    entries = []

    def make_title(entry):
        if entry.user != request.user:
            if entry.user.first_name:
                title = '%s %s - ' % (entry.user.first_name,
                                      entry.user.last_name)
            else:
                title = '%s - ' % entry.user.username
        else:
            title = ''
        days = (entry.end - entry.start).days + 1
        if days > 1:
            title += '%s days' % days
            if Hours.objects.filter(entry=entry, birthday=True).exists():
                title += ' (includes birthday)'
        elif (days == 1 and entry.total_hours == 0 and
            Hours.objects.filter(entry=entry, birthday=True)):
            title += 'Birthday!'
        else:
            title += '%s hours' % entry.total_hours
        if entry.details:
            if days == 1:
                max_length = 20
            else:
                max_length = 40
            title += ', '
            if len(entry.details) > max_length:
                title += entry.details[:max_length] + '...'
            else:
                title += entry.details
        return title

    COLORS = ("#EAA228", "#c5b47f", "#579575", "#839557", "#958c12",
              "#953579", "#4b5de4", "#d8b83f", "#ff5800", "#0085cc",
              "#c747a3", "#cddf54", "#FBD178", "#26B4E3", "#bd70c7")
    _colors = list(COLORS)
    user_ids = [request.user.pk]
    colors = {}
    colors[request.user.pk] = None
    for minion in get_minions(request.user, max_depth=2):
        user_ids.append(minion.pk)
        colors[minion.pk] = _colors.pop()
    for entry in (Entry.objects
                   .filter(user__in=user_ids,
                           total_hours__gte=0,
                           total_hours__isnull=False)
                   .select_related('user')
                   .exclude(Q(end__lt=start) | Q(start__gt=end))):
        entries.append({
          'id': entry.pk,
          'title': make_title(entry),
          'start': entry.start.strftime('%Y-%m-%d'),
          'end': entry.end.strftime('%Y-%m-%d'),
          'color': colors[entry.user.pk],
        })

    return entries


def get_minions(user, depth=1, max_depth=2):
    minions = []
    for minion in (UserProfile.objects.filter(manager_user=user)
                   .select_related('manager_user')
                   .order_by('manager_user')):
        minions.append(minion.user)

        if depth < max_depth:
            minions.extend(get_minions(minion.user,
                                       depth=depth + 1,
                                       max_depth=max_depth))
    return minions


@transaction.commit_on_success
@login_required
def notify(request):
    data = {}
    data['page_title'] = "Notify about new PTO"
    if request.method == 'POST':
        form = forms.AddForm(request.user, data=request.POST)
        if form.is_valid():
            start = form.cleaned_data['start']
            end = form.cleaned_data['end']
            details = form.cleaned_data['details'].strip()
            notify = form.cleaned_data['notify']
            entry = Entry.objects.create(
              user=request.user,
              start=start,
              end=end,
              details=details,
            )
            clean_unfinished_entries(entry)

            messages.info(request, 'Entry added, now specify hours')
            url = reverse('dates.hours', args=[entry.pk])
            request.session['notify_extra'] = notify
            return redirect(url)
    else:
        initial = {}
        if request.GET.get('start'):
            try:
                initial['start'] = parse_datetime(request.GET['start'])
            except DatetimeParseError:
                pass
        if request.GET.get('end'):
            try:
                initial['end'] = parse_datetime(request.GET['end'])
            except DatetimeParseError:
                pass
        form = forms.AddForm(request.user, initial=initial)

    profile = request.user.get_profile()
    manager = None
    if profile and profile.manager:
        manager = ldap_lookup.fetch_user_details(profile.manager)
    data['hr_managers'] = [ldap_lookup.fetch_user_details(x)
                           for x in settings.HR_MANAGERS]

    data['manager'] = manager
    data['all_managers'] = [x for x in data['hr_managers']
                            if x]
    if manager:
        data['all_managers'].append(manager)
    data['form'] = form
    return jingo.render(request, 'dates/notify.html', data)


def clean_unfinished_entries(good_entry):
    # delete all entries that don't have total_hours and touch on the
    # same dates as this good one
    bad_entries = (Entry.objects
                   .filter(user=good_entry.user,
                           total_hours__isnull=True)
                   .exclude(pk=good_entry.pk))
    for entry in bad_entries:
        entry.delete()


@transaction.commit_on_success
@login_required
def hours(request, pk):
    data = {}
    entry = get_object_or_404(Entry, pk=pk)
    if entry.user != request.user:
        if not (request.user.is_staff or request.user.is_superuser):
            return http.HttpResponseForbidden('insufficient access')
    if request.method == 'POST':
        form = forms.HoursForm(entry, data=request.POST)
        if form.is_valid():
            total_hours, is_edit = save_entry_hours(entry, form)

            extra_users = request.session.get('notify_extra', '')
            extra_users = [x.strip() for x
                           in extra_users.split(';')
                           if x.strip()]

            success, email_addresses = send_email_notification(
              entry,
              extra_users,
              is_edit=is_edit,
            )
            assert success

            messages.info(request,
              '%s hours of PTO logged.' % total_hours
            )
            url = reverse('dates.emails_sent', args=[entry.pk])
            url += '?' + urlencode({'e': email_addresses}, True)
            return redirect(url)
    else:
        initial = {}
        for date in utils.get_weekday_dates(entry.start, entry.end):
            try:
                #hours_ = Hours.objects.get(entry=entry, date=date)
                hours_ = Hours.objects.get(date=date, entry__user=entry.user)
                initial[date.strftime('d-%Y%m%d')] = hours_.hours
            except Hours.DoesNotExist:
                initial[date.strftime('d-%Y%m%d')] = settings.WORK_DAY

        #print initial
        form = forms.HoursForm(entry, initial=initial)
    data['form'] = form

    if entry.total_hours:
        data['total_hours'] = entry.total_hours
    else:
        total_hours = 0
        for date in utils.get_weekday_dates(entry.start, entry.end):
            try:
                hours_ = Hours.objects.get(entry=entry, date=date)
                total_hours += hours_.hours
            except Hours.DoesNotExist:
                total_hours += settings.WORK_DAY
        data['total_hours'] = total_hours

    notify = request.session.get('notify_extra', [])
    data['notify'] = notify

    return jingo.render(request, 'dates/hours.html', data)

def save_entry_hours(entry, form):
    assert form.is_valid()

    total_hours = 0
    for date in utils.get_weekday_dates(entry.start, entry.end):
        hours = int(form.cleaned_data[date.strftime('d-%Y%m%d')])
        birthday = False
        if hours == -1:
            birthday = True
            hours = 0
        assert hours >= 0 and hours <= settings.WORK_DAY, hours
        try:
            hours_ = Hours.objects.get(entry__user=entry.user,
                                       date=date)
            if hours_.hours:
                # this nullifies the previous entry on this date
                reverse_entry = Entry.objects.create(
                  user=hours_.entry.user,
                  start=date,
                  end=date,
                  details=hours_.entry.details,
                  total_hours=hours_.hours * -1,
                )
                Hours.objects.create(
                  entry=reverse_entry,
                  hours=hours_.hours * -1,
                  date=date,
                )
            #hours_.hours = hours  # nasty stuff!
            #hours_.birthday = birthday
            #hours_.save()
        except Hours.DoesNotExist:
            # nothing to credit
            pass
        Hours.objects.create(
          entry=entry,
          hours=hours,
          date=date,
          birthday=birthday,
        )
        total_hours += hours
    #raise NotImplementedError

    is_edit = entry.total_hours is not None
    #if entry.total_hours is not None:
    entry.total_hours = total_hours
    entry.save()

    return total_hours, is_edit



def send_email_notification(entry, extra_users, is_edit=False):
    email_addresses = list(settings.HR_MANAGERS)

    profile = entry.user.get_profile()
    if profile and profile.manager:
        manager = ldap_lookup.fetch_user_details(profile.manager)
        if manager.get('mail'):
            email_addresses.append(manager['mail'])

    if extra_users:
        email_addresses.extend(extra_users)
    email_addresses = list(set(email_addresses))  # get rid of dupes
    if not email_addresses:
        email_addresses = [settings.FALLBACK_TO_ADDRESS]
    if is_edit:
        subject = settings.EMAIL_SUBJECT_EDIT
    else:
        subject = settings.EMAIL_SUBJECT
    subject = subject % dict(
      first_name=entry.user.first_name,
      last_name=entry.user.last_name,
      username=entry.user.username,
      email=entry.user.email,
    )

    message = template = loader.get_template('dates/notification.txt')
    context = {
      'entry': entry,
      'user': entry.user,
      'is_edit': is_edit,
      'settings': settings,
      'start_date': entry.start.strftime(settings.DEFAULT_DATE_FORMAT),
    }
    body = template.render(Context(context)).strip()
    connection = get_connection()
    message = EmailMessage(
      subject=subject,
      body=body,
      from_email=entry.user.email,
      to=email_addresses,
      cc=entry.user.email and [entry.user.email] or None,
      connection=connection
    )

    cal = vobject.iCalendar()
    cal.add('method').value = 'PUBLISH'  # IE/Outlook needs this
    event = cal.add('vevent')
    if entry.total_hours < 8:
        hours = Hours.objects.get(entry=entry)
        if hours.birthday:
            length = 'birthday'
        else:
            length = '%s hours' % entry.total_hours
    else:
        days = (entry.end - entry.start).days + 1
        if days == 1:
            length = '1 day'
        else:
            length = '%d days' % days
    if entry.user.first_name:
        user_name = ('%s %s' %
          (entry.user.first_name, entry.user.last_name)).strip()
    else:
        user_name = entry.user.username
    summary = '%s on PTO (%s)' % (user_name, length)
    event.add('summary').value = summary
    event.add('dtstart').value = entry.start
    event.add('dtend').value = entry.end
    #url = (home_url + '?cal_y=%d&cal_m=%d' %
    #(slot.date.year, slot.date.month))
    #event.add('url').value = url
    description = ''
    event.add('description').value = description
    message.attach('event.ics', cal.serialize(), 'text/calendar')
    success = message.send()
    return success, email_addresses


@login_required
def emails_sent(request, pk):
    data = {}
    entry = get_object_or_404(Entry, pk=pk)
    if entry.user != request.user:
        if not (request.user.is_staff or request.user.is_superuser):
            return http.HttpResponseForbidden('insufficient access')

    emails = request.REQUEST.getlist('e')
    if isinstance(emails, basestring):
        emails = [emails]
    data['emails'] = emails
    data['emailed_users'] = []
    for email in emails:
        record = ldap_lookup.fetch_user_details(email)
        if record:
            data['emailed_users'].append(record)
        else:
            data['emailed_users'].append(email)
    show_fireworks = not request.COOKIES.get('no_fw', False)
    data['show_fireworks'] = show_fireworks
    return jingo.render(request, 'dates/emails_sent.html', data)


@login_required
def list_(request):
    data = {}
    form = forms.ListFilterForm(date_format='%d %B %Y',
                                data=request.GET)
    if form.is_valid():
        data['filters'] = form.cleaned_data

    data['today'] = datetime.date.today()
    entries_base = Entry.objects.all()

    try:
        data['first_date'] = entries_base.order_by('start')[0].start
        data['last_date'] = entries_base.order_by('-end')[0].end
        data['first_filed_date'] = (entries_base
                                    .order_by('add_date')[0]
                                    .add_date)
    except IndexError:
        # first run, not so important
        data['first_date'] = datetime.date(2000, 1, 1)
        data['last_date'] = datetime.date(2000, 1, 1)
        data['first_filed_date'] = datetime.date(2000, 1, 1)

    data['form'] = form
    return jingo.render(request, 'dates/list.html', data)


@json_view
@login_required
def list_json(request):
    data = []
    form = forms.ListFilterForm(date_format='%d %B %Y', data=request.GET)

    if form.is_valid():
        fdata = form.cleaned_data
        entries = (Entry.objects.exclude(total_hours=None)
                   .select_related('user'))
        if fdata.get('date_from'):
            entries = entries.filter(end__gte=fdata.get('date_from'))
        if fdata.get('date_to'):
            entries = entries.filter(start__lte=fdata.get('date_to'))
        if fdata.get('date_filed_from'):
            entries = entries.filter(
              add_date__gte=fdata.get('date_filed_from'))
        if fdata.get('date_filed_to'):
            entries = entries.filter(
              add_date__lt=fdata.get('date_filed_to') +
                datetime.timedelta(days=1))
        if fdata.get('name'):
            name = fdata['name'].strip()
            if valid_email(name):
                entries = entries.filter(user__email__iexact=name)
            else:
                entries = entries.filter(
                  Q(user__first_name__istartswith=name.split()[0]) |
                  Q(user__last_name__iendswith=name.split()[-1])
                )
    else:
        entries = Entry.objects.none()

    data = []
    profiles = {}
    for entry in entries:
        edit_link = hours_link = '&nbsp;'
        if entry.user.pk not in profiles:
            profiles[entry.user.pk] = entry.user.get_profile()
        profile = profiles[entry.user.pk]
        row = [entry.user.email,
               entry.user.first_name,
               entry.user.last_name,
               entry.add_date.strftime('%Y-%m-%d'),
               entry.total_hours,
               entry.start.strftime('%Y-%m-%d'),
               entry.end.strftime('%Y-%m-%d'),
               profile.city,
               profile.country,
               entry.details,
               edit_link,
               hours_link
               ]
        data.append(row)

    return {'aaData': data}

## Kumar stuff
#def home(request):
#    return jingo.render(request, 'pto/home.html',
#                        dict(calculate_pto_url=reverse('pto.calculate_pto')))
#
#
#def days_to_hrs(day):
#    return day * Decimal('8')
#
#
#def hrs_to_days(hour):
#    return hour / Decimal('8')
#
#
#@json_view
#def calculate_pto(request):
#    d = date.today()
#    today = datetime(d.year, d.month, d.day, 0, 0, 0)
#    trip_start = parse_datetime(request.GET['start_date'])
#    pointer = today
#    hours_per_quarter = Decimal(request.GET['per_quarter'])
#    hours_avail = Decimal(request.GET['hours_avail'])
#    while pointer <= trip_start:
#        if pointer.day == 1 or pointer.day == 15:
#            hours_avail += hours_per_quarter
#        if pointer.day > 15:
#            add_days = days_til_1st(pointer)
#        else:
#            add_days = 15 - pointer.day
#        if add_days == 0:
#            add_days = 15  # 1st of the month
#        pointer += timedelta(days=add_days)
#    return dict(hours_available_on_start=str(round(hours_avail, 2)),
#                days_available_on_start=str(round(hrs_to_days(hours_avail),
#                                                  2)))
#
#
#def days_til_1st(a_datetime):
#    """Returns the number of days until the 1st of the next month."""
#    next = a_datetime.replace(day=28)
#    while next.month == a_datetime.month:
#        next = next + timedelta(days=1)
#    return (next - a_datetime).days
#
