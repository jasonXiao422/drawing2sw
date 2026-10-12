"""合成数据集生成器、尺寸归属检查、姿态无关的几何评分。"""
import copy
import json
from pathlib import Path
import random
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "dev" / "tools"))

import association  # noqa: E402


class NumberParsing(unittest.TestCase):
    def test_dimension_texts(self):
        cases = {"4× Ø9 THRU": [4, 9], "4X Ø.375 THRU": [4, .375], "R5": [5], "C1": [1],
                 "PCD80": [80], "1 X 45°": [1, 45], "12,5": [12.5]}
        for text, nums in cases.items():
            with self.subTest(text=text):
                self.assertTrue(association.looks_like_dimension(text))
                self.assertEqual(association.numbers_in(text), nums)

    def test_primary_value_ignores_count_and_tolerance(self):
        cases = {"4× Ø9 THRU": 9, "Ø20 H7": 20, "20±0.1": 20, "20 +0.1/-0.05": 20, "(35)": 35,
                 "1 X 45°": 1, ".06 X 45°": .06, "M8x1.25": 8, "4X M6": 6}
        for text, value in cases.items():
            with self.subTest(text=text):
                self.assertTrue(association.looks_like_dimension(text))
                self.assertEqual(association.primary_value(text), value)

    def test_title_block_is_not_dimension(self):
        for text in ("SCALE 1:1", "1:1", "ISO 128", "GENERAL TOLERANCES ISO 2768-m", "45钢"):
            with self.subTest(text=text):
                self.assertFalse(association.looks_like_dimension(text))

    def test_hole_numbers_include_spacing_and_edge_offsets(self):
        table = {"features": [
            {"id": "p", "type": "base_extrude", "plane": "top",
             "profile": {"shape": "rect", "width": 100, "height": 60, "center": [50, 30]}, "depth": 10},
            {"id": "h", "type": "hole", "plane": "top", "diameter": 9, "positions": [[12, 10], [88, 10]],
             "depth": "through_all"}]}
        nums = association.feature_numbers(table["features"][1], table)
        for v in (9, 76, 12, 10, 2):
            self.assertTrue(association.contains(nums, v), v)
        self.assertFalse(association.contains(nums, 100))


class Callouts(unittest.TestCase):
    def parse(self, text):
        import callouts
        return callouts.parse(text)

    def test_counterbore_through_hole(self):
        p = self.parse("2X ⌀4.5 THRU ⌴⌀7 ↧3.5")
        self.assertEqual(p["feature_hint"], {"diameter": 4.5, "depth": "through_all",
                                             "cbore": {"diameter": 7.0, "depth": 3.5}})
        self.assertEqual(p["count"], 2)

    def test_gb_counterbore(self):
        p = self.parse("4×Φ9 沉孔Φ15深5")
        self.assertEqual((p["count"], p["diameter"], p["cbore"]), (4, 9.0, {"diameter": 15.0, "depth": 5.0}))

    def test_bolt_circle_iso_and_asme(self):
        for text in ("4X ⌀5 THRU EQ SP ON ⌀60 ±0.2 B.C.", "4×⌀5 EQUALLY SPACED ON ⌀60 PCD", "4×Φ5 均布 PCD60"):
            with self.subTest(text=text):
                self.assertEqual(self.parse(text)["feature_hint"]["bolt_circle"], {"pcd": 60.0, "count": 4})

    def test_spotface_with_tolerance_in_between(self):
        p = self.parse("⌀30 THRU ⌴⌀40 ±0.2 SF ↧5")
        self.assertEqual(p["spotface"]["diameter"], 40.0)
        self.assertEqual(p["spotface"]["depth"], 5.0)
        self.assertNotIn("unparsed", p)

    def test_countersink_thread_slot_gdt(self):
        self.assertEqual(self.parse("⌀10 ⌵⌀18 X 90°")["csink"], {"diameter": 18.0, "angle": 90.0})
        self.assertEqual(self.parse("M8x1.25 ↧12")["thread"]["pitch"], 1.25)
        self.assertEqual(self.parse("4×7 × 29 ↧2,5")["slot"], {"width": 7.0, "length": 29.0, "depth": 2.5})
        g = self.parse("perpendicularity|⌀0.2|B\ncylindricity|0.2")
        self.assertEqual([f["characteristic"] for f in g["frames"]], ["perpendicularity", "cylindricity"])
        self.assertFalse(association.looks_like_dimension("flatness|0.2"))

    def test_unknown_is_not_forced(self):
        for text in ("SCALE 2:1", "ISO 2768-f", "Synthetic data"):
            self.assertEqual(self.parse(text)["kind"], "unknown")


class Dataset(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import generate_dataset
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name) / "ds"
        cls.cases = generate_dataset.generate(cls.root, 2, 11, ["plate", "flange"], {"dxf", "pdf", "png"})

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_every_label_maps_to_an_observation(self):
        for case in self.cases:
            for fmt in ("dxf", "pdf"):
                m = case["observation_match"][fmt]
                self.assertEqual(m["matched"], m["labels"], (case["id"], fmt))

    def test_answers_hidden_from_prepared_input(self):
        import benchmark
        out = Path(self.tmp.name) / "blind"
        benchmark.prepare(self.root / "manifest.json", self.cases[0]["id"], out, "dxf")
        names = sorted(p.name for p in out.iterdir())
        self.assertEqual(names, ["TASK.md", "drawing.dxf", "input_manifest.json"])

    def _model_output(self, case, mutate=None):
        import observations
        import preprocess_drawing as pre
        folder = self.root / case["id"]
        answer = json.loads((folder / "answer.json").read_text(encoding="utf-8"))
        work = Path(tempfile.mkdtemp(dir=self.tmp.name))
        src = folder / "drawing.dxf"
        ev = observations.from_extract(pre.from_dxf(src, work), src)
        observations.dump(ev, work / "obs.json")
        table = copy.deepcopy(answer["source_table"])
        table["schema_version"] = "0.5"
        table["part"]["source"] = {"file": src.name, "sha256": ev["source"]["sha256"]}
        for f in table["features"]:
            refs = sorted({lab["observations"]["dxf"] for lab in answer["dimension_labels"]
                           if lab["feature"] == f["id"]})
            f["meta"]["evidence_refs"] = refs or [ev["observations"][0]["id"]]
        if mutate:
            mutate(table)
        observations.dump(table, work / "part.json")
        return work

    def _score(self, case, mutate=None):
        import benchmark
        work = self._model_output(case, mutate)
        return benchmark.score(self.root / "manifest.json", case["id"], work / "part.json",
                               work / "obs.json", "unit-test")

    def test_perfect_reading_scores_full_marks(self):
        for case in self.cases:
            r = self._score(case)
            self.assertEqual(r["status"], "geometry_passed", (case["id"], r))
            self.assertEqual(r["association"]["summary"]["association_recall"], 1.0)

    def test_other_pose_still_passes(self):
        def swap_planes(t):
            for f in t["features"]:
                if f.get("plane") in ("top", "front"):
                    f["plane"] = {"top": "front", "front": "top"}[f["plane"]]
        plate = next(c for c in self.cases if c["family"] == "plate")
        self.assertEqual(self._score(plate, swap_planes)["status"], "geometry_passed")

    def test_pose_free_rejects_mirror_but_accepts_rotation(self):
        import benchmark
        import cadquery as cq
        part = cq.Workplane("XY").box(100, 60, 10, centered=False).faces(">Z").workplane(origin=(0, 0, 10))             .center(15, 12).hole(8, 5).val()       # 盲孔：镜像以后不能靠翻转复原
        mirrored = part.mirror("YZ", (50, 0, 0))
        rotated = part.rotate((0, 0, 0), (1, 0, 0), 90).translate((7, -3, 2))
        self.assertLess(benchmark.pose_free_difference(rotated, part)[0], 1e-6)
        self.assertGreater(benchmark.pose_free_difference(mirrored, part)[0], 100)

    def test_swapped_evidence_is_detected(self):
        def swap(t):
            a, b = t["features"][0], t["features"][1]
            a["meta"]["evidence_refs"], b["meta"]["evidence_refs"] = b["meta"]["evidence_refs"], a["meta"]["evidence_refs"]
        case = self.cases[0]
        r = self._score(case, swap)
        self.assertLess(r["association"]["summary"]["association_recall"], 1.0)
        self.assertGreater(r["association"]["summary"]["wrong_feature"], 0)


if __name__ == "__main__":
    random.seed(0)
    unittest.main()
