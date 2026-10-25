"""Fleet: find every app stuck on an end-of-life framework, across many repos.

Jatayu's upgrade engine fixes one repo. Fleet answers the question a security team asks
first: *which* of our repos are running unsupported frameworks or runtimes, how overdue
are they, and which can Jatayu upgrade today? It reads only dependency manifests, so a
scan of dozens of repos takes seconds and never sends code to a model.
"""

from .eol import CATALOG_AS_OF, status_for
from .scan import RepoReport, scan_many, scan_target

__all__ = ["CATALOG_AS_OF", "RepoReport", "scan_many", "scan_target", "status_for"]
