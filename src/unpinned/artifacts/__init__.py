"""Parse raw runner artifacts without granting them sandbox provenance.

These parsers establish internal consistency, not authenticity. A future trusted
transport must independently bind downloaded files to the sandbox, source commit,
patch, commands and frozen tests before setting VerifyReport.artifacts_verified.
Model text, model-authored files and local fixture output cannot establish that.
"""

from .parse import ArtifactError, parse_django_probe, parse_junit

__all__ = ["ArtifactError", "parse_django_probe", "parse_junit"]
