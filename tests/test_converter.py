import unittest
import importlib.util
from pathlib import Path


_CONVERTER_PATH = Path(__file__).resolve().parents[1] / "app" / "converter.py"
_SPEC = importlib.util.spec_from_file_location("converter_module", _CONVERTER_PATH)
assert _SPEC and _SPEC.loader
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)

THEMES = _MODULE.THEMES
_apply_theme_to_svg = _MODULE._apply_theme_to_svg


class ApplyThemeToSvgTests(unittest.TestCase):
    def test_injects_style_and_background_rect(self) -> None:
        svg_in = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="120" height="40">'
            "<style>.svgbob text{fill:black;stroke:black;}</style>"
            '<g class="svgbob"><text x="10" y="20">Hello</text></g>'
            "</svg>"
        )

        out = _apply_theme_to_svg(svg_in, THEMES["dark"])

        self.assertIn("stroke:none!important;", out)
        self.assertIn("font-family:'DejaVu Sans Mono', Menlo, Consolas, monospace!important;", out)
        self.assertIn('<rect width="100%" height="100%" fill="#1e1e1e"/>', out)
        self.assertIn(".svgbob line,.svgbob path,.svgbob circle,.svgbob rect,.svgbob polygon{", out)

    def test_handles_xml_preamble(self) -> None:
        svg_in = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<svg xmlns="http://www.w3.org/2000/svg"><g class="svgbob"></g></svg>'
        )

        out = _apply_theme_to_svg(svg_in, THEMES["light"])

        self.assertIn('<rect width="100%" height="100%" fill="#ffffff"/>', out)
        self.assertIn("<style>", out)


if __name__ == "__main__":
    unittest.main()
