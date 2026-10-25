from datetime import date

from unpinned.fleet.eol import BUILTIN, cycle_of, recommended_cycle, status_for

TODAY = date(2026, 10, 25)


def test_django_42_is_end_of_life_and_points_to_52_lts():
    s = status_for("django", "4.2.30", TODAY)
    assert s.status == "eol" and s.eol == "2026-04-07"
    assert s.days_overdue == (TODAY - date(2026, 4, 7)).days
    assert (s.recommended, s.recommended_latest) == ("5.2", "5.2.18")


def test_supported_lts_has_no_recommendation():
    s = status_for("django", "5.2.18", TODAY)
    assert s.status == "supported" and s.recommended is None


def test_expiring_window():
    # Rails 8.0 security support ends 2026-11-07: 13 days after TODAY.
    s = status_for("rails", "8.0.2", TODAY)
    assert s.status == "expiring" and s.days_left == 13


def test_node_cycles_are_major_only_and_lts_must_have_started():
    assert cycle_of("nodejs", "v20.11.1") == "20"
    s = status_for("nodejs", "20.11.1", TODAY)
    assert s.status == "eol"
    # Node 26 becomes LTS on 2026-10-28, after TODAY, so the target is 24.
    assert s.recommended == "24"


def test_mature_release_rule_for_non_lts_products():
    # Python 3.15 is two weeks old; recommend 3.14.
    assert recommended_cycle("python", TODAY, BUILTIN["python"])["cycle"] == "3.14"
    # Spring Boot 4.1 is < 180 days old; recommend 4.0.
    assert recommended_cycle("spring-boot", TODAY, BUILTIN["spring-boot"])["cycle"] == "4.0"


def test_spring_reports_commercial_support_separately():
    s = status_for("spring-boot", "2.7.18", TODAY)
    assert s.status == "eol" and s.extended_support == "2029-06-30"


def test_unknown_release():
    assert status_for("django", "9.9", TODAY).status == "unknown"
