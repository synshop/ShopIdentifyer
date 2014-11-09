# Django settings for moksha project.
import os
from command import CryptoUtil
from moksha import SettingsUtil

def relative_project_path(*x):
    return os.path.join(os.path.abspath(os.path.dirname(__file__)), *x)

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))

print ("Project Root: ")
print (PROJECT_ROOT)

DEBUG = True
TEMPLATE_DEBUG = DEBUG

ADMINS = (
    # ('BARE', 'bare@zappos.com'),
)

EXECUTOR = 'SaltExecutor'

MANAGERS = ADMINS

RUN_MODE = 'development'

ENCRYPTION_KEY = SettingsUtil.EncryptionKey.get(RUN_MODE == 'development')

qa_netscaler_password  = CryptoUtil.decrypt('0R2VdugNjStBJBzWWbSJAw==', ENCRYPTION_KEY)
web_netscaler_password = CryptoUtil.decrypt('0R2VdugNjStBJBzWWbSJAw==', ENCRYPTION_KEY)
dmz_netscaler_password = CryptoUtil.decrypt('0R2VdugNjStBJBzWWbSJAw==', ENCRYPTION_KEY)
wms_netscaler_password = CryptoUtil.decrypt('0R2VdugNjStBJBzWWbSJAw==', ENCRYPTION_KEY)

LOAD_BALANCERS = {
    'qans': {
        'lb-type':  'netscaler',
        'hostname': 'qans.zappos.net',
        'username': 'bounce',
        'password': qa_netscaler_password,
    },

    'webns': {
        'lb-type':  'netscaler',
        'hostname': 'webns.zappos.net',
        'username': 'bounce',
        'password': web_netscaler_password,
    },

    'dmzns': {
        'lb-type':  'netscaler',
        'hostname': 'dmzns.zappos.net',
        'username': 'bounce',
        'password': dmz_netscaler_password,
    },

    'wmsns': {
        'lb-type':  'netscaler',
        'hostname': 'wmsns.wms.zappos.net',
        'username': 'bounce',
        'password': wms_netscaler_password,
    }    
}

password = CryptoUtil.decrypt('w26pAotDwh16BjjnjQF4iQ==', ENCRYPTION_KEY)

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',     # Add 'postgresql_psycopg2', 'mysql', 'sqlite3' or 'oracle'.
        'NAME': 'moksha_prod',                    # Or path to database file if using sqlite3.
        'USER': 'moksha_prod',                    # Not used with sqlite3.
        'PASSWORD': password,                     # Not used with sqlite3.
        'HOST': 'dbadmin01.zappos.net',             # Set to empty string for localhost. Not used with sqlite3.
        'PORT': '3306',                           # Set to empty string for default. Not used with sqlite3.
    }
}

DEPLOY_CHAT_ROOM='#level1'
COMMAND_CHAT_ROOM='#deploy'

# Local time zone for this installation. Choices can be found here:
# http://en.wikipedia.org/wiki/List_of_tz_zones_by_name
# although not all choices may be available on all operating systems.
# On Unix systems, a value of None will cause Django to use the same
# timezone as the operating system.
# If running in a Windows environment this must be set to the same as your
# system time zone.
TIME_ZONE = 'America/Los_Angeles'

# Language code for this installation. All choices can be found here:
# http://www.i18nguy.com/unicode/language-identifiers.html
LANGUAGE_CODE = 'en-us'

SITE_ID = 1

# If you set this to False, Django will make some optimizations so as not
# to load the internationalization machinery.
USE_I18N = True

# If you set this to False, Django will not format dates, numbers and
# calendars according to the current locale.
USE_L10N = True

# If you set this to False, Django will not use timezone-aware datetimes.
USE_TZ = True

# Absolute filesystem path to the directory that will hold user-uploaded files.
# Example: "/home/media/media.lawrence.com/media/"
MEDIA_ROOT = ''

# URL that handles the media served from MEDIA_ROOT. Make sure to use a
# trailing slash.
# Examples: "http://media.lawrence.com/media/", "http://example.com/media/"
MEDIA_URL = ''

ADMIN_MEDIA_PREFIX = '/static/admin/'

# Absolute path to the directory static files should be collected to.
# Don't put anything in this directory yourself; store your static files
# in apps' "static/" subdirectories and in STATICFILES_DIRS.
# Example: "/home/media/media.lawrence.com/static/"
STATIC_ROOT = '/Users/bmunroe/dj-ango/moksha/static'

# URL prefix for static files.
# Example: "http://media.lawrence.com/static/"
STATIC_URL = '/static/'

# Additional locations of static files
STATICFILES_DIRS = (
    # Put strings here, like "/home/html/static" or "C:/www/django/static".
    # Always use forward slashes, even on Windows.
    # Don't forget to use absolute paths, not relative paths.
    '/home/static',
)

# List of finder classes that know how to find static files in
# various locations.
STATICFILES_FINDERS = (
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
#    'django.contrib.staticfiles.finders.DefaultStorageFinder',
)

# Make this unique, and don't share it with anybody.
SECRET_KEY = 'x_xb!-^=*_xrlhxbyka+qqyg3@ix4y&amp;!uot=@pl&amp;9v08exj7bv'

# List of callables that know how to import templates from various sources.
TEMPLATE_LOADERS = (
    'django.template.loaders.filesystem.Loader',
    'django.template.loaders.app_directories.Loader',
#     'django.template.loaders.eggs.Loader',
)

MIDDLEWARE_CLASSES = (
    'django.middleware.common.CommonMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    #
    # This caused the :  Reason given for failure:   CSRF token missing or incorrect.
    #'django.middleware.csrf.CsrfViewMiddleware',

    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    # Uncomment the next line for simple clickjacking protection:
    # 'django.middleware.clickjacking.XFrameOptionsMiddleware',
    #'debug_toolbar.middleware.DebugToolbarMiddleware',
)

#INTERNAL_IPS = ('0.0.0.0',)

ROOT_URLCONF = 'moksha.urls'

# Python dotted path to the WSGI application used by Django's runserver.
WSGI_APPLICATION = 'moksha.wsgi.application'

# TEMPLATE_DIRS = (
    # Put strings here, like "/home/html/django_templates" or "C:/www/django/templates".
    # Always use forward slashes, even on Windows.
    # Don't forget to use absolute paths, not relative paths.
    # '/home/ytran/gitrepo/integration/moksha/templates',
    # relative_project_path('templates'),
# )

# TEMPLATES_DIR = os.path.join(PROJECT_PATH, 'templates')

TEMPLATE_DIRS = (
     PROJECT_ROOT + "/templates/",
)

INSTALLED_APPS = (
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.sites',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # requires by tiote:
    'django.contrib.sessions',
    # Uncomment the next line to enable the admin:
    'django.contrib.admin',
    # Uncomment the next line to enable admin documentation:
    # 'django.contrib.admindocs',
    'bootstrap_toolkit',
    'bootstrap',
    'crispy_forms',
    'tastypie',
    #'tiote',
    #'menus',
#    'sitetree',
    'db',
#    'api',
    'config',
    'chat_client',
    'django_logtail',
    'south',
    'isgold',
    'poolflip',
)

#TEMPLATE_CONTEXT_PROCESSORS = (
#    'django.contrib.auth.context_processors.auth',
#    'django.core.context_processors.debug',
#    'django.core.context_processors.i18n',
#    'django.core.context_processors.media',
#    'django.core.context_processors.static',
#    'django.core.context_processors.tz',
#    'django.contrib.messages.context_processors.messages',
#    'django.core.context_processors.request',
#    'django.contrib.auth.context_processors.auth',
#)

# A sample logging configuration. The only tangible logging
# performed by this configuration is to send an email to
# the site admins on every HTTP 500 error when DEBUG=False.
# See http://docs.djangoproject.com/en/dev/topics/logging for
# more details on how to customize your logging configuration.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '%(asctime)s [%(levelname)s] [stage=%(stage)s, server=%(server_name)s, command=%(command)s] %(module)s - %(message)s'
        },
        'simple': {
            'format': '[%(levelname)s] %(message)s'
        },
    },
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse'
        },
        'thread_local_context': {
            '()': 'command.logcontext.ThreadLocalLogContextFilter'
        },
    },
    'handlers': {
        'console':{
            'level':'DEBUG',
            'class':'logging.StreamHandler',
            'formatter' : 'verbose',
            'filters' : ['thread_local_context'],
        },
        'filehandle':{
            'level':'DEBUG',
            'class':'logging.handlers.RotatingFileHandler',
            'filename':'/tmp/django.log',
            'formatter' : 'verbose',
            'filters' : ['thread_local_context'],
            'maxBytes': 1024*1024*5,
            
        },
        'mail_admins': {
            'level': 'ERROR',
            'filters': ['require_debug_false'],
            'class': 'django.utils.log.AdminEmailHandler'
        }
    },
    'root': {
        'handlers':['filehandle'],
        'level':'INFO',
    },
    'loggers': {
        'django': {
            'handlers':['filehandle'],
            'propagate': True,
            'level':'INFO',
        },
        'django.request': {
            'handlers': ['mail_admins'],
            'level': 'ERROR',
            'propagate': True,
        },
    }
}

# tastypie:
TASTYPIE_FULL_DEBUG = True

# Django-logtail settings
LOGTAIL_UPDATE_INTERVAL = 2000

LOGTAIL_FILES = {
        'django': '/tmp/django.log',
}
