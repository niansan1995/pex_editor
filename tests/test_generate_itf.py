"""验证独立参数配置、从高到低层序、通孔连接与空行保留。"""

import importlib.util
import json
import re
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("generate_itf", ROOT / "scripts/generate_itf.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class GenerateTests(unittest.TestCase):
    """覆盖主要生成流程及常用配置。"""

    def test_repository_stack_and_all_corners(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            paths = MODULE.generate(ROOT / "metal_option.json", output)
            self.assertEqual(len(paths), 9)
            for path in paths:
                content = path.read_text(encoding="utf-8")
                self.assertTrue(content.startswith("# 全局参数定义可在此补充。\nTECHNOLOGY = demo_" + path.parent.name + "_" + path.stem + "\n\n"))
                conductors = re.findall(r"^CONDUCTOR\s+(\w+)\s+\{", content, re.M)
                self.assertEqual(conductors, ["ALPA", "metal5", "metal4", "metal3", "metal2", "metal1", "npoly", "ppoly", "ndiff", "pdiff"])
                first_via = content.index("\nVIA ")
                self.assertNotIn("\nCONDUCTOR ", content[first_via:])
                self.assertNotIn("\nDIELECTRIC ", content[first_via:])
                via_names = re.findall(r"^VIA (\w+) ", content, re.M)
                self.assertEqual(via_names[:5], ["PA", "V4", "V3", "V2", "V1"])
                for i in range(1, 5):
                    self.assertIn("VIA V" + str(i) + " { FROM=metal" + str(i) + " TO=metal" + str(i + 1) + " RPV=10 }", content)
                self.assertIn("VIA PA { FROM=metal5 TO=ALPA RPV=10 }", content)
                self.assertIn("VIA npolyCont { FROM=npoly TO=metal1 AREA=0.01 RPV=10 }", content)
                thickness, resistance = {"CMAX": ("0.27", "0.065"), "TYPICAL": ("0.3", "0.05"), "CMIN": ("0.33", "0.035")}[path.stem]
                dielectric_thickness = {"CMAX": "0.045", "TYPICAL": "0.05", "CMIN": "0.055"}[path.stem]
                for i in range(1, 4):
                    self.assertIn("CONDUCTOR metal" + str(i) + " { THICKNESS=" + thickness + " RPSQ=" + resistance, content)
                    self.assertIn("DIELECTRIC IMD" + str(i) + "b { THICKNESS=" + dielectric_thickness + " ER=4.0 }", content)
                # 平齐介电层与金属共用厚度，方阻按相对典型值的比例变化。
                for layer, metal_tk, metal_rsh in re.findall(r"^CONDUCTOR (metal\d+|ALPA) \{ THICKNESS=(\S+) RPSQ=(\S+)", content, re.M):
                    self.assertEqual(metal_rsh, resistance)
                    if layer.startswith("metal"):
                        self.assertIn("DIELECTRIC IMD" + layer[5:] + "c2 { THICKNESS=" + metal_tk, content)
                self.assertIn("}\n\nDIELECTRIC IMD4c2", content)
                self.assertNotIn("{{", content)
                self.assertEqual({p.name for p in path.parent.iterdir()}, {"CMAX.itf", "TYPICAL.itf", "CMIN.itf"})
            option = paths[0].parent.name
            single = MODULE.generate(ROOT / "metal_option.json", output / "selected", "cmax", option)
            self.assertEqual(len(single), 1)
            self.assertEqual(single[0].read_bytes(), (output / option / "CMAX.itf").read_bytes())

    def test_custom_names_inline_values_and_header(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            options = json.loads((ROOT / "metal_option.json").read_text(encoding="utf-8"))
            options["parameter_file"] = str(ROOT / "parameters.json")
            options["header_template"] = "header.j2"
            (root / "header.j2").write_text("GLOBAL={{ GLOBAL_ER }};{{ CORNER }}\n\n", encoding="utf-8")
            options["parameters"] = {"GLOBAL_ER": [4.1, 4.0, 3.9]}
            for field in ("suffix_templates", "via_templates"):
                options[field] = [str(ROOT / path) for path in options[field]]
            for component in options["components"].values():
                component["template"] = str(ROOT / component["template"])
            options["naming"]["metal"] = "fab{{ MID }}"
            options["components"]["ALPA2"]["name"] = "pad{{ PAD_ID }}"
            option = "1P5M_3Ic_1TMc_1MTTc_ALPA2_MIM10"
            layers = options["metal_options"][option]
            layers[layers.index("MTT")] = {"component": "MTT", "name": "top{{ MID }}"}
            options["components"]["INTER_METAL"].setdefault("parameters", {}).update(TK_M=["0.099", "0.123", "0.150"], TK_IMDB="0.067")
            path = root / "metal_option.json"
            path.write_text(json.dumps(options), encoding="utf-8")
            paths = MODULE.generate(path, root / "out", "all", option)
            for path, er, thickness in zip(paths, ("4.1", "4.0", "3.9"), ("0.099", "0.123", "0.150")):
                content = path.read_text(encoding="utf-8")
                self.assertTrue(content.startswith("GLOBAL=" + er + ";" + path.stem + "\n\n"))
                for i in range(1, 4):
                    self.assertIn("CONDUCTOR fab" + str(i) + " { THICKNESS=" + thickness, content)
                    self.assertIn("DIELECTRIC IMD" + str(i) + "b { THICKNESS=0.067 ER=4.0 }", content)
                self.assertIn("VIA V4 { FROM=fab4 TO=top5", content)
                self.assertIn("VIA PA { FROM=top5 TO=pad1", content)

    def test_exact_template_whitespace(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "header.j2").write_bytes(b"HEADER {{ CORNER }}\r\n\r\n")
            (root / "metal.j2").write_bytes(b"\r\nmetal{{ MID }}={{ TK_M }}\r\n\r\n")
            path = root / "options.json"
            path.write_text(json.dumps({
                "header_template": "header.j2",
                "components": {"INTER": {"kind": "metal", "template": "metal.j2", "parameters": {"TK_M": ["0.09", "0.10", "0.11"]}}},
                "metal_options": {"custom": ["INTER", "INTER"]},
            }), encoding="utf-8")
            paths = MODULE.generate(path, root / "out", "typical")
            self.assertEqual(paths[0].read_bytes(), b"HEADER TYPICAL\r\n\r\n\r\nmetal2=0.10\r\n\r\n\r\nmetal1=0.10\r\n\r\n")


if __name__ == "__main__":
    unittest.main()
