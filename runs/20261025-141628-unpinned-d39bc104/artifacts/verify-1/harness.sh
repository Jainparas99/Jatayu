#!/usr/bin/env bash
# Jatayu verification harness (controller-owned; do not edit).
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="$HERE/out"; W="$HERE/work"
rm -rf "$OUT" "$W"; mkdir -p "$OUT" "$W"
rec() { echo "$2" > "$OUT/$1"; }

git clone --quiet "https://github.com/Jainparas99/jatayu-demo-app" "$W/repo" > "$OUT/clone.log" 2>&1 || { rec clone.exit $?; echo done > "$OUT/DONE"; exit 0; }
cd "$W/repo"
git checkout --quiet --detach "554e82b8150f656e0de8ea55c6fbb80ba8a34579" >> "$OUT/clone.log" 2>&1
git rev-parse HEAD > "$OUT/head.txt"

# Apply the patch exactly: whole-file replacements from the archive, then deletions.
tar xzf "$HERE/patch.tar.gz" --no-same-owner -C "$W/repo" >> "$OUT/clone.log" 2>&1
while IFS= read -r p; do [ -n "$p" ] && rm -f -- "$W/repo/$p"; done < "$HERE/deletes.txt"

python3 --version > "$OUT/python.txt" 2>&1
python3 -m venv "$W/venv" && . "$W/venv/bin/activate"
{
  pip install --disable-pip-version-check -q -r requirements.txt
  pip install --disable-pip-version-check -q "Django==5.2.18" "unittest-xml-reporting>=3.2"
} > "$OUT/install.log" 2>&1
rec install.exit $?
python -c "import django; print(django.get_version())" > "$OUT/django.txt" 2>> "$OUT/install.log"

# Point Django's test runner at a JUnit writer without editing the project.
ORIG="$(python - <<'PY'
import re
m = re.search(r"DJANGO_SETTINGS_MODULE['\"]\s*,\s*['\"]([\w.]+)['\"]", open("manage.py").read())
print(m.group(1) if m else "")
PY
)"
ORIG="${ORIG:-${DJANGO_SETTINGS_MODULE:-}}"
mkdir -p "$W/shim"
cat > "$W/shim/jatayu_junit_settings.py" <<PY
from $ORIG import *  # noqa: F401,F403
TEST_RUNNER = "xmlrunner.extra.djangotestrunner.XMLTestRunner"
TEST_OUTPUT_DIR = "$OUT"
TEST_OUTPUT_FILE_NAME = "junit.xml"
PY
PYTHONPATH="$W/shim:$W/repo" timeout 900 python manage.py test --settings=jatayu_junit_settings --noinput --verbosity 2 > "$OUT/tests.stdout" 2> "$OUT/tests.stderr"
rec tests.exit $?
timeout 300 python manage.py check > "$OUT/check.stdout" 2> "$OUT/check.stderr"
rec check.exit $?

if [ -n "security_probe.py" ] && [ -f "security_probe.py" ]; then
  sha256sum "security_probe.py" | cut -d' ' -f1 > "$OUT/probe.sha256"
  timeout 300 python "security_probe.py" > "$OUT/probe.stdout" 2> "$OUT/probe.stderr"
  rec probe.exit $?
fi
echo done > "$OUT/DONE"
