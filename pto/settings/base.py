# This is your project's main settings file that can be committed to your
# repo. If you need to override a setting locally, use settings_local.py

from funfactory.settings_base import *

# Name of the top-level module where you put all your apps.
# If you did not install Playdoh with the funfactory installer script
# you may need to edit this value. See the docs about installing from a
# clone.
PROJECT_MODULE = 'pto'

# Bundles is a dictionary of two dictionaries, css and js, which list css files
# and js files that can be bundled together by the minify app.
#MINIFY_BUNDLES = {
#    'css': {
##        'global': (
##            'css/style.css',
##        ),
#        'jquery_ui': (
#            'css/libs/jquery_ui/redmond/jquery-ui-1.8.20.datepicker.autocomplete.dialog.css',
#        ),
#        'libs/jquery_mobile': (
#            'css/libs/jquery.mobile-1.1.0.min.css',
#        ),
#        'mobile': (
#            'css/mobile/mobile.css',
#        ),
##        'dates': (
##            'css/dates/notify.css',
##            'css/dates/hours.css',
##        ),
#        'dates.home': (
#            'css/libs/fullcalendar.css',
#            'css/dates/home.css',
#        ),
#        'dates.emails_sent': (
#            'css/libs/fireworks.css',
#        ),
##        'dates.list': (
##            'css/libs/datatable/css/demo_table.css',
##        ),
##        'dates.following': (
##            'css/dates/following.css',
##        ),
#        'dates.about-calendar-url': (
#            'css/dates/about-calendar-url.css',
#        ),
#    },
#    'js': {
#        'mobile': (
#            'js/libs/jquery-1.7.2.min.js',
#            'js/libs/date.js',
#            'js/mobile/mobile.js',
#            'js/libs/jquery.mobile-1.1.0.min.js',
#        ),
##        'dates.hours': (
##            'js/dates/hours.js',
##        ),
##        'dates.emails_sent': (
##            'js/libs/soundmanager2-nodebug-jsmin.js',
##            'js/libs/fireworks.js',
##            'js/libs/jquery.cookie.min.js',
##            'js/dates/emails_sent.js',
##        ),
##        'jquery_ui': (
##            'js/libs/jquery-ui-1.8.20.datepicker.autocomplete.dialog.min.js',
##        ),
##        'dates.notify': (
##            'js/dates/notify.js',
##        ),
##        'dates.list': (
##            'js/libs/jquery.dataTables.js',
##            'js/dates/list.js',
##        ),
##        'dates.following': (
##            'js/dates/following.js',
##        ),
##        'users.profile': (
##            'js/users/profile.js',
##        ),
#    }
#}

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
    'apps.dates.context_processors.global_settings',
    'jingo_minify.helpers.build_ids',
)


JINGO_EXCLUDE_APPS = (
    'admin',
)

## Middlewares, apps, URL configs.

MIDDLEWARE_CLASSES = list(MIDDLEWARE_CLASSES)
MIDDLEWARE_CLASSES.remove('funfactory.middleware.LocaleURLMiddleware')
MIDDLEWARE_CLASSES.append('commonware.middleware.HidePasswordOnException')
MIDDLEWARE_CLASSES.append('mobility.middleware.DetectMobileMiddleware')
MIDDLEWARE_CLASSES.append('mobility.middleware.XMobileMiddleware')
MIDDLEWARE_CLASSES = tuple(MIDDLEWARE_CLASSES)

ROOT_URLCONF = '%s.urls' % PROJECT_MODULE

INSTALLED_APPS += (
    'mobility',
    'django.contrib.messages',
    # Uncomment the next line to enable the admin:
    'django.contrib.admin',
    # Uncomment the next line to enable admin documentation:
    # 'django.contrib.admindocs',

    # apps/
    'base',
    'apps.dates',
    'apps.users',
    'apps.legacy',
    'apps.mobile',
    'apps.autocomplete',
)


# Path to Java. Used for compress_assets.
JAVA_BIN = '/usr/bin/java'

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

EMAIL_SUBJECT = 'PTO notification from %(first_name)s %(last_name)s'
EMAIL_SUBJECT_EDIT = 'PTO update from %(first_name)s %(last_name)s'
EMAIL_SIGNATURE = "The Mozilla PTO"
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


try:
    ## LDAP
    import ldap

    AUTHENTICATION_BACKENDS = (
       'apps.users.email_auth_backend.EmailOrUsernameModelBackend',
       'apps.users.auth.backends.MozillaLDAPBackend',
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
       'users.email_auth_backend.EmailOrUsernameModelBackend',
       'django.contrib.auth.backends.ModelBackend',
    )
