from __future__ import annotations

import unittest

from launcher.ui.edge_positioner import EdgePositioner, ScreenArea


class EdgePositionerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.positioner = EdgePositioner()
        self.area = ScreenArea(x=100, y=50, width=1920, height=1040)

    def test_expanded_top_spans_available_width(self) -> None:
        placement = self.positioner.compute(self.area, edge="top", collapsed=False)

        self.assertEqual((placement.x, placement.y, placement.width, placement.height), (100, 50, 1920, 40))
        self.assertEqual(placement.orientation, "horizontal")

    def test_expanded_bottom_sticks_to_bottom(self) -> None:
        placement = self.positioner.compute(self.area, edge="bottom", collapsed=False)

        self.assertEqual((placement.x, placement.y, placement.width, placement.height), (100, 1050, 1920, 40))
        self.assertEqual(placement.orientation, "horizontal")

    def test_expanded_left_is_vertical_strip(self) -> None:
        placement = self.positioner.compute(self.area, edge="left", collapsed=False)

        self.assertEqual((placement.x, placement.y, placement.width, placement.height), (100, 50, 118, 1040))
        self.assertEqual(placement.orientation, "vertical")

    def test_expanded_right_is_vertical_strip(self) -> None:
        placement = self.positioner.compute(self.area, edge="right", collapsed=False)

        self.assertEqual((placement.x, placement.y, placement.width, placement.height), (1902, 50, 118, 1040))
        self.assertEqual(placement.orientation, "vertical")

    def test_collapsed_top_is_centered_tail(self) -> None:
        placement = self.positioner.compute(self.area, edge="top", collapsed=True)

        self.assertEqual((placement.x, placement.y, placement.width, placement.height), (980, 50, 160, 18))

    def test_collapsed_top_uses_tail_offset(self) -> None:
        placement = self.positioner.compute(self.area, edge="top", collapsed=True, tail_offset=0.25)

        self.assertEqual((placement.x, placement.y, placement.width, placement.height), (540, 50, 160, 18))

    def test_collapsed_right_is_centered_tail(self) -> None:
        placement = self.positioner.compute(self.area, edge="right", collapsed=True)

        self.assertEqual((placement.x, placement.y, placement.width, placement.height), (2002, 504, 18, 132))

    def test_collapsed_right_uses_tail_offset(self) -> None:
        placement = self.positioner.compute(self.area, edge="right", collapsed=True, tail_offset=0.75)

        self.assertEqual((placement.x, placement.y, placement.width, placement.height), (2002, 731, 18, 132))

    def test_invalid_edge_falls_back_to_top(self) -> None:
        placement = self.positioner.compute(self.area, edge="weird", collapsed=False)

        self.assertEqual((placement.x, placement.y, placement.width, placement.height), (100, 50, 1920, 40))

    def test_nearest_edge(self) -> None:
        self.assertEqual(self.positioner.nearest_edge(self.area, 110, 520), "left")
        self.assertEqual(self.positioner.nearest_edge(self.area, 2010, 520), "right")
        self.assertEqual(self.positioner.nearest_edge(self.area, 1000, 55), "top")
        self.assertEqual(self.positioner.nearest_edge(self.area, 1000, 1080), "bottom")


if __name__ == "__main__":
    unittest.main()
