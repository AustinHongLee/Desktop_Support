from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from launcher.core.state_store import AppStateStore
from launcher.plugins.iso_tools.profile import IsoNamingProfile, load_iso_naming_profile, save_iso_naming_profile
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


if __name__ == "__main__":
    unittest.main()
