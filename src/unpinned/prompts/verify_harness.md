You are executing a fixed verification script. Do not write, edit, create or delete any files yourself, and do not install anything outside the script. Never run `git push` and never open a pull request.

1. Find the directory `{harness_dir}` that contains `verify.sh` (it was mounted into your workspace; check the current directory first, then search with `find / -type f -name verify.sh -path '*{harness_dir}*' 2>/dev/null`).
2. Run exactly: `bash <that directory>/verify.sh`
3. It may take several minutes. When it exits, run `ls <that directory>/out`.

Reply with ONLY this JSON: {{"harness_dir": "<absolute path of {harness_dir}>", "script_exit": <int>, "out_files": [<file names>]}}
