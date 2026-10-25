from pathlib import Path

import pytest

from unpinned import adapters
from unpinned.adapters.rails import bump as rails_bump
from unpinned.adapters.spring import bump as spring_bump


def test_roadmap_adapters_are_not_claimed_by_default(tmp_path: Path):
    with pytest.raises(ValueError, match="roadmap"):
        adapters.get("rails")
    assert adapters.get("rails", allow_roadmap=True).roadmap is True
    (tmp_path / "Gemfile").write_text("gem 'rails', '~> 6.1'\n")
    assert adapters.detect(tmp_path) is None
    assert adapters.detect(tmp_path, include_roadmap=True).name == "rails"


def test_rails_and_spring_bumps_touch_only_the_pin():
    p = rails_bump({"Gemfile": "gem 'pg'\ngem 'rails', '~> 6.1.7'\n"}, "7.2")
    assert p.files == {"Gemfile": "gem 'pg'\ngem 'rails', \"~> 7.2\"\n"}
    pom = (
        "<project><parent><artifactId>spring-boot-starter-parent</artifactId>"
        "<version>2.7.18</version></parent><version>1.0.0</version></project>"
    )
    p = spring_bump({"pom.xml": pom}, "3.5.16")
    assert "<version>3.5.16</version></parent><version>1.0.0</version>" in p.files["pom.xml"]
