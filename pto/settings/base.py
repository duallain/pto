# This is your project's main settings file that can be committed to your
# repo. If you need to override a setting locally, use settings_local.py

from funfactory.settings_base import *

## Internationalization.

# Local time zone for this installation. Choices can be found here:
# http://en.wikipedia.org/wiki/List_of_tz_zones_by_name
# although not all choices may be available on all operating systems.
# On Unix systems, a value of None will cause Django to use the same
# timezone as the operating system.
# If running in a Windows environment this must be set to the same as your
# system time zone.
TIME_ZONE = 'America/Los_Angeles'

# If you set this to False, Django will make some optimizations so as not
# to load the internationalization machinery.
USE_I18N = False

# If you set this to False, Django will not format dates, numbers and
# calendars according to the current locale
USE_L10N = True

# Make this unique, and don't share it with anybody.
SECRET_KEY = ''  # override this in local.py

TEMPLATE_CONTEXT_PROCESSORS += (
    'pto.apps.dates.context_processors.global_settings',
)


JINGO_EXCLUDE_APPS = (
    'admin',
)

## Middlewares, apps, URL configs.

MIDDLEWARE_CLASSES = list(MIDDLEWARE_CLASSES)
MIDDLEWARE_CLASSES.remove('funfactory.middleware.LocaleURLMiddleware')
MIDDLEWARE_CLASSES = tuple(MIDDLEWARE_CLASSES)
MIDDLEWARE_CLASSES += (
    'mobility.middleware.DetectMobileMiddleware',
    'mobility.middleware.XMobileMiddleware',
    'commonware.middleware.ScrubRequestOnException',
)

ROOT_URLCONF = 'pto.urls'

INSTALLED_APPS += (
    'mobility',
    'django.contrib.messages',
    # Uncomment the next line to enable the admin:
    'django.contrib.admin',
    # Uncomment the next line to enable admin documentation:
    # 'django.contrib.admindocs',

    # apps/
    'pto.base',
    'pto.apps.dates',
    'pto.apps.users',
    'pto.apps.legacy',
    'pto.apps.mobile',
    'pto.apps.autocomplete',
)


## Auth
PWD_ALGORITHM = 'bcrypt'  # fast but insecure alternative 'sha512'
HMAC_KEYS = {  # for bcrypt only
    '2011-07-18': 'cheeseballs',
}

## Sessioning
SESSION_ENGINE = 'django.contrib.sessions.backends.cached_db'
SESSION_COOKIE_AGE = 60 * 60 * 24  # seconds, 1 day

## Memcache
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.memcached.MemcachedCache',
        'LOCATION': '127.0.0.1:11211',
        'KEY_PREFIX': 'pto',
    }
}

SESSION_COOKIE_SECURE = True
COOKIES_SECURE = True

## Tests
TEST_RUNNER = 'test_utils.runner.RadicalTestSuiteRunner'

## Celery
#BROKER_HOST = 'localhost'
#BROKER_PORT = 5672
#BROKER_USER = 'playdoh'
#BROKER_PASSWORD = 'playdoh'
#BROKER_VHOST = 'playdoh'
#BROKER_CONNECTION_TIMEOUT = 0.1
#CELERY_RESULT_BACKEND = 'amqp'
#CELERY_IGNORE_RESULT = True

# Logging
LOGGING = dict(loggers=dict(playdoh={'level': logging.DEBUG}))

AUTH_PROFILE_MODULE = 'users.UserProfile'

LOGIN_URL = '/users/login/'
LOGOUT_REDIRECT_URL = '/'
LOGIN_REDIRECT_URL = '/'

DEFAULT_DATE_FORMAT = '%A, %B %d, %Y'
WORK_DAY = 8  # hours

EMAIL_SUBJECT = 'Vacation notification from %(first_name)s %(last_name)s'
EMAIL_SUBJECT_EDIT = 'Vacation update from %(first_name)s %(last_name)s'
EMAIL_SIGNATURE = "Mozilla Vacation"
FALLBACK_TO_ADDRESS = 'jvandeven@mozilla.com'

# People you're not allowed to notify additionally
EMAIL_BLACKLIST = (
  'all@mozilla.com',
  'all-mv@mozilla.com',
)

TOTALS = {
  # COUNTRY: (HOLIDAYS, SICKDAYS)
  'US': {'holidays': 21, 'sickdays': 0},
  'GB': {'holidays': 18, 'sickdays': 6},
  # Jill?!?!?!
}

# because we use LDAP users only, we never have to store real passwords,
# we don't need django_sha2 so go back to Django defaults
PASSWORD_HASHERS = (
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher',
    'django.contrib.auth.hashers.BCryptPasswordHasher',
    'django.contrib.auth.hashers.SHA1PasswordHasher',
    'django.contrib.auth.hashers.MD5PasswordHasher',
    'django.contrib.auth.hashers.CryptPasswordHasher',
)

try:
    ## LDAP
    import ldap

    AUTHENTICATION_BACKENDS = (
       'pto.apps.users.email_auth_backend.EmailOrUsernameModelBackend',
       'pto.apps.users.auth.backends.MozillaLDAPBackend',
       'django.contrib.auth.backends.ModelBackend',
    )

    # these must be set in settings/local.py!
    AUTH_LDAP_SERVER_URI = ''
    #AUTH_LDAP_BIND_DN = ''
    #AUTH_LDAP_BIND_PASSWORD = ''

    AUTH_LDAP_START_TLS = True
    AUTH_LDAP_USER_ATTR_MAP = {
      "first_name": "givenName",
      "last_name": "sn",
      "email": "mail",
    }
    AUTH_LDAP_PROFILE_ATTR_MAP = {
        "manager": "manager",
        "office": "physicalDeliveryOfficeName",
    }
    from django_auth_ldap.config import LDAPSearch
    AUTH_LDAP_USER_SEARCH = LDAPSearch(
      "o=com,dc=mozilla",
      ldap.SCOPE_SUBTREE,
      "mail=%(user)s"
    )
    AUTH_LDAP_USER_DN_TEMPLATE = "mail=%(user)s,o=com,dc=mozilla"

except ImportError:
    AUTHENTICATION_BACKENDS = (
       'pto.apps.users.email_auth_backend.EmailOrUsernameModelBackend',
       'django.contrib.auth.backends.ModelBackend',
    )
