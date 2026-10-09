import unittest
from datetime import datetime, timezone

from unittest.mock import patch

from update import freshness_error, main, select_version, semver_key, update

NOW = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)


def metadata(latest: str, published: str, alpha: str = "0.2.1-alpha.1") -> dict:
    return {
        "dist-tags": {"latest": latest, "next": latest, "alpha": alpha},
        "time": {latest: published, alpha: "2026-10-07T11:00:00.000Z"},
        "versions": {version: {"name": "@deepseek-ai/dsh", "version": version}
                     for version in {latest, alpha, "0.2.1-alpha.2"}},
    }


class SelectVersionTest(unittest.TestCase):
    def test_latest_equal_to_packaged_is_no_change(self):
        self.assertIsNone(select_version(metadata("0.2.0-rc.2", "2026-09-29T09:56:27.792Z"), "0.2.0-rc.2"))

    def test_newer_latest_is_selected(self):
        self.assertEqual(select_version(metadata("0.2.0-rc.3", "2026-10-07T00:00:00.000Z"), "0.2.0-rc.2"), "0.2.0-rc.3")

    def test_newer_alpha_alone_is_ignored(self):
        self.assertIsNone(select_version(metadata("0.2.0-rc.2", "2026-09-29T09:56:27.792Z", alpha="0.3.0-alpha.1"), "0.2.0-rc.2"))

    def test_older_latest_does_not_downgrade_newer_packaged_alpha(self):
        self.assertIsNone(select_version(metadata("0.2.0-rc.2", "2026-09-01T00:00:00Z"), "0.2.1-alpha.2"))

    def test_same_core_release_is_newer_than_packaged_prerelease(self):
        self.assertEqual(select_version(metadata("0.2.1", "2026-10-07T00:00:00Z"), "0.2.1-alpha.2"), "0.2.1")

    def test_build_only_difference_is_no_change(self):
        self.assertIsNone(select_version(metadata("0.2.1+new", "2026-10-07T00:00:00Z"), "0.2.1+old"))

    def test_invalid_latest_or_packaged_is_rejected(self):
        for latest, packaged in [("latest", "0.2.1-alpha.2"), ("0.2.0-rc.2", "0.2")]:
            with self.subTest(latest=latest, packaged=packaged), self.assertRaises(ValueError):
                select_version(metadata(latest, "2026-10-07T00:00:00Z"), packaged)


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

    def test_packaged_ahead_of_old_latest_is_fresh(self):
        self.assertIsNone(freshness_error(metadata("0.2.0-rc.2", "2026-09-01T00:00:00Z"), "0.2.1-alpha.2", NOW))

    def test_same_core_newer_release_still_obeys_freshness_limit(self):
        self.assertIn("49h", freshness_error(metadata("0.2.1", "2026-10-05T11:00:00Z"), "0.2.1-alpha.2", NOW))


class SemVerTest(unittest.TestCase):
    def test_standard_precedence_chain(self):
        versions = [
            "1.0.0-alpha", "1.0.0-alpha.1", "1.0.0-alpha.beta", "1.0.0-beta",
            "1.0.0-beta.2", "1.0.0-beta.11", "1.0.0-rc.1", "1.0.0",
            "1.0.1-alpha.1", "1.0.1", "1.1.0-alpha.1", "1.1.0", "2.0.0-alpha.1",
        ]
        for older, newer in zip(versions, versions[1:]):
            with self.subTest(older=older, newer=newer):
                self.assertLess(semver_key(older), semver_key(newer))

    def test_numeric_prerelease_identifiers_are_not_lexicographic(self):
        self.assertLess(semver_key("0.2.1-alpha.2"), semver_key("0.2.1-alpha.10"))
        self.assertLess(semver_key("0.2.1-9"), semver_key("0.2.1-alpha"))

    def test_build_metadata_does_not_affect_precedence(self):
        self.assertEqual(semver_key("1.0.0+abc.01"), semver_key("1.0.0+def"))
        self.assertEqual(semver_key("1.0.0-alpha.2+abc"), semver_key("1.0.0-alpha.2"))

    def test_invalid_semver_is_rejected(self):
        for version in ["", "latest", "alpha", "v1.0.0", "1.0", "01.0.0", "1.01.0", "1.0.01",
                        "1.0.0-alpha.01", "1.0.0-", "1.0.0-alpha..2", "1.0.0+", "1.0.0+abc..def",
                        "^1.0.0", "1.0.0 ", "1.0.0\n", "1.0.0-α"]:
            with self.subTest(version=version), self.assertRaisesRegex(ValueError, "invalid SemVer"):
                semver_key(version)


class ExplicitVersionTest(unittest.TestCase):
    def test_explicit_newer_version_ignores_latest_channel(self):
        self.assertEqual(select_version(metadata("0.2.0-rc.2", "2026-09-01T00:00:00Z"),
                                        "0.2.0-rc.2", "0.2.1-alpha.2"), "0.2.1-alpha.2")

    def test_explicit_older_version_is_an_intentional_override(self):
        self.assertEqual(select_version(metadata("0.2.0-rc.2", "2026-09-01T00:00:00Z"),
                                        "0.2.1-alpha.2", "0.2.0-rc.2"), "0.2.0-rc.2")

    def test_explicit_equal_version_is_no_change(self):
        self.assertIsNone(select_version(metadata("0.2.0-rc.2", "2026-09-01T00:00:00Z"),
                                         "0.2.1-alpha.2", "0.2.1-alpha.2"))

    def test_explicit_invalid_version_is_rejected(self):
        for version in ["latest", "alpha", "^0.2.1", "0.2.1-alpha.02", "0.2.1-alpha.3"]:
            with self.subTest(version=version), self.assertRaises(ValueError):
                select_version(metadata("0.2.0-rc.2", "2026-09-01T00:00:00Z"), "0.2.0-rc.2", version)

    def test_exact_metadata_version_and_name_are_required(self):
        for field, value in [("version", "0.2.1-alpha.1"), ("name", "other-package")]:
            data = metadata("0.2.0-rc.2", "2026-09-01T00:00:00Z")
            data["versions"]["0.2.1-alpha.2"][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "does not match"):
                select_version(data, "0.2.0-rc.2", "0.2.1-alpha.2")

    def test_equal_override_still_validates_metadata(self):
        data = metadata("0.2.0-rc.2", "2026-09-01T00:00:00Z")
        del data["versions"]["0.2.1-alpha.2"]
        with self.assertRaisesRegex(ValueError, "no published version"):
            select_version(data, "0.2.1-alpha.2", "0.2.1-alpha.2")

    def test_invalid_override_fails_before_generated_file_writes(self):
        data = metadata("0.2.0-rc.2", "2026-09-01T00:00:00Z")
        data["versions"]["0.2.1-alpha.2"]["version"] = "0.2.1-alpha.1"
        with patch("update.HASHES") as hashes, patch("update.LOCK") as lock, \
             patch("update.generate_lock") as generate_lock, patch("update.write_hashes") as write_hashes:
            hashes.read_text.return_value = '{"version": "0.2.0-rc.2"}'
            with self.assertRaisesRegex(ValueError, "does not match"):
                update(data, "0.2.1-alpha.2")
            generate_lock.assert_not_called()
            write_hashes.assert_not_called()
            hashes.write_text.assert_not_called()
            lock.write_text.assert_not_called()

    def test_equal_override_does_not_write(self):
        with patch("update.HASHES") as hashes, patch("update.generate_lock") as generate_lock, \
             patch("update.write_hashes") as write_hashes, patch("builtins.print"):
            hashes.read_text.return_value = '{"version": "0.2.1-alpha.2"}'
            self.assertEqual(update(metadata("0.2.0-rc.2", "2026-09-01T00:00:00Z"), "0.2.1-alpha.2"), 0)
            generate_lock.assert_not_called()
            write_hashes.assert_not_called()

    def test_cli_version_reaches_updater(self):
        data = metadata("0.2.0-rc.2", "2026-09-01T00:00:00Z")
        with patch("sys.argv", ["update.py", "--version", "0.2.1-alpha.2"]), \
             patch("update.fetch_metadata", return_value=data), patch("update.update", return_value=0) as updater:
            self.assertEqual(main(), 0)
            updater.assert_called_once_with(data, "0.2.1-alpha.2")

    def test_cli_modes_are_mutually_exclusive(self):
        with patch("sys.argv", ["update.py", "--version", "0.2.1-alpha.2", "--check-freshness"]), \
             patch("sys.stderr"), self.assertRaises(SystemExit) as error:
            main()
        self.assertEqual(error.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
