"""sw_build 里不需要 SolidWorks 就能测的安全逻辑：建模前的拦截、旧版本清理不碰目标文件本身。"""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import sw_build


class RemoveVersions(unittest.TestCase):
    def test_only_numbered_copies_are_removed(self):
        d = Path(tempfile.mkdtemp())
        try:
            for n in ('part.SLDPRT', 'part_1.SLDPRT', 'part_12.SLDPRT', 'part_a.SLDPRT', 'partx.SLDPRT', 'other_1.SLDPRT'):
                (d / n).write_text('x')
            removed = sw_build.remove_versions(d / 'part.SLDPRT')
            self.assertEqual(sorted(removed), ['part_1.SLDPRT', 'part_12.SLDPRT'])
            left = sorted(p.name for p in d.iterdir())
            self.assertEqual(left, ['other_1.SLDPRT', 'part.SLDPRT', 'part_a.SLDPRT', 'partx.SLDPRT'])
        finally:
            shutil.rmtree(d)


class GatesBeforeSolidWorks(unittest.TestCase):
    """校验不过、预览算不出来时，sw_build 在连接 SolidWorks 之前就停下（退出码 3），所以在没有 SolidWorks 的机器上也能测。"""

    def run_build(self, table):
        d = Path(tempfile.mkdtemp())
        try:
            (d / 't.json').write_text(json.dumps(table, ensure_ascii=False), encoding='utf-8')
            p = subprocess.run([sys.executable, str(ROOT / 'scripts' / 'sw_build.py'), str(d / 't.json'),
                                '-o', str(d / 'x.SLDPRT'), '--report', str(d / 'r.json')],
                               capture_output=True, cwd=ROOT)
            return p.returncode, json.loads((d / 'r.json').read_text(encoding='utf-8'))
        finally:
            shutil.rmtree(d)

    def table(self, features, version='0.4'):
        return {'schema_version': version,
                'part': {'name': 't', 'part_type': 'prismatic', 'units': 'mm',
                         'drawing_setup': {'length_unit': 'mm', 'unit_evidence': 'test', 'standard': 'ISO',
                                           'language': 'en', 'scale': '1:1', 'confidence': 0.99},
                         'projection': 'first_angle', 'source': {'file': 't', 'format': 'other', 'standard': 'ISO'}},
                'features': features}

    plate = {'id': 'plate', 'type': 'base_extrude', 'plane': 'top',
             'profile': {'shape': 'rect', 'width': 40, 'height': 30}, 'depth': 10, 'meta': {'confidence': 1, 'evidence': 't'}}

    def test_validation_error_blocks(self):
        bad = dict(self.plate, depth=-5)
        code, rep = self.run_build(self.table([bad]))
        self.assertEqual(code, 3)
        self.assertEqual(rep['status'], 'blocked_validation')

    def test_v05_without_evidence_blocks(self):
        code, rep = self.run_build(self.table([self.plate], version='0.5'))
        self.assertEqual(code, 3)
        self.assertEqual(rep['status'], 'blocked_validation')

    def test_preview_failure_blocks(self):
        huge = {'id': 'r', 'type': 'edge_treatment', 'kind': 'fillet', 'size': 20, 'edges': 'top_outer',
                'meta': {'confidence': 1, 'evidence': 't'}}
        code, rep = self.run_build(self.table([self.plate, huge]))
        self.assertEqual(code, 3)
        self.assertEqual(rep['status'], 'blocked_preview_failed')


if __name__ == '__main__':
    unittest.main()
