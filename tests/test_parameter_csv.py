"""验证 CSV 参数计算、往返转换与 ITF 生成主流程。"""

import csv
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("parameter_csv", ROOT / "scripts/parameter_csv.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ParameterCsvTests(unittest.TestCase):
    """覆盖三种类型、两个方向和实际项目参数。"""

    def test_modes_and_directions(self):
        self.assertEqual(MODULE.expand("same", "5.0", "", ""), "5.0")
        for kind, amount in (("delta", "0.03"), ("ratio", "10"), ("ratio", "10%")):
            for direction, expected in (("-+", ["0.27", "0.3", "0.33"]),
                                        ("+-", ["0.33", "0.3", "0.27"])):
                with self.subTest(kind=kind, amount=amount, direction=direction):
                    self.assertEqual(list(map(Decimal, MODULE.expand(kind, "0.3", amount, direction))),
                                     list(map(Decimal, expected)))

    def test_csv_json_round_trip_and_itf(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            generated = root / "parameters.json"
            actual = MODULE.csv_to_json(ROOT / "parameters.csv", generated)
            expected = json.loads((ROOT / "parameters.json").read_text(encoding="utf-8"))
            self.assertEqual(actual, expected)
            exported = root / "export.csv"
            MODULE.json_to_csv(generated, exported)
            self.assertTrue(exported.read_bytes().startswith(b"\xef\xbb\xbf"))
            with exported.open(encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.reader(stream))
            self.assertEqual(rows[0], ["component", "parameter", "type", "typical", "delta_or_percent", "direction"])
            self.assertIn(["INTER_METAL", "ER_IMDA", "same", "5.0", "", ""], rows)
            self.assertEqual(MODULE.csv_to_json(exported, root / "roundtrip.json"), expected)
            with exported.open("a", encoding="utf-8", newline="") as stream:
                csv.writer(stream).writerow(("", "GLOBAL_ER", "same", "4.1", "", ""))
            self.assertEqual(MODULE.csv_to_json(exported, generated)["parameters"], {"GLOBAL_ER": "4.1"})
            options = json.loads((ROOT / "metal_option.json").read_text(encoding="utf-8"))
            options["parameter_file"] = str(generated)
            options["header_template"] = str(ROOT / options["header_template"])
            for field in ("suffix_templates", "via_templates"):
                options[field] = [str(ROOT / path) for path in options[field]]
            for component in options["components"].values():
                component["template"] = str(ROOT / component["template"])
            config = root / "options.json"
            config.write_text(json.dumps(options), encoding="utf-8")
            result = subprocess.run([sys.executable, str(ROOT / "scripts/generate_itf.py"),
                                     "--metal-options", str(config), "--output-dir", str(root / "build")],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            outputs = list((root / "build").glob("*/*.itf"))
            self.assertEqual(len(outputs), 9)
            typical = next(path for path in outputs if path.stem == "TYPICAL")
            self.assertIn("THICKNESS=0.3 RPSQ=0.05", typical.read_text(encoding="utf-8"))
            for path in outputs:
                if "ALPA2" in path.parent.name:
                    content = path.read_text(encoding="utf-8")
                    pass_thickness = {"CMAX": "0.045", "TYPICAL": "0.05", "CMIN": "0.055"}[path.stem]
                    for level in range(1, 7):
                        self.assertIn("DIELECTRIC PASS" + str(level) + " { THICKNESS=" + pass_thickness + " ER=3.0", content)
                    self.assertIn("TW_T=0 SW_T=0 MEASURED_FROM=TOP_OF_CHIP", content)
                    self.assertNotIn("IMD_ALPA", content)


if __name__ == "__main__":
    unittest.main()
