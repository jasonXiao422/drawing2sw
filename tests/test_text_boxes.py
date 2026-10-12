"""text_boxes.py：图片上找文字框、按编号生成观察、检查手写框是否落在字上。用合成图，不依赖任何图纸。"""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import text_boxes


def make_drawing(path):
    img = Image.new('RGB', (600, 400), 'white')
    d = ImageDraw.Draw(img)
    d.rectangle((100, 100, 400, 300), outline='black', width=2)       # 外轮廓
    d.line((100, 340, 400, 340), fill=(150, 0, 0), width=1)           # 尺寸线
    d.text((235, 325), '300', fill=(150, 0, 0))                        # 红色尺寸数字
    d.text((420, 190), 'R12', fill='black')
    img.save(path)


class TextBoxes(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.img = self.dir / 'drawing.png'
        make_drawing(self.img)
        self.data = text_boxes.detect(str(self.img))

    def tearDown(self):
        shutil.rmtree(self.dir)

    def box_near(self, x, y):
        for b in self.data['boxes']:
            x0, y0, x1, y1 = b['bbox']
            if x0 - 3 <= x <= x1 + 3 and y0 - 3 <= y <= y1 + 3:
                return b
        self.fail(f'没有找到 ({x}, {y}) 附近的文字框: {self.data["boxes"]}')

    def test_finds_text_but_not_long_lines(self):
        self.box_near(245, 330)
        self.box_near(428, 195)
        for b in self.data['boxes']:
            x0, y0, x1, y1 = b['bbox']
            self.assertLess(x1 - x0, 200, '长直线不应该被当成文字框')

    def test_emit_then_check_passes_and_bad_box_fails(self):
        (self.dir / 'tb.json').write_text(json.dumps(self.data), encoding='utf-8')
        obs = {'schema_version': '1.0', 'source': {'file': 'drawing.png', 'sha256': 'a' * 64},
               'pages': [{'page': 1, 'image': 'drawing.png', 'size_px': [600, 400]}],
               'observations': [], 'views': [],
               'open_questions': ['No text extracted. Import OCR or record visual observations with original-image bounding boxes.']}
        (self.dir / 'obs.json').write_text(json.dumps(obs), encoding='utf-8')
        b300, br = self.box_near(245, 330), self.box_near(428, 195)
        labels = [{'box': b300['id'], 'text': '300'}, {'box': br['id'], 'text': 'R12'}]
        (self.dir / 'labels.json').write_text(json.dumps(labels), encoding='utf-8')
        doc = text_boxes.emit(str(self.dir / 'tb.json'), str(self.dir / 'labels.json'),
                              str(self.dir / 'obs.json'), str(self.dir / 'out.json'))
        self.assertEqual(len(doc['observations']), 2)
        self.assertEqual(doc['open_questions'], [])
        errors, warnings = text_boxes.check_boxes(doc, [self.dir])
        self.assertEqual((errors, warnings), ([], []))
        # 估出来的框：落在空白处 -> 报错；只框住半个字 -> 警告
        doc['observations'].append({'id': 'guess', 'page': 1, 'text': '50', 'bbox': [150, 150, 190, 180],
                                    'coordinate_space': 'image_px', 'provider': 'visual'})
        x0, y0, x1, y1 = b300['bbox']
        doc['observations'].append({'id': 'half', 'page': 1, 'text': '300', 'bbox': [x0, y0, (x0 + x1) // 2, y1],
                                    'coordinate_space': 'image_px', 'provider': 'visual'})
        errors, warnings = text_boxes.check_boxes(doc, [self.dir])
        self.assertTrue(any(e.startswith('guess') for e in errors))
        self.assertTrue(any(w.startswith('half') for w in warnings))

    def test_unknown_box_id_rejected(self):
        (self.dir / 'tb.json').write_text(json.dumps(self.data), encoding='utf-8')
        (self.dir / 'obs.json').write_text(json.dumps({'observations': [], 'pages': []}), encoding='utf-8')
        (self.dir / 'labels.json').write_text(json.dumps([{'box': 't999', 'text': '1'}]), encoding='utf-8')
        with self.assertRaises(SystemExit):
            text_boxes.emit(str(self.dir / 'tb.json'), str(self.dir / 'labels.json'),
                            str(self.dir / 'obs.json'), str(self.dir / 'out.json'))


if __name__ == '__main__':
    unittest.main()
