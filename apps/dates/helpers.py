import urllib
import urlparse

from django.contrib.auth.models import User
from django.conf import settings
from django.utils.encoding import smart_str
from django.core.urlresolvers import reverse

from dates.models import Hours
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
def media(context, url, key='MEDIA_URL'):
    """Get a MEDIA_URL link with a cache buster querystring."""
    if url.endswith('.js'):
        build = context['BUILD_ID_JS']
    elif url.endswith('.css'):
        build = context['BUILD_ID_CSS']
    else:
        build = context['BUILD_ID_IMG']
    return context[key] + urlparams(url, b=build)


@register.function
@jinja2.contextfunction
def static(context, url):
    """Get a STATIC_URL link with a cache buster querystring."""
    return media(context, url, 'STATIC_URL')


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
def entry_length(context, entry):
    return (entry.end - entry.start).days + 1


@register.function
@jinja2.contextfunction
def entry_is_birthday(context, entry):
    if entry.total_hours == 0:
        if (entry.end - entry.start).days == 0:
            if Hours.objects.filter(entry=entry, birthday=True).exists():
                return True
    return False


@register.function
@jinja2.contextfunction
def full_name_form(context, user):
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

    if name and email:
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
    return date.strftime(format)
