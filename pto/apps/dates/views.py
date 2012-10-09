# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import re
import datetime
from urllib import urlencode
from collections import defaultdict
from django import http
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
from django.db import transaction
from django.core.urlresolvers import reverse
from django.conf import settings
from django.shortcuts import redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Q
from django.template import Context, loader
from django.core.mail import get_connection, EmailMessage
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.shortcuts import render
from django.views.decorators.http import require_POST
from django.contrib.sites.models import RequestSite
from django.core.cache import cache
from django.db.models import Min, Count
import vobject
from .models import Entry, Hours, BlacklistedUser, FollowingUser, UserKey
from pto.apps.users.models import UserProfile, User
from pto.apps.users.utils import ldap_lookup
from .utils import parse_datetime, DatetimeParseError
from .utils.countrytotals import UnrecognizedCountryError, get_country_totals
import utils
import forms
from .decorators import json_view
from .csv_export import UnicodeWriter as CSVUnicodeWriter


def valid_email(value):
    try:
        validate_email(value)
        return True
    except ValidationError:
        return False


def handler500(request):
    data = {}
    import sys
    import traceback
    from StringIO import StringIO
    err_type, err_value, err_traceback = sys.exc_info()
    out = StringIO()
    traceback.print_exc(file=out)
    traceback_formatted = out.getvalue()
    data['err_type'] = err_type
    data['err_value'] = err_value
    data['err_traceback'] = traceback_formatted
    return render(request, '500.html', data, status=500)


def home(request):  # aka dashboard
    data = {}
    data['mobile'] = request.MOBILE  # thank you django-mobility (see settings)
    if data['mobile']:
        # unless an explicit cookie it set, redirect to /mobile/
        if not request.COOKIES.get('no-mobile', False):
            return redirect(reverse('mobile.home'))

    # now do what the login_required would usually do
    if not request.user.is_authenticated():
        path = request.get_full_path()
        return redirect_to_login(path)

    data['page_title'] = "Dashboard"
    profile = request.user.get_profile()
    if profile and profile.country in ('GB', 'FR', 'DE'):
        first_day = 1  # 1=Monday
    else:
        first_day = 0  # default to 0=Sunday
    data['first_day'] = first_day

    if 'all-rightnow' in request.GET:
        MAX_RIGHT_NOWS = 9999
    else:
        MAX_RIGHT_NOWS = 20

    ## Commented out whilst we decide whether to keep it at all
    #right_nows, right_now_users = get_right_nows()
    #data['right_nows'] = right_nows
    #data['right_now_users'] = right_now_users
    #if len(right_now_users) > MAX_RIGHT_NOWS:
    #    data['right_now_too_many'] = (len(data['right_now_users'])
    #                                   - MAX_RIGHT_NOWS)
    #    data['right_now_users'] = data['right_now_users'][:MAX_RIGHT_NOWS]
    #else:
    #    data['right_now_too_many'] = None

    data.update(get_taken_info(request.user))

    data['calendar_url'] = _get_user_calendar_url(request)

    cache_key = 'recently_created_%s' % request.user.pk
    recently_created = cache.get(cache_key)
    if recently_created:
        data['recently_created'] = recently_created
        cache.delete(cache_key)

    return render(request, 'dates/home.html', data)

def _get_user_calendar_url(request):
    user_key, __ = UserKey.objects.get_or_create(user=request.user)
    base_url = '%s://%s' % (request.is_secure() and 'https' or 'http',
                            RequestSite(request).domain)
    return base_url + reverse('dates.calendar_vcal', args=(user_key.key,))


def get_taken_info(user):
    data = {}

    profile = user.get_profile()
    if profile.country:
        data['country'] = profile.country
        try:
            data['country_totals'] = get_country_totals(profile.country)
        except UnrecognizedCountryError:
            data['unrecognized_country'] = True

    today = datetime.date.today()
    start_date = datetime.date(today.year, 1, 1)
    last_date = datetime.date(today.year + 1, 1, 1)
    from django.db.models import Sum
    qs = Entry.objects.filter(
      user=user,
      start__gte=start_date,
      end__lt=last_date
    )
    agg = qs.aggregate(Sum('total_hours'))
    total_hours = agg['total_hours__sum']
    if total_hours is None:
        total_hours = 0
    data['taken'] = _friendly_format_hours(total_hours)

    return data


def _friendly_format_hours(total_hours):
    days = 1.0 * total_hours / settings.WORK_DAY
    hours = total_hours % settings.WORK_DAY

    if not total_hours:
        return '0 days'
    elif total_hours < settings.WORK_DAY:
        return '%s hours' % total_hours
    elif total_hours == settings.WORK_DAY:
        return '1 day'
    else:
        if not hours:
            return '%d days' % days
        else:
            return '%s days' % days


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


def make_entry_title(entry, this_user, include_details=True):
    if entry.user != this_user:
        if entry.user.first_name:
            title = '%s %s - ' % (entry.user.first_name,
                                  entry.user.last_name)
        else:
            title = '%s - ' % entry.user.username
    else:
        title = ''
    days = 0
    for hour in Hours.objects.filter(entry=entry):
        if hour.hours == 8:
            days += 1
        elif hour.hours == 4:
            days += 0.5

    if days > 1:
        if int(days) == days:
            title += '%d days' % days
        else:
            title += '%s days' % days
        if Hours.objects.filter(entry=entry, birthday=True).exists():
            title += ' (includes birthday)'
    elif (days == 1 and entry.total_hours == 0 and
        Hours.objects.filter(entry=entry, birthday=True)):
        title += 'Birthday!'
    elif days == 1 and entry.total_hours == 8:
        title += '1 day'
    else:
        title += '%s hours' % entry.total_hours
    if entry.details:
        if days == 1:
            max_length = 20
        else:
            max_length = 40
        if include_details:
            title += ', '
            if len(entry.details) > max_length:
                title += entry.details[:max_length] + '...'
            else:
                title += entry.details
    return title


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

    COLORS = ("#EAA228", "#c5b47f", "#579575", "#839557", "#958c12",
              "#953579", "#4b5de4", "#d8b83f", "#ff5800", "#0085cc",
              "#c747a3", "#cddf54", "#FBD178", "#26B4E3", "#bd70c7")
    user_ids = [request.user.pk]
    colors = {}
    colors_fullnames = []
    colors[request.user.pk] = None
    colors_fullnames.append((request.user.pk, 'Me myself and I', '#3366CC'))
    for i, user_ in enumerate(get_observed_users(request.user, max_depth=2)):
        user_ids.append(user_.pk)

        colors[user_.pk] = COLORS[i]
        full_name = user_.get_full_name()
        if not full_name:
            full_name = user_.username
        colors_fullnames.append((
          user_.pk,
          full_name,
          colors[user_.pk]
        ))

    _managers = {}

    def can_see_details(user):
        if request.user.is_superuser:
            return True
        if request.user.pk == user.pk:
            return True
        if user.pk not in _managers:
            _profile = user.get_profile()
            _manager = None
            if _profile and _profile.manager_user:
                _manager = _profile.manager_user.pk
            _managers[user.pk] = _manager
        return _managers[user.pk] == request.user.pk

    visible_user_ids = set()
    for entry in (Entry.objects
                   .filter(user__in=user_ids,
                           total_hours__gte=0,
                           total_hours__isnull=False)
                   .select_related('user')
                   .exclude(Q(end__lt=start) | Q(start__gt=end))):
        visible_user_ids.add(entry.user.pk)
        entries.append({
          'id': entry.pk,
          'title': make_entry_title(entry, request.user,
                                  include_details=can_see_details(entry.user)),
          'start': entry.start.strftime('%Y-%m-%d'),
          'end': entry.end.strftime('%Y-%m-%d'),
          'color': colors[entry.user.pk],
          'mine': entry.user.pk == request.user.pk,
        })

    colors = [dict(name=x, color=y) for (pk, x, y) in colors_fullnames
              if pk in visible_user_ids]
    return {'events': entries, 'colors': colors}


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


def get_siblings(user):
    profile = user.get_profile()
    if not profile.manager_user:
        return []
    users = []
    for profile in (UserProfile.objects
                    .filter(manager_user=profile.manager_user)
                    .exclude(pk=user.pk)
                    .select_related('user')):
        users.append(profile.user)
    return users


def get_followed_users(user):
    users = []
    for each in (FollowingUser.objects
                 .filter(follower=user)
                 .select_related('following')):
        users.append(each.following)
    return users


def get_observed_users(this_user, depth=1, max_depth=2):
    users = []

    def is_blacklisted(user):
        return (BlacklistedUser.objects
                .filter(observer=this_user, observable=user)
                .exists())

    for user in get_minions(this_user, depth=depth, max_depth=max_depth):
        if user not in users:
            if not is_blacklisted(user):
                users.append(user)

    for user in get_siblings(this_user):
        if user not in users:
            if not is_blacklisted(user):
                users.append(user)

    profile = this_user.get_profile()
    manager = profile.manager_user
    if manager and manager not in users:
        if not is_blacklisted(manager):
            users.append(manager)

    for user in get_followed_users(this_user):
        if user not in users:
            users.append(user)

    return users


@transaction.commit_on_success
@login_required
def notify(request):
    data = {}
    data['page_title'] = "Notify about new vacation"
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
    data['hr_managers'] = [x.user for x in
                           (UserProfile.objects
                            .filter(hr_manager=True)
                            .select_related('user'))]

    data['manager'] = manager
    data['all_managers'] = [x for x in data['hr_managers'] if x]
    if manager:
        data['all_managers'].append(manager)
    data['form'] = form
    return render(request, 'dates/notify.html', data)


@transaction.commit_on_success
@login_required
def cancel_notify(request):
    Entry.objects.filter(user=request.user, total_hours__isnull=True).delete()
    return redirect(reverse('dates.home'))


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

            #messages.info(request,
            #  '%s hours of vacation logged.' % total_hours
            #)
            recently_created = make_entry_title(entry, request.user)
            cache_key = 'recently_created_%s' % request.user.pk
            cache.set(cache_key, recently_created, 60)

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

        form = forms.HoursForm(entry, initial=initial)
    data['form'] = form

    if entry.total_hours:
        data['total_hours'] = entry.total_hours
    else:
        total_days = 0
        for date in utils.get_weekday_dates(entry.start, entry.end):
            try:
                hours_ = Hours.objects.get(entry=entry, date=date)
                print hours_.hours
                if hours_.hours == settings.WORK_DAY:
                    total_days += 1
                elif hours_.hours:
                    total_days += .5
            except Hours.DoesNotExist:
                total_days += 1
        data['total_days'] = total_days

    notify = request.session.get('notify_extra', [])
    data['notify'] = notify

    return render(request, 'dates/hours.html', data)


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
    email_addresses = []
    for profile in (UserProfile.objects
                     .filter(hr_manager=True,
                             user__email__isnull=False)):
        email_addresses.append(profile.user.email)

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
    return render(request, 'dates/emails_sent.html', data)


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
    data['query_string'] = request.META.get('QUERY_STRING')
    return render(request, 'dates/list.html', data)


@login_required
def list_csv(request):
    entries = get_entries_from_request(request.GET)
    response = http.HttpResponse(mimetype='text/csv')
    writer = CSVUnicodeWriter(response)
    writer.writerow((
      'ID',
      'EMAIL',
      'FIRST NAME',
      'LAST NAME',
      'ADDED',
      'START',
      'END',
      'DAYS',
      'DETAILS',
      'CITY',
      'COUNTRY',
      'START DATE',
    ))

    profiles = {}  # basic memoization
    for entry in entries:
        if entry.user.pk not in profiles:
            profiles[entry.user.pk] = entry.user.get_profile()
        profile = profiles[entry.user.pk]
        writer.writerow((
          str(entry.pk),
          entry.user.email,
          entry.user.first_name,
          entry.user.last_name,
          entry.add_date.strftime('%Y-%m-%d'),
          entry.start.strftime('%Y-%m-%d'),
          entry.end.strftime('%Y-%m-%d'),
          str(entry.total_days),
          entry.details,
          profile.city,
          profile.country,
          (profile.start_date and
           profile.start_date.strftime('%Y-%m-%d') or ''),
        ))

    return response


@json_view
@login_required
def list_json(request):
    entries = get_entries_from_request(request.GET)

    _managers = {}

    def can_see_details(user):
        if request.user.is_superuser:
            return True
        if request.user.pk == user.pk:
            return True
        if user.pk not in _managers:
            _profile = user.get_profile()
            _manager = None
            if _profile and _profile.manager_user:
                _manager = _profile.manager_user.pk
            _managers[user.pk] = _manager
        return _managers[user.pk] == request.user.pk

    data = []
    profiles = {}
    for entry in entries:
        if entry.user.pk not in profiles:
            profiles[entry.user.pk] = entry.user.get_profile()
        profile = profiles[entry.user.pk]
        if entry.total_hours < 0:
            details = '*automatic edit*'
        elif can_see_details(entry.user):
            details = entry.details
        else:
            details = ''

        row = [entry.user.email,
               entry.user.first_name,
               entry.user.last_name,
               entry.add_date.strftime('%Y-%m-%d'),
               entry.total_days,
               entry.start.strftime('%Y-%m-%d'),
               entry.end.strftime('%Y-%m-%d'),
               profile.city,
               profile.country,
               details,
               #edit_link,
               #hours_link
               ]
        data.append(row)

    return {'aaData': data}


def get_entries_from_request(data):
    form = forms.ListFilterForm(date_format='%d %B %Y', data=data)

    if not form.is_valid():
        return Entry.objects.none()

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
    if fdata.get('country'):
        country = fdata['country'].strip()
        _users = UserProfile.objects.filter(country=country).values('user_id')
        entries = entries.filter(user__id__in=_users)

    return entries


@login_required
def following(request):
    data = {}
    observed = []
    _followed = get_followed_users(request.user)
    _minions_1 = get_minions(request.user, depth=1, max_depth=1)
    _minions_2 = get_minions(request.user, depth=1, max_depth=2)
    _manager = request.user.get_profile().manager_user
    for user in sorted(get_observed_users(request.user, max_depth=2),
                       lambda x, y: cmp(x.first_name.lower(),
                                        y.first_name.lower())):
        if user in _minions_1:
            reason = 'direct manager of'
        elif user in _minions_2:
            reason = 'indirect manager of'
        elif user == _manager:
            reason = 'your manager'
        elif user in _followed:
            reason = 'curious'
        else:
            reason = 'teammate'
        observed.append((user, reason))
    not_observed = (BlacklistedUser.objects
                    .filter(observer=request.user)
                    .order_by('observable__first_name'))

    data['observed'] = observed
    data['not_observed'] = [x.observable for x in not_observed]
    return render(request, 'dates/following.html', data)


@json_view
@login_required
@transaction.commit_on_success
@require_POST
def save_following(request):
    search = request.POST.get('search')
    if not search:
        return http.HttpResponseBadRequest('Missing search')

    if (-1 < search.rfind('<') < search.rfind('@') < search.rfind('>')):
        try:
            email = re.findall('<([\w\.\-]+@[\w\.\-]+)>', search)[0]
            email = email.strip()
            validate_email(email)
        except (ValidationError, IndexError):
            email = None
    elif search.isdigit():
        try:
            email = User.objects.get(pk=search).email
        except User.DoesNotExist:
            email = None  # will deal with this later
    else:
        found = []
        result = ldap_lookup.search_users(search, 30, autocomplete=True)
        for each in result:
            try:
                found.append(User.objects.get(email__iexact=each['mail']))
            except User.DoesNotExist:
                pass
        if len(found) > 1:
            return http.HttpResponseBadRequest('More than one user found')
        elif not found:
            return http.HttpResponseBadRequest('No user found')
        else:
            email = found[0].email

    # if no email is found in the search, it's an error
    if not email:
        return http.HttpResponseBadRequest('No email found')

    try:
        user = User.objects.get(email__iexact=email)
    except User.DoesNotExist:
        return http.HttpResponseBadRequest('No user by that email found')

    FollowingUser.objects.get_or_create(
      follower=request.user,
      following=user,
    )

    # find a reason why we're following this user
    _minions_1 = get_minions(request.user, depth=1, max_depth=1)
    _minions_2 = get_minions(request.user, depth=1, max_depth=2)
    if user in _minions_1:
        reason = 'direct manager of'
    elif user in _minions_2:
        reason = 'indirect manager of'
    elif user == request.user.get_profile().manager_user:
        reason = 'your manager'
    elif (request.user.get_profile().manager_user
          and user in _minions_1):
        reason = 'teammate'
    else:
        reason = 'curious'

    name = ('%s %s' % (user.first_name,
                       user.last_name)).strip()
    if not name:
        name = user.username

    data = {
      'id': user.pk,
      'name': name,
      'reason': reason,
    }

    return data


@json_view
@login_required
@transaction.commit_on_success
@require_POST
def save_unfollowing(request):
    remove = request.POST.get('remove')
    try:
        user = User.objects.get(pk=remove)
    except (ValueError, User.DoesNotExist):
        return http.HttpResponseBadRequest('Invalid user ID')

    for f in (FollowingUser.objects
              .filter(follower=request.user, following=user)):
        f.delete()

    data = {}
    if user in get_observed_users(request.user, max_depth=2):
        # if not blacklisted, this user will automatically re-appear
        BlacklistedUser.objects.get_or_create(
          observer=request.user,
          observable=user
        )
        data['id'] = user.pk
        name = ('%s %s' % (user.first_name,
                           user.last_name)).strip()
        if not name:
            name = user.username
        data['name'] = name

    return data


def calendar_vcal(request, key):
    base_url = '%s://%s' % (request.is_secure() and 'https' or 'http',
                            RequestSite(request).domain)
    home_url = base_url + '/'
    cal = vobject.iCalendar()
    cal.add('x-wr-calname').value = 'Mozilla Vacation'

    try:
        user = UserKey.objects.get(key=key).user
    except UserKey.DoesNotExist:
        # instead of raising a HTTP error, respond a calendar
        # that urges the user to update the stale URL
        event = cal.add('vevent')
        event.add('summary').value = (
          "Calendar expired. Visit %s#calendarurl to get the "
          "new calendar URL" % home_url
        )
        today = datetime.date.today()
        event.add('dtstart').value = today
        event.add('dtend').value = today
        event.add('url').value = '%s#calendarurl' % (home_url,)
        event.add('description').value = ("The calendar you used has expired "
        "and is no longer associated with any user")
        return _render_vcalendar(cal, key)

    # always start on the first of this month
    today = datetime.date.today()
    #first = datetime.date(today.year, today.month, 1)

    user_ids = [user.pk]
    for user_ in get_observed_users(user, max_depth=2):
        user_ids.append(user_.pk)

    entries = (Entry.objects
               .filter(user__in=user_ids,
                       total_hours__gte=0,
                       total_hours__isnull=False,
                       end__gte=today)
               .select_related('user')
               )

    _list_base_url = base_url + reverse('dates.list')

    def make_list_url(entry):
        name = entry.user.get_full_name()
        if not name:
            name = entry.user.username
        data = {
          'date_from': entry.start.strftime('%d %B %Y'),
          'date_to': entry.end.strftime('%d %B %Y'),
          'name': name
        }
        return _list_base_url + '?' + urlencode(data, True)
    for entry in entries:
        event = cal.add('vevent')
        event.add('summary').value = '%s Vacation' % make_entry_title(entry, user,
                                                include_details=False)
        event.add('dtstart').value = entry.start
        event.add('dtend').value = entry.end
        #url = (home_url + '?cal_y=%d&cal_m=%d' %
        #       (slot.date.year, slot.date.month))
        event.add('url').value = make_list_url(entry)
        #event.add('description').value = entry.details
        event.add('description').value = "Log in to see the details"

    return _render_vcalendar(cal, key)


def _render_vcalendar(cal, key):
    #return http.HttpResponse(cal.serialize(),
    #                         mimetype='text/plain;charset=utf-8'
    #                         )
    resp = http.HttpResponse(cal.serialize(),
                             mimetype='text/calendar;charset=utf-8'
                             )
    filename = '%s.ics' % (key,)
    resp['Content-Disposition'] = 'inline; filename="%s"' % filename
    return resp


@login_required
@transaction.commit_on_success
def reset_calendar_url(request):
    for each in UserKey.objects.filter(user=request.user):
        each.delete()
    return redirect(reverse('dates.home') + '#calendarurl')


@login_required
def about_calendar_url(request):
    data = {}
    data['calendar_url'] = _get_user_calendar_url(request)
    return render(request, 'dates/about-calendar-url.html', data)

@login_required
def duplicate_report(request):
    data = {
      'filter_errors': None,
    }

    if request.method == 'POST':
        raise NotImplementedError
    else:
        form = forms.DuplicateReportFilterForm(date_format='%d %B %Y',
                                               data=request.GET)
        user = request.user
        filter_ = dict(user=user)

        if form.is_valid():
            if form.cleaned_data['user']:
                user = form.cleaned_data['user']
                if user != request.user:
                    if not (request.user.is_superuser
                            or request.user.is_staff):
                        if user != request.user:
                            return http.HttpResponse(
                                                 "Only available for admins")
                filter_['user'] = user

            if form.cleaned_data['since']:
                filter_['start__gte'] = form.cleaned_data['since']
                data['since'] = form.cleaned_data['since']
        else:
            data['filter_errors'] = form.errors

        data['first_date'] = (Entry.objects
                              .filter(user=user)
                              .aggregate(Min('start'))
                              ['start__min'])

        start_dates = (Entry.objects
                       .filter(**filter_)
                       .values("start")
                       .annotate(Count("start"))
                       .order_by('-start__count'))
        groups = []
        for each in start_dates:
            if each['start__count'] <= 1:
                break
            entries = Entry.objects.filter(user=user, start=each['start'])
            details = [x.details for x in entries]
            note = "Probably not a mistake"
            if len(set(details)) == 1:
                note = ("Probably a duplicate! "
                        "The details are the same for each entry")
            else:
                note = "Possibly not a duplicate since the details different"
            groups.append((entries, note))
        data['groups'] = groups

        if 'since' not in data:
            data['since'] = data['first_date']

    return render(request, 'dates/duplicate-report.html', data)
