"""拔模 draft：基体拉伸、加料拉伸（反方向、向外）、切除的体积和精确公式一致；校验拦住不该用拔模的情况。"""
import math
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import ftable
from validate_feature_table import validate

META = {'confidence': 1, 'evidence': 'test'}


def table(features):
    return {'schema_version': '0.4',
            'part': {'name': 't', 'part_type': 'prismatic', 'units': 'mm',
                     'drawing_setup': {'length_unit': 'mm', 'unit_evidence': 'test', 'standard': 'ISO',
                                       'language': 'en', 'scale': '1:1', 'confidence': 0.99},
                     'projection': 'first_angle', 'source': {'file': 't', 'format': 'other', 'standard': 'ISO'}},
            'features': features}


def prismatoid(a, b, h, side):
    """矩形 a×b，每边沿高度 h 线性移动 side（负 = 收）；拟柱体公式是精确的。"""
    area = lambda s: (a + 2 * side * s) * (b + 2 * side * s)
    return h / 6 * (area(0) + 4 * area(0.5) + area(1))


def k(deg, h):
    return h * math.tan(math.radians(deg))


BLOCK = {'id': 'block', 'type': 'base_extrude', 'plane': 'top', 'profile': {'shape': 'rect', 'width': 40, 'height': 30},
         'depth': 20, 'draft': 3, 'meta': META}
POCKET = {'id': 'pocket', 'type': 'cut_extrude', 'plane': 'top', 'offset': 20,
          'profile': {'shape': 'rect', 'width': 20, 'height': 12}, 'depth': 8, 'direction': 'negative', 'draft': 2, 'meta': META}
FOOT = {'id': 'foot', 'type': 'extrude', 'plane': 'top', 'profile': {'shape': 'rect', 'width': 10, 'height': 10},
        'depth': 5, 'direction': 'negative', 'draft': 4, 'draft_outward': True, 'meta': META}


class DraftVolumes(unittest.TestCase):
    def volume(self, feats):
        import preview_cadquery
        return preview_cadquery.build(ftable.to_mm(ftable.resolve(table(feats)))).val().Volume()

    def test_base_pocket_and_reversed_outward_boss(self):
        # SolidWorks 实测 21248.343 = 拟柱体公式；CadQuery 锥度拉伸差 0.2 mm³
        hand = prismatoid(40, 30, 20, -k(3, 20)) - prismatoid(20, 12, 8, -k(2, 8)) + prismatoid(10, 10, 5, k(4, 5))
        self.assertAlmostEqual(self.volume([BLOCK, POCKET, FOOT]), hand, delta=0.5)

    def test_reversed_boss_grows_away_from_sketch_plane(self):
        import preview_cadquery
        t = ftable.to_mm(ftable.resolve(table([BLOCK, FOOT])))
        bb = preview_cadquery.build(t).val().BoundingBox()
        self.assertAlmostEqual(bb.ymin, -5, places=3)                 # 往 -Y 长了 5
        self.assertAlmostEqual(bb.xmax, 20, places=3)                 # 外形最大处还是基体的 40 宽


class DraftValidation(unittest.TestCase):
    def test_rejects_through_all_and_two_sided(self):
        bad1 = dict(POCKET, depth='through_all')
        bad2 = dict(POCKET, id='p2', direction='both')
        errors, _ = validate(table([BLOCK, bad1, bad2]))
        text = '\n'.join(errors)
        self.assertIn('深度是数值', text)
        self.assertIn('单方向', text)


if __name__ == '__main__':
    unittest.main()
