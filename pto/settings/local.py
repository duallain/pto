# Is this a development instance? Set this to True on development/master
# instances and False on stage/prod.


#from . import base
#INSTALLED_APPS = base.INSTALLED_APPS + ('debug_toolbar',)
#MIDDLEWARE_CLASSES = base.MIDDLEWARE_CLASSES + ('debug_toolbar.middleware.DebugToolbarMiddleware',)
#INTERNAL_IPS = ('127.0.0.1',)
DEBUG_PROPAGATE_EXCEPTIONS = True
DEV = DEBUG = TEMPLATE_DEBUG = True
#DEV = DEBUG = TEMPLATE_DEBUG = 0
SECRET_KEY = 'simetugh'
TEMPLATE_STRING_IF_INVALID = '!{ %s }'
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
PWD_ALGORITHM = 'sha521'
SESSION_COOKIE_SECURE = False  # if you run http://localhost:8000


#TEST_RUNNER = 'django.test.simple.DjangoTestSuiteRunner'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'pto',
        'USER': 'root',
        'PASSWORD': 'test123',
        'HOST': '',
        'PORT': '3306',
        'OPTIONS': {
            'init_command': 'SET storage_engine=InnoDB',
            'charset' : 'utf8',
            'use_unicode' : True,
        },
        'TEST_CHARSET': 'utf8',
        'TEST_COLLATION': 'utf8_general_ci',
    },
}

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake'
    }
}

#AUTH_LDAP_HOST = 'ldap://pm-ns.mozilla.org'
AUTH_LDAP_SERVER_URI = 'ldap://pm-ns.mozilla.org'
AUTH_LDAP_BIND_DN = 'uid=bind-pto,ou=logins,dc=mozilla'
AUTH_LDAP_BIND_PASSWORD = 'yg50MAjJqYDMS3Liny'
AUTH_LDAP_START_TLS = False

#import ldap
#AUTH_LDAP_GLOBAL_OPTIONS = {
#  ldap.OPT_DEBUG_LEVEL: 4095
#}

#AUTH_LDAP_SERVER_URI = 'ldap://pm-ns.mozilla.org'
#AUTH_LDAP_BIND_DN = 'uid=binduser,ou=logins,dc=mozilla'
#AUTH_LDAP_BIND_PASSWORD = 'Z6bp3Zrh'
