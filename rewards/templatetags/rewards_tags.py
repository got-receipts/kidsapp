from django import template

register = template.Library()


@register.filter
def dollars(cents):
    sign = "-" if cents < 0 else ""
    return f"{sign}${abs(cents) / 100:.2f}"
