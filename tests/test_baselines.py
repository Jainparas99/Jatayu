from unpinned.baselines import bump_requirements
from unpinned.pack import Bundle


def test_bump_only_touches_django_pin(tmp_path):
    b = Bundle(
        root=tmp_path,
        files={
            "requirements.txt": "Django>=4.2,<5\nrequests==2.0\n",
            "app/views.py": "import django\n",
        },
    )
    p = bump_requirements(b, "5.2.18")
    assert p.files == {"requirements.txt": "Django==5.2.18\nrequests==2.0\n"}
