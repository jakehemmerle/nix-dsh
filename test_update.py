import unittest
from datetime import datetime, timezone

from update import freshness_error, select_version

NOW = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)


def metadata(latest: str, published: str, alpha: str = "0.2.1-alpha.1") -> dict:
    return {
        "dist-tags": {"latest": latest, "next": latest, "alpha": alpha},
        "time": {latest: published, alpha: "2026-10-07T11:00:00.000Z"},
    }


class SelectVersionTest(unittest.TestCase):
    def test_latest_equal_to_packaged_is_no_change(self):
        self.assertIsNone(select_version(metadata("0.2.0-rc.2", "2026-09-29T09:56:27.792Z"), "0.2.0-rc.2"))

    def test_newer_latest_is_selected(self):
        self.assertEqual(select_version(metadata("0.2.0-rc.3", "2026-10-07T00:00:00.000Z"), "0.2.0-rc.2"), "0.2.0-rc.3")

    def test_newer_alpha_alone_is_ignored(self):
        self.assertIsNone(select_version(metadata("0.2.0-rc.2", "2026-09-29T09:56:27.792Z", alpha="0.3.0-alpha.1"), "0.2.0-rc.2"))


class FreshnessTest(unittest.TestCase):
    def test_packaged_latest_is_fresh(self):
        self.assertIsNone(freshness_error(metadata("0.2.0-rc.2", "2026-09-01T00:00:00.000Z"), "0.2.0-rc.2", NOW))

    def test_one_day_lag_passes(self):
        self.assertIsNone(freshness_error(metadata("0.2.0-rc.3", "2026-10-06T12:00:00.000Z"), "0.2.0-rc.2", NOW))

    def test_exactly_48_hours_passes(self):
        self.assertIsNone(freshness_error(metadata("0.2.0-rc.3", "2026-10-05T12:00:00.000Z"), "0.2.0-rc.2", NOW))

    def test_49_hours_fails_naming_versions_and_age(self):
        self.assertEqual(
            freshness_error(metadata("0.2.0-rc.3", "2026-10-05T11:00:00.000Z"), "0.2.0-rc.2", NOW),
            "npm latest 0.2.0-rc.3 has been unpackaged for 49h (packaged: 0.2.0-rc.2, limit: 48h)",
        )


if __name__ == "__main__":
    unittest.main()
