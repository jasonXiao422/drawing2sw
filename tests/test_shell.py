"""抽壳 shell：按点选面、向内 / 向外 / 封闭三种情况的体积和手算一致，单位换算，校验提示。"""
import math
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import ftable
from validate_feature_table import validate

META = {'confidence': 1, 'evidence': 'test'}


def table(features, units='mm'):
    return {'schema_version': '0.4',
            'part': {'name': 't', 'part_type': 'prismatic', 'units': units,
                     'drawing_setup': {'length_unit': units, 'unit_evidence': 'test', 'standard': 'ISO',
                                       'language': 'en', 'scale': '1:1', 'confidence': 0.99},
                     'projection': 'first_angle', 'source': {'file': 't', 'format': 'other', 'standard': 'ISO'}},
            'features': features}


BLOCK = {'id': 'block', 'type': 'base_extrude', 'plane': 'top',
         'profile': {'shape': 'rect', 'width': 120, 'height': 120}, 'depth': 60, 'meta': META}
R20 = {'id': 'r20', 'type': 'edge_treatment', 'kind': 'fillet', 'size': 20, 'edges': 'vertical', 'meta': META}


def rounded_square(w, r, hole=0.0):
    return w * w - 4 * (r * r - math.pi * r * r / 4) - math.pi * hole * hole


def shell(thickness, top_open=True, outward=False):
    f = {'id': 'shell', 'type': 'shell', 'thickness': thickness, 'meta': META}
    if top_open:
        f['open_faces'] = {'points': [[45, 60, 0]]}
    if outward:
        f['outward'] = True
    return f


class ShellVolumes(unittest.TestCase):
    def volume(self, feats):
        import preview_cadquery
        return preview_cadquery.build(ftable.to_mm(ftable.resolve(table(feats)))).val().Volume()

    def test_inward_open_top_with_center_hole(self):
        hole = {'id': 'hole', 'type': 'cut_extrude', 'plane': 'top', 'profile': {'shape': 'circle', 'diameter': 60},
                'depth': 'through_all', 'meta': META}
        v = self.volume([BLOCK, hole, R20, shell(2)])
        hand = rounded_square(120, 20, 30) * 60 - rounded_square(116, 18, 32) * 58
        self.assertAlmostEqual(v, hand, delta=0.5)

    def test_closed_hollow(self):
        v = self.volume([BLOCK, R20, shell(3, top_open=False)])
        hand = rounded_square(120, 20) * 60 - rounded_square(114, 17) * 54
        self.assertAlmostEqual(v, hand, delta=0.5)

    def test_outward_keeps_sharp_edges_like_solidworks(self):
        # SolidWorks 向外抽壳不给锐边加圆角；预览用 kind="intersection" 才对得上（实测 84154.689）
        v = self.volume([BLOCK, R20, shell(2, outward=True)])
        hand = rounded_square(124, 22) * 62 - rounded_square(120, 20) * 60
        self.assertAlmostEqual(v, hand, delta=0.5)

    def test_point_on_edge_rejected(self):
        import preview_cadquery
        bad = dict(shell(2), open_faces={'points': [[60, 60, 0]]})   # 顶面和侧面的交线上
        with self.assertRaises(preview_cadquery.CapabilityBlocked):
            self.volume([BLOCK, bad])


class ShellTable(unittest.TestCase):
    def test_inch_thickness_and_points_converted(self):
        f = dict(shell(0.1), open_faces={'points': [[1, 2, 0]]})
        t = ftable.to_mm(table([BLOCK, f], units='inch'))
        self.assertAlmostEqual(t['features'][1]['thickness'], 2.54)
        self.assertEqual(t['features'][1]['open_faces']['points'][0][:2], [25.4, 50.8])

    def test_warnings(self):
        thin = dict(R20, size=1.5)
        _, warnings = validate(table([BLOCK, thin, shell(2, top_open=False)]))
        text = '\n'.join(warnings)
        self.assertIn('内壁会变成尖角', text)
        self.assertIn('没写 open_faces', text)


if __name__ == '__main__':
    unittest.main()
