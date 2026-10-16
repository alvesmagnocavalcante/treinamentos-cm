from django.templatetags.static import static
from django.urls import reverse
from jinja2 import Environment


def environment(**options):
    environment = Environment(**options)
    environment.globals.update(static=static, url=reverse)
    return environment
