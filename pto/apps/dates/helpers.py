# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import urllib
import urlparse
import textwrap

from django.contrib.auth.models import User
from django.conf import settings
from django.utils.encoding import smart_str
from django.core.urlresolvers import reverse
from django.contrib.staticfiles.storage import staticfiles_storage

import jinja2
from jingo import register


def urlencode(items):
    """A Unicode-safe URLencoder."""
    try:
        return urllib.urlencode(items)
    except UnicodeEncodeError:
        return urllib.urlencode([(k, smart_str(v)) for k, v in items])


def urlparams(url_, hash=None, **query):
    """
    Add a fragment and/or query paramaters to a URL.

    New query params will be appended to exising parameters, except duplicate
    names, which will be replaced.
    """
    url = urlparse.urlparse(url_)
    fragment = hash if hash is not None else url.fragment

    # Use dict(parse_qsl) so we don't get lists of values.
    q = url.query
    query_dict = dict(urlparse.parse_qsl(smart_str(q))) if q else {}
    query_dict.update((k, v) for k, v in query.items())

    query_string = urlencode([(k, v) for k, v in query_dict.items()
                             if v is not None])
    new = urlparse.ParseResult(url.scheme, url.netloc, url.path, url.params,
                               query_string, fragment)
    return new.geturl()


@register.function
@jinja2.contextfunction
def truncatewords(context, string, length):
    if len(string) > length:
        string = string[:length - 3] + '...'
    return string


#@register.function
#@jinja2.contextfunction
#def media(context, url, key='MEDIA_URL'):
#    """Get a MEDIA_URL link with a cache buster querystring."""
#    if url.endswith('.js'):
#        build = context['BUILD_ID_JS']
#    elif url.endswith('.css'):
#        build = context['BUILD_ID_CSS']
#    else:
#        #build = context['BUILD_ID_IMG']
#        build = context['BUILD_ID_JS']
#    return context[key] + urlparams(url, b=build)


@register.function
def static(path):
    return staticfiles_storage.url(path)


@register.function
@jinja2.contextfunction
def entry_to_list_url(context, entry):
    url = reverse('dates.list')
    values = {'name': entry.user.email,
              'date_from': entry.start.strftime('%d %B %Y'),
              'date_to': entry.end.strftime('%d %B %Y'),
              }
    values_encoded = urllib.urlencode(values)
    return '%s?%s' % (url, values_encoded)


@register.function
@jinja2.contextfunction
def full_name_form(context, user, avoid_email=False):
    if user is None:
        return ''
    elif (isinstance(user, dict)
        and 'sn' in user
        and 'givenName' in user
        and 'mail' in user):
        name = ('%s %s' % (user['givenName'],
                           user['sn'])).strip()
        if not name:
            name = user['cn']
        email = user['mail']
    elif isinstance(user, User):
        name = ('%s %s' % (user.first_name,
                           user.last_name)).strip()
        if not name:
            name = user.username
        email = user.email
    else:
        assert isinstance(user, basestring)
        if '@' in user:
            email = user
            name = None
        else:
            email = None
            name = user

    if name and email and not avoid_email:
        return '%s <%s>' % (name, email)
    elif name:
        return name
    else:
        return email


@register.function
@jinja2.contextfunction
def format_date(context, date, format=None, shorter=False):
    if format is None:
        format = settings.DEFAULT_DATE_FORMAT
    if shorter:
        format = format.replace('%B', '%b')
        format = format.replace('%A', '%a')
    return date.strftime(format)


@register.function
def line_indent(text, indent=' ' * 4):
    return '\n'.join(textwrap.wrap(text,
                                   initial_indent=indent,
                                   subsequent_indent=indent))
