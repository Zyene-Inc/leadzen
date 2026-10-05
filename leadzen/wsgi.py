import os

from django.core.wsgi import get_wsgi_application
from leadzen.production import validate_environment

validate_environment()
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "leadzen.settings")

application = get_wsgi_application()
