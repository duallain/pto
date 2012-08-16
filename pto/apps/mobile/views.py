# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import time
import datetime
from django import http
from django.db.models import Q
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.shortcuts import redirect, get_object_or_404, render
from django.contrib.auth import login as auth_login, logout as auth_logout
from pto.apps.dates.models import Entry, Hours
from pto.apps.dates.decorators import json_view
from pto.apps.dates.utils import get_weekday_dates
from pto.apps.users.forms import ProfileForm


MOBILE_DATE_FORMAT = '%Y-%m-%d'


def home(request):
    data = {}
    data['page_title'] = 'Mozilla Vacation'
    # not fully developed so disabled for now
    data['use_manifest'] = False#True#not settings.DEBUG

    response = render(request, 'mobile/mobile.html', data)
    # if you have loaded this page, forget the no-mobile cookie
    response.delete_cookie('no-mobile')
    return response

def appcache(request):
    data = {}
    return render(request, 'mobile/appcache.html', data,
                  content_type='text/cache-manifest')

@json_view
def right_now(request):
    if not request.user.is_authenticated():  # XXX improve this
        return {'error': 'Not logged in'}
    from pto.apps.dates.helpers import format_date
    from pto.apps.dates.views import get_observed_users, make_entry_title

    now = []
    upcoming = []
    user_ids = [request.user.pk]
    for user_ in get_observed_users(request.user, max_depth=2):
        user_ids.append(user_.pk)

    start = today = datetime.datetime.utcnow()
    end = start + datetime.timedelta(days=90)

    for entry in (Entry.objects
                   .filter(user__in=user_ids,
                           total_hours__gte=0,
                           total_hours__isnull=False)
                   .select_related('user')
                   .order_by('start')
                   .exclude(Q(end__lt=start) | Q(start__gte=end))):
        row = {}
        name = entry.user.get_full_name()
        if not name:
            name = entry.user.username
        row['name'] = name
        row['email'] = entry.user.email
        if entry.start > today.date():
            days = (entry.start - today.date()).days
            description = 'starts in '
            if days == 1:
                description += '1 day '
            elif days == 7:
                description += '1 week '
            elif days == 7:
                description += '2 weeks '
            else:
                description += '%d days ' % days
            description += 'on %s' % format_date(None, entry.end, shorter=True)
            row['descriptions'] = [description]
            upcoming.append(row)
        else:
            days_left = (entry.end - today.date()).days
            description = 'ends in '
            if days_left == 1:
                description += '1 day '
            else:
                description += '%d days ' % days_left
            description += 'on %s' % format_date(None, entry.end, shorter=True)
            row['descriptions'] = [description]
            now.append(row)

    return {'now': now, 'upcoming': upcoming}


@json_view
def taken(request):
    if not request.user.is_authenticated():  # XXX improve this
        return {'error': 'Not logged in'}
    from pto.apps.dates.views import get_taken_info
    return get_taken_info(request.user)


@csrf_exempt  # XXX fix this
@require_POST
@transaction.commit_on_success
@json_view
def notify(request):
    if not request.user.is_authenticated():  # XXX improve this
        return {'error': 'Not logged in'}
    from pto.apps.dates.forms import AddForm
    from pto.apps.dates.views import clean_unfinished_entries
    form = AddForm(request.user, data=request.POST)
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
        request.session['notify_extra'] = notify
        return {'entry': entry.pk}
    else:
        return {'form_errors': form.errors}


@csrf_exempt  # XXX fix this
@require_POST
@transaction.commit_on_success
@json_view
def save_hours(request):
    if not request.user.is_authenticated():  # XXX improve this
        return {'error': 'Not logged in'}
    if not request.POST.get('entry'):
        return http.HttpResponseBadRequest("No entry parameter provided")
    try:
        entry = Entry.objects.get(pk=request.POST['entry'])
    except Entry.DoesNotExist:
        return http.HttpResponseNotFound("Not found")
    if entry.user != request.user:
        return http.HttpResponseForbidden("Not your entry")

    from pto.apps.dates.forms import HoursForm
    from pto.apps.dates.views import save_entry_hours, send_email_notification
    form = HoursForm(entry, data=request.POST)
    if form.is_valid():
        total_hours, is_edit = save_entry_hours(entry, form)
        success, email_addresses = send_email_notification(
          entry,
          '',  # extra users to send to
          is_edit=is_edit,
        )
        return {'ok': True}

    else:
        return {'form_errors': form.errors}


@json_view
def hours_json(request):
    if not request.user.is_authenticated():  # XXX improve this
        return {'error': 'Not logged in'}

    entry_id = request.GET.get('entry')
    if not entry_id:
        return {'error': 'No entry pre-loaded'}
    entry = get_object_or_404(Entry, pk=entry_id)
    if entry.user != request.user:
        return http.HttpResponseForbidden("Not your entry")
    days = []

    for date in get_weekday_dates(entry.start, entry.end):
        key = date.strftime('d-%Y%m%d')
        try:
            hours_ = Hours.objects.get(
              date=date,
              entry__user=entry.user,
              hours__gt=0,
            )
            #initial[date.strftime('d-%Y%m%d')] = hours_.hours
            value = hours_.hours
        except Hours.DoesNotExist:
            #initial[date.strftime('d-%Y%m%d')] = settings.WORK_DAY
            value = settings.WORK_DAY
        days.append({'key': key,
                     'value': value,
                     'full_day': date.strftime(settings.DEFAULT_DATE_FORMAT)})
    return days

@json_view
def settings_json(request):
    if not request.user.is_authenticated():  # XXX improve this
        return {'error': 'Not logged in'}

    data = {
      'username': request.user.username,
      'email': request.user.email,
    }
    from pto.apps.dates.helpers import full_name_form
    data['full_name'] = full_name_form(None, request.user)
    profile = request.user.get_profile()
    if profile.start_date:
        data['start_date'] = profile.start_date.strftime(
          MOBILE_DATE_FORMAT)
    if profile.country:
        data['country'] = profile.country
    if profile.city:
        data['city'] = profile.city

    return data

@csrf_exempt  # XXX fix this
@require_POST
@transaction.commit_on_success
@json_view
def save_settings(request):
    if not request.user.is_authenticated():  # XXX improve this
        return {'error': 'Not logged in'}

    profile = request.user.get_profile()
    form = ProfileForm(instance=profile, data=request.POST)
    if form.is_valid():
        profile = form.save(commit=False)
        profile.country = form.cleaned_data['country']
        profile.save()
        return {'ok': True}
    else:
        return {'form_errors': form.errors}


def exit_mobile(request):
    r = redirect('/')
    then = datetime.datetime.now() + datetime.timedelta(days=300)
    r.set_cookie('no-mobile', 1, expires=then)
    return r


@csrf_exempt  # XXX fix this
@json_view
def login(request):
    if request.method == 'GET':
        return {'logged_in': request.user.is_authenticated()}

    from pto.apps.users.forms import AuthenticationForm
    form = AuthenticationForm(data=request.POST)
    if form.is_valid():
        auth_login(request, form.get_user())
        return {'ok': True}
    else:
        return {'form_errors': form.errors}

@csrf_exempt  # XXX fix this
@require_POST
@json_view
def logout(request):
    auth_logout(request)
    return {'ok': True}
