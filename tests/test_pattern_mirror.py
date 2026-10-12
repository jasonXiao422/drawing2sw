"""线性阵列 linear_pattern、镜像 mirror：展开、单位换算、校验、CadQuery 体积、尺寸归属。"""
import copy
import math
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import ftable
import association
from validate_feature_table import validate

META = {'confidence': 1, 'evidence': 'test'}


def table(features, units='mm'):
    return {'schema_version': '0.4',
            'part': {'name': 't', 'part_type': 'prismatic', 'units': units,
                     'drawing_setup': {'length_unit': units, 'unit_evidence': 'test', 'standard': 'ISO',
                                       'language': 'en', 'scale': '1:1', 'confidence': 0.99},
                     'projection': 'first_angle', 'source': {'file': 't', 'format': 'other', 'standard': 'ISO'}},
            'features': features}


def plate():
    return {'id': 'plate', 'type': 'base_extrude', 'plane': 'top',
            'profile': {'shape': 'rect', 'width': 100, 'height': 60}, 'depth': 10, 'meta': META}


def rib():
    return {'id': 'rib', 'type': 'extrude', 'plane': 'top', 'offset': 10,
            'profile': {'shape': 'rect', 'width': 4, 'height': 40, 'center': [-40, 0]}, 'depth': 5, 'meta': META}


def cb_hole():
    return {'id': 'h', 'type': 'hole', 'plane': 'top', 'offset': 10, 'diameter': 5, 'depth': 'through_all',
            'direction': 'negative', 'positions': [[35, 15]], 'cbore': {'diameter': 9, 'depth': 2}, 'meta': META}


class PatternGeometry(unittest.TestCase):
    def test_offsets_grid_excludes_seed(self):
        f = {'direction': '-X', 'count': 3, 'spacing': 10, 'direction2': '+Z', 'count2': 2, 'spacing2': 5}
        offs = ftable.pattern_offsets(f)
        self.assertEqual(len(offs), 5)
        self.assertNotIn((0, 0, 0), offs)
        self.assertIn((-20, 0, 5), offs)

    def test_mirror_plane_offset(self):
        self.assertEqual(ftable.mirror_plane({'plane': 'right', 'offset': 7}), ((7, 0, 0), (1, 0, 0)))

    def test_resolve_expands_counterbore_refs(self):
        t = ftable.resolve(table([plate(), cb_hole(),
                                  {'id': 'm', 'type': 'mirror', 'features': ['h'], 'plane': 'right', 'meta': META}]))
        self.assertEqual(t['features'][-1]['features'], ['h__cbore', 'h'])

    def test_resolve_keeps_unknown_ref_for_validator(self):
        t = ftable.resolve(table([plate(), {'id': 'm', 'type': 'mirror', 'features': ['nope'],
                                            'plane': 'right', 'meta': META}]))
        self.assertEqual(t['features'][-1]['features'], ['nope'])

    def test_to_mm_scales_spacing(self):
        p = {'id': 'p', 'type': 'linear_pattern', 'features': ['rib'], 'direction': '+X', 'count': 2,
             'spacing': 1, 'direction2': '+Z', 'count2': 2, 'spacing2': 0.5, 'meta': META}
        t = ftable.to_mm(table([plate(), rib(), p], units='inch'))
        self.assertAlmostEqual(t['features'][-1]['spacing'], 25.4)
        self.assertAlmostEqual(t['features'][-1]['spacing2'], 12.7)


class PatternValidation(unittest.TestCase):
    def test_rejects_base_unknown_and_parallel_directions(self):
        bad = [plate(), rib(),
               {'id': 'p', 'type': 'linear_pattern', 'features': ['rib'], 'direction': '+X', 'count': 2,
                'spacing': 10, 'direction2': '-X', 'count2': 2, 'spacing2': 5, 'meta': META},
               {'id': 'm', 'type': 'mirror', 'features': ['plate', 'later'], 'plane': 'right', 'meta': META},
               {'id': 'later', 'type': 'extrude', 'plane': 'top', 'offset': 10,
                'profile': {'shape': 'rect', 'width': 2, 'height': 2}, 'depth': 1, 'meta': META}]
        errors, _ = validate(table(bad))
        text = '\n'.join(errors)
        self.assertIn('必须垂直', text)
        self.assertIn('不能复制 plate', text)
        self.assertIn('later 不存在，或者写在了本特征后面', text)

    def test_second_direction_needs_all_three_fields(self):
        p = {'id': 'p', 'type': 'linear_pattern', 'features': ['rib'], 'direction': '+X', 'count': 2,
             'spacing': 10, 'direction2': '+Z', 'meta': META}
        errors, _ = validate(table([plate(), rib(), p]))
        self.assertTrue(any('同时写 direction2' in e for e in errors))


class PatternPreview(unittest.TestCase):
    def test_volume_matches_hand_calculation(self):
        import preview_cadquery
        feats = [plate(), rib(),
                 {'id': 'ribs', 'type': 'linear_pattern', 'features': ['rib'], 'direction': '+X', 'count': 5,
                  'spacing': 20, 'meta': META},
                 cb_hole(),
                 {'id': 'hm', 'type': 'mirror', 'features': ['h'], 'plane': 'right', 'meta': META}]
        t = ftable.to_mm(ftable.resolve(table(feats)))
        vol = preview_cadquery.build(t).val().Volume()
        hole = math.pi * 2.5 ** 2 * 10 + math.pi * (4.5 ** 2 - 2.5 ** 2) * 2
        self.assertAlmostEqual(vol, 60000 + 5 * 800 - 2 * hole, places=2)


class PatternAssociation(unittest.TestCase):
    def test_mirrored_copy_position_counts(self):
        # 左孔离左边 15，右孔（镜像件）离左边 55：55 应该能对上镜像特征
        t = table([{'id': 'b', 'type': 'base_extrude', 'plane': 'top',
                    'profile': {'shape': 'rect', 'width': 70, 'height': 30}, 'depth': 12, 'meta': META},
                   {'id': 'h', 'type': 'hole', 'plane': 'top', 'diameter': 4.5, 'depth': 'through_all',
                    'positions': [[-20, 0]], 'meta': META},
                   {'id': 'm', 'type': 'mirror', 'features': ['h'], 'plane': 'right', 'meta': META}])
        nums = association.feature_numbers(t['features'][2], t)
        self.assertTrue(association.contains(nums, 55))
        self.assertTrue(association.contains(nums, 4.5))

    def test_pattern_total_length_and_count(self):
        p = {'id': 'p', 'type': 'linear_pattern', 'features': ['rib'], 'direction': '+X', 'count': 5,
             'spacing': 12, 'meta': META}
        t = table([plate(), rib(), p])
        nums = association.feature_numbers(p, t)
        self.assertTrue(association.contains(nums, 48))
        self.assertTrue(association.contains(nums, 5))


if __name__ == '__main__':
    unittest.main()
