"""Behavioral regression tests for evidence, fail-closed checks and blind inputs."""
import copy
import json
from pathlib import Path
import sys
import shutil
import uuid
from contextlib import contextmanager
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import observations
import ocr_drawing
import benchmark
from verify_model import compare
from validate_feature_table import validate
from preprocess_drawing import detect_setup


@contextmanager
def temporary_workspace():
    root = (ROOT / 'work').resolve()
    root.mkdir(exist_ok=True)
    path = root / ('test-' + uuid.uuid4().hex)
    path.mkdir()
    try:
        yield str(path)
    finally:
        if path.resolve().is_relative_to(root) and path.name.startswith('test-'):
            shutil.rmtree(path)


def evidence():
    return {'schema_version':'1.0','source':{'file':'page.png','sha256':'a'*64},
            'pages':[{'page':1,'image':'page.png','size_px':[100,100]}],
            'observations':[{'id':'p1-text-1','page':1,'text':'80','bbox':[1,1,20,20],
                'coordinate_space':'image_px','provider':'visual','kind':'dimension'}],
            'views':[],'open_questions':[]}


class VerificationTests(unittest.TestCase):
    def test_exact_properties_pass(self):
        r={'volume_mm3':100,'surface_area_mm2':80,'bbox_mm':[10,5,2]}
        self.assertTrue(compare(r,r)['verified'])
        self.assertFalse(compare(r,r)['drawing_verified'])

    def test_missing_expected_measurement_fails(self):
        self.assertFalse(compare({'volume_mm3':100},{'volume_mm3':100,'surface_area_mm2':80})['verified'])

    def test_only_face_or_declared_holes_never_verify(self):
        self.assertFalse(compare({'face_count':6,'hole_count_from_table':2},{'face_count':6},2)['verified'])

    def test_empty_reference_is_unverified(self):
        self.assertEqual(compare({'volume_mm3':100},{})['status'],'unverified')

    def test_invalid_metric_fails(self):
        for bad in (float('nan'),float('inf'),True,-1,0,'100',None):
            with self.subTest(bad=bad): self.assertFalse(compare({'volume_mm3':bad},{'volume_mm3':100})['verified'])

    def test_bad_bbox_length_fails(self):
        self.assertFalse(compare({'bbox_mm':[1,2]},{'bbox_mm':[1,2,3]})['verified'])

    def test_aligned_axes_detect_permutation(self):
        a,b={'bbox_mm':[10,20,30]},{'bbox_mm':[30,20,10]}
        self.assertTrue(compare(a,b)['verified'])
        self.assertFalse(compare(a,b,aligned_axes=True)['verified'])

    def test_failed_backend_and_multi_solid_fail(self):
        for extra in ({'status':'failed'},{'solid_count':2}):
            self.assertFalse(compare({'volume_mm3':100,**extra},{'volume_mm3':100})['verified'])

    def test_negative_tolerance_rejected(self):
        with self.assertRaises(ValueError): compare({}, {}, tolerance=-1)


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.table=json.loads((ROOT/'examples/bracket_prismatic.json').read_text(encoding='utf-8'))

    def traced(self):
        self.table['schema_version']='0.5'
        self.table['part']['source']['sha256']='a'*64
        for f in self.table['features']: f['meta']['evidence_refs']=['p1-text-1']
        return self.table

    def test_legacy_examples_remain_valid(self):
        for p in (ROOT/'examples').glob('*.json'):
            self.assertEqual(validate(json.loads(p.read_text(encoding='utf-8')))[0],[])

    def test_v05_requires_evidence_file(self):
        self.assertTrue(validate(self.traced())[0])

    def test_v05_valid_links(self):
        self.assertEqual(validate(self.traced(),evidence())[0],[])

    def test_foreign_source_rejected(self):
        doc=evidence();doc['source']['sha256']='b'*64
        self.assertTrue(validate(self.traced(),doc)[0])

    def test_dangling_reference_rejected(self):
        table=self.traced();table['features'][0]['meta']['evidence_refs']=['invented']
        self.assertTrue(validate(table,evidence())[0])

    def test_blank_explanation_rejected(self):
        table=self.traced();table['features'][0]['meta']['evidence']=' '
        self.assertTrue(validate(table,evidence())[0])

    def test_duplicate_observations_rejected(self):
        doc=evidence();doc['observations']*=2
        self.assertTrue(observations.validate_document(doc))

    def test_out_of_bounds_box_rejected(self):
        doc=evidence();doc['observations'][0]['bbox']=[10,10,101,20]
        self.assertTrue(observations.validate_document(doc))

    def test_nan_evidence_rejected(self):
        doc=evidence();doc['observations'][0]['bbox'][0]=float('nan')
        self.assertTrue(observations.validate_document(doc))

    def test_unknown_view_reference_rejected(self):
        doc=evidence();doc['views']=[{'id':'front','page':1,'role':'front','observation_refs':['bad']}]
        self.assertTrue(observations.validate_document(doc))

    def test_unit_colon_mm_and_inch(self):
        for unit in ('mm','inch'):
            self.assertEqual(detect_setup([f'All dimensions: {unit}'],[])['length_unit'][0]['value'],unit)

    def test_bundled_v05_example_valid(self):
        p=ROOT/'examples/evidence'
        table=json.loads((p/'part.json').read_text(encoding='utf-8'))
        doc=json.loads((p/'extract_observations.json').read_text(encoding='utf-8'))
        self.assertEqual(validate(table,doc)[0],[])
        self.assertEqual(observations.sha256(p/'drawing.pdf'),doc['source']['sha256'])


class OCRTests(unittest.TestCase):
    def payload(self):
        return {'res':{'rec_texts':['Ø10'],'rec_scores':[.97],
                       'rec_polys':[[[10,10],[40,10],[40,30],[10,30]]]}}

    def test_polygon_to_original_pixel_box(self):
        out=ocr_drawing.attach(evidence(),self.payload(),1)
        obs=out['observations'][-1]
        self.assertEqual(obs['bbox'],[10,10,40,30])
        self.assertTrue(obs['requires_review'])
        self.assertEqual(obs['score'],.97)

    def test_mismatched_lengths_rejected(self):
        p=self.payload();p['res']['rec_scores']=[]
        with self.assertRaises(ValueError): ocr_drawing.attach(evidence(),p,1)

    def test_unknown_page_rejected(self):
        with self.assertRaises(ValueError): ocr_drawing.attach(evidence(),self.payload(),2)

    def test_double_import_rejected(self):
        out=ocr_drawing.attach(evidence(),self.payload(),1)
        with self.assertRaises(ValueError): ocr_drawing.attach(out,self.payload(),1)


class DatasetTests(unittest.TestCase):
    def test_external_bytes_match_provenance(self):
        root=ROOT/'data/external/aaditya-jain'
        provenance=json.loads((root/'PROVENANCE.json').read_text())
        for item in provenance['files']:
            self.assertEqual(observations.sha256(root/item['file']),item['sha256'])

    def test_prepared_input_excludes_answers(self):
        with temporary_workspace() as td:
            out=Path(td)/'input'
            benchmark.prepare(ROOT/'data/synthetic/manifest.json','plate-01',out)
            self.assertEqual({p.name for p in out.iterdir()},{'drawing.pdf','TASK.md','input_manifest.json'})
            self.assertNotIn('expected',json.loads((out/'input_manifest.json').read_text()))

    def test_traversal_rejected(self):
        with self.assertRaises(ValueError): benchmark.case_path(ROOT/'data','../../private.pdf')

    def test_all_synthetic_tables_valid(self):
        for path in (ROOT/'data/synthetic').glob('*/answer.json'):
            self.assertEqual(validate(json.loads(path.read_text(encoding='utf-8')))[0],[],str(path))

    def test_shifted_hole_is_detected_despite_matching_properties(self):
        table=json.loads((ROOT/'data/synthetic/plate-01/answer.json').read_text())
        table['features'][1]['positions'][0][0]+=2
        with temporary_workspace() as td:
            path=Path(td)/'part.json';observations.dump(table,path)
            result=benchmark.score(ROOT/'data/synthetic/manifest.json','plate-01',path,None,'regression-test')
        self.assertTrue(result['properties']['verified'])
        self.assertFalse(result['symmetric_difference']['pass'])
        self.assertEqual(result['status'],'failed')


if __name__=='__main__': unittest.main()
