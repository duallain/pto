# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import logging
from django import http
from apps.dates.decorators import json_view
from apps.users.models import UserProfile, User
from apps.users.utils import ldap_lookup


@json_view
def cities(request):
    if not request.user.is_authenticated():
        return http.HttpResponseForbidden('Must be logged in')
    data = []
    term = request.GET.get('term')
    qs = UserProfile.objects.exclude(city='')
    if term:
        qs = qs.filter(city__istartswith=term)
    for each in (qs
                     .values('city')
                     .distinct()
                     .order_by('city')):
        city = each['city']
        data.append(city)
    return data

@json_view
def users(request, known_only=False):
    if not request.user.is_authenticated():
        return http.HttpResponseForbidden('Must be logged in')
    query = request.GET.get('term').strip()
    if len(query) < 2:
        return []

    results = []
    # I chose a limit of 30 because there are about 20+ 'peter'
    # something in mozilla
    for each in ldap_lookup.search_users(query, 30, autocomplete=True):
        if not each.get('givenName'):
            logging.warn("Skipping LDAP entry %s" % each)
            continue
        if known_only:
            if not User.objects.filter(email__iexact=each['mail']).exists():
                continue
        full_name_and_email = '%s %s <%s>' % (each['givenName'],
                                              each['sn'],
                                              each['mail'])
        result = {'id': each['uid'],
                  'label': full_name_and_email,
                  'value': full_name_and_email}
        results.append(result)
    return results
