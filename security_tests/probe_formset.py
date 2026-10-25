"""Owned, in-memory application fixture for the editable-PK formset regression.

Run as a standalone script in each pinned Django environment. This demonstrates
this fixture only; it does not establish exposure in an unrelated target app.
No network requests, credentials or external databases are used.
"""

import hashlib
import json
import sys
from importlib.metadata import version
from pathlib import Path

import django
from django.conf import settings

settings.configure(
    SECRET_KEY="disposable-local-regression-fixture",
    INSTALLED_APPS=[],
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
    ROOT_URLCONF=__name__,
    ALLOWED_HOSTS=["testserver"],
    DEFAULT_AUTO_FIELD="django.db.models.BigAutoField",
)
django.setup()

from django.db import connection, models  # noqa: E402
from django.forms import modelformset_factory  # noqa: E402
from django.http import JsonResponse  # noqa: E402
from django.test import Client  # noqa: E402
from django.urls import path  # noqa: E402


class Document(models.Model):
    key = models.CharField(primary_key=True, max_length=40)
    owner = models.CharField(max_length=40)
    body = models.CharField(max_length=200)

    class Meta:
        app_label = "unpinned_probe"


def edit_documents(request):
    formset_class = modelformset_factory(Document, fields=("key", "body"), can_delete=True, extra=0)
    # The fixture represents Alice's authenticated session. Bob's record is
    # deliberately outside its limiting queryset.
    formset = formset_class(request.POST, queryset=Document.objects.filter(owner="alice"))
    if not formset.is_valid():
        return JsonResponse({"valid": False}, status=400)
    formset.save()
    return JsonResponse({"valid": True})


urlpatterns = [path("documents/", edit_documents)]


def probe():
    with connection.schema_editor() as editor:
        editor.create_model(Document)
    Document.objects.create(key="alice-document", owner="alice", body="original")
    Document.objects.create(key="bob-document", owner="bob", body="private")
    client = Client()
    management = {"form-TOTAL_FORMS": "1", "form-INITIAL_FORMS": "1", "form-MAX_NUM_FORMS": "0"}
    benign = client.post(
        "/documents/",
        {
            **management,
            "form-0-key": "alice-document",
            "form-0-body": "edited",
        },
    )
    benign_ok = (
        benign.status_code == 200 and Document.objects.get(pk="alice-document").body == "edited"
    )
    forged = client.post(
        "/documents/",
        {
            **management,
            "form-0-key": "bob-document",
            "form-0-body": "private",
            "form-0-DELETE": "on",
        },
    )
    if forged.status_code != 200:
        outcome = "error"
    else:
        outcome = "blocked" if Document.objects.filter(pk="bob-document").exists() else "vulnerable"
    return {
        "scope": "purpose-built in-memory application fixture; not a target-repo claim",
        "case": "CVE-2026-87975 editable-primary-key formset regression",
        "django_version": django.get_version(),
        "python_version": sys.version,
        "dependencies": {name: version(name) for name in ("Django", "asgiref", "sqlparse")},
        "probe_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "benign_control_passed": benign_ok,
        "outcome": outcome,
        "http_status": forged.status_code,
    }


if __name__ == "__main__":
    print(json.dumps(probe(), sort_keys=True))
