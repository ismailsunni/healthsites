# -*- coding: utf-8 -*-
from .base import *  # noqa
import os

# Extra installed apps
INSTALLED_APPS += (
    'pipeline',
    'social.apps.django_app.default',
    'pg_fts',
    'django_forms_bootstrap',
    'celery'
)

# define template function (example for underscore)
# PIPELINE_TEMPLATE_FUNC = '_.template'

# enable cached storage - requires uglify.js (node.js)
STATICFILES_STORAGE = 'pipeline.storage.PipelineCachedStorage'


STATICFILES_FINDERS = (
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
    'pipeline.finders.PipelineFinder'
)

AUTHENTICATION_BACKENDS = (
    'social.backends.openstreetmap.OpenStreetMapOAuth',
    'social.backends.twitter.TwitterOAuth',
    'social.backends.github.GithubOAuth2',
    'social.backends.google.GoogleOAuth2',
    'social.backends.facebook.FacebookOAuth2',
    'django.contrib.auth.backends.ModelBackend',
)

TEMPLATE_CONTEXT_PROCESSORS = (
    'django.contrib.auth.context_processors.auth',
    'django.core.context_processors.debug',
    'django.core.context_processors.i18n',
    'django.core.context_processors.media',
    'django.core.context_processors.static',
    'django.core.context_processors.tz',
    'django.contrib.messages.context_processors.messages',
    'social.apps.django_app.context_processors.backends',
    'social.apps.django_app.context_processors.login_redirect',
)

BROKER_URL = 'amqp://guest:guest@%s:5672//' % os.environ['RABBITMQ_HOST']

CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
