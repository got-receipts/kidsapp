from django.conf import settings


def app_info(request):
    return {"app_version": settings.APP_VERSION}
