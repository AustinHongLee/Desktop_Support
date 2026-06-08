from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from launcher.core.state_store import AppStateStore
from launcher.plugins.iso_tools.profile import (
    IsoNamingProfile,
    iso_naming_profile_history,
    load_iso_naming_profile,
    load_iso_naming_profile_draft,
    publish_iso_naming_profile,
    revert_iso_naming_profile,
    save_iso_naming_profile,
    save_iso_naming_profile_draft,
)
from launcher.plugins.iso_tools.serial_vision import SerialVisionRegion


class IsoProfileTests(unittest.TestCase):
    def test_profile_payload_round_trip(self) -> None:
        profile = IsoNamingProfile(
            serial_region=SerialVisionRegion(left=0.1, top=0.2, width=0.3, height=0.4),
            drawing_region=SerialVisionRegion(left=0.5, top=0.6, width=0.2, height=0.3),
            confidence_threshold=0.75,
            pattern="{serial}-{line}.pdf",
            iso_list_path=Path("C:/Work/iso.xlsx"),
            sheet_name="ISO",
            serial_col=2,
            line_col=5,
        )

        restored = IsoNamingProfile.from_payload(profile.to_payload())

        self.assertEqual(restored, profile)

    def test_profile_saves_to_state_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = AppStateStore(Path(tmp) / "state.json")
            folder = Path(tmp) / "pages"
            folder.mkdir()
            profile = IsoNamingProfile(pattern="{serial}--{line}.pdf", serial_col=0, line_col=1)

            save_iso_naming_profile(store, folder, profile)

            self.assertEqual(load_iso_naming_profile(AppStateStore(store.path), folder), profile)

    def test_draft_profile_does_not_replace_published_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = AppStateStore(Path(tmp) / "state.json")
            folder = Path(tmp) / "pages"
            folder.mkdir()
            published = IsoNamingProfile(pattern="{serial}--{line}.pdf", serial_col=0, line_col=1)
            draft = IsoNamingProfile(pattern="{serial}_{line}.pdf", serial_col=2, line_col=3)

            save_iso_naming_profile(store, folder, published)
            save_iso_naming_profile_draft(store, folder, draft)
            restored = AppStateStore(store.path)

            self.assertEqual(load_iso_naming_profile(restored, folder), published)
            self.assertEqual(load_iso_naming_profile_draft(restored, folder), draft)

    def test_publish_profile_promotes_draft_and_keeps_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = AppStateStore(Path(tmp) / "state.json")
            folder = Path(tmp) / "pages"
            folder.mkdir()
            old_profile = IsoNamingProfile(pattern="{serial}--{line}.pdf", serial_col=0, line_col=1)
            new_profile = IsoNamingProfile(pattern="{serial}_{line}.pdf", serial_col=2, line_col=3)

            save_iso_naming_profile(store, folder, old_profile)
            save_iso_naming_profile_draft(store, folder, new_profile)
            published = publish_iso_naming_profile(store, folder)
            restored = AppStateStore(store.path)
            history = iso_naming_profile_history(restored, folder)

            self.assertEqual(published, new_profile)
            self.assertEqual(load_iso_naming_profile(restored, folder), new_profile)
            self.assertIsNone(load_iso_naming_profile_draft(restored, folder))
            self.assertEqual(history[0]["profile"]["pattern"], old_profile.pattern)

    def test_revert_profile_restores_previous_published_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = AppStateStore(Path(tmp) / "state.json")
            folder = Path(tmp) / "pages"
            folder.mkdir()
            old_profile = IsoNamingProfile(pattern="{serial}--{line}.pdf", serial_col=0, line_col=1)
            new_profile = IsoNamingProfile(pattern="{serial}_{line}.pdf", serial_col=2, line_col=3)

            save_iso_naming_profile(store, folder, old_profile)
            save_iso_naming_profile_draft(store, folder, new_profile)
            publish_iso_naming_profile(store, folder)
            reverted = revert_iso_naming_profile(store, folder)
            restored = AppStateStore(store.path)
            history = iso_naming_profile_history(restored, folder)

            self.assertEqual(reverted, old_profile)
            self.assertEqual(load_iso_naming_profile(restored, folder), old_profile)
            self.assertEqual(history[0]["profile"]["pattern"], new_profile.pattern)


if __name__ == "__main__":
    unittest.main()
