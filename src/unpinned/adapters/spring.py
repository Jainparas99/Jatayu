"""Spring Boot adapter — ROADMAP (roadmap=True). Not proven by a saved run yet.

The classic Spring Boot 2.7 → 3.x jump (javax → jakarta, Java 17) is a textbook
"touches every file" upgrade. Baseline B1 would be OpenRewrite's recipe.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..parse import Patch
from .base import Adapter, Files

GUIDE = "https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide"
_POM_PARENT = re.compile(
    r"(<parent>.*?<artifactId>\s*spring-boot-starter-parent\s*</artifactId>.*?<version>\s*)"
    r"[^<\s]+",
    re.S,
)
_GRADLE = re.compile(r"""(org\.springframework\.boot["')]*\s*version\s*["'])[^"']+""")


def bump(files: Files, target: str) -> Patch:
    p = Patch()
    for path, content in files.items():
        name = Path(path).name
        if name == "pom.xml":
            new = _POM_PARENT.sub(lambda m: m.group(1) + target, content, count=1)
        elif name in ("build.gradle", "build.gradle.kts"):
            new = _GRADLE.sub(lambda m: m.group(1) + target, content, count=1)
        else:
            continue
        if new != content:
            p.files[path] = new
    return p


def detect(root: Path) -> bool:
    for name in ("pom.xml", "build.gradle", "build.gradle.kts"):
        f = root / name
        if f.is_file() and "spring-boot" in f.read_text(errors="ignore"):
            return True
    return False


SPRING_BOOT = Adapter(
    name="spring-boot",
    framework="Spring Boot",
    language="Java",
    include_suffixes=frozenset(
        {".java", ".kt", ".xml", ".gradle", ".kts", ".properties", ".yml", ".yaml"}
    ),
    include_names=frozenset({"pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle"}),
    bump=bump,
    notes_urls=lambda a, b: [GUIDE],
    install_command="./mvnw -q -DskipTests install || ./gradlew assemble",
    test_command="./mvnw test || ./gradlew test",
    check_command=None,
    baseline_command=(
        "./mvnw -U org.openrewrite.maven:rewrite-maven-plugin:run "
        "-Drewrite.recipeArtifactCoordinates=org.openrewrite.recipe:rewrite-spring:RELEASE "
        "-Drewrite.activeRecipes=org.openrewrite.java.spring.boot3.UpgradeSpringBoot_3_0"
    ),
    detect=detect,
    roadmap=True,
)
