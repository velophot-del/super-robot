from io import BytesIO
from zipfile import ZipFile
from xml.etree import ElementTree as ET
import unittest
from app.services.curriculum_materials import extract_rows


def document(rows):
    ns='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    root=ET.Element('{'+ns+'}document');body=ET.SubElement(root,'{'+ns+'}body');table=ET.SubElement(body,'{'+ns+'}tbl')
    for row in rows:
        tr=ET.SubElement(table,'{'+ns+'}tr')
        for value in row:
            tc=ET.SubElement(tr,'{'+ns+'}tc');p=ET.SubElement(tc,'{'+ns+'}p');r=ET.SubElement(p,'{'+ns+'}r');ET.SubElement(r,'{'+ns+'}t').text=str(value)
    out=BytesIO()
    with ZipFile(out,'w') as z:z.writestr('word/document.xml',ET.tostring(root))
    return out.getvalue()


class CurriculumDocxTests(unittest.TestCase):
    def test_missing_code_and_stage_metadata_are_preserved(self):
        content=document([['课程性质','课程名称','学分','总学时','上课学期','周课时','上课周数','备注'],
            ['专业必修课','形式基础',4,72,1,16,5,'最后一周8课时'],['','','86',1568,'','','',''],['注：说明']])
        rows,errors=extract_rows('scheme.docx',content)
        self.assertEqual(errors,[]);self.assertEqual(len(rows),1)
        row=rows[0];self.assertTrue(row['code_generated']);self.assertTrue(row['code'].startswith('SYS-'))
        self.assertEqual(row['semester'],1);self.assertEqual(row['weekly_hours'],16)
        self.assertEqual(row['teaching_weeks'],5);self.assertEqual(row['tail_hours'],8)
        self.assertEqual(row['notes'],'最后一周8课时');self.assertEqual(row['raw_fields']['总学时'],'72')
        self.assertEqual(extract_rows('scheme.docx',content)[0][0]['code'],row['code'])

    def test_missing_semester_and_duplicate_names_are_not_invented_or_merged(self):
        content=document([['课程性质','课程名称','学分','总学时','开课学期'],
            ['公共必修课','思政选修课',1,18,''],['专业限选课','界面交互设计',3,54,4],
            ['专业限选课','界面交互设计',3,54,4],['专业任选课','课程单独列出',6,108,6]])
        rows,errors=extract_rows('scheme.docx',content)
        self.assertEqual(errors,[]);self.assertEqual(len(rows),4)
        self.assertIsNone(rows[0]['semester']);self.assertFalse(rows[0]['schedulable'])
        self.assertNotEqual(rows[1]['code'],rows[2]['code'])
        self.assertFalse(rows[1]['schedulable']);self.assertTrue(rows[1]['review_notes'])
        self.assertFalse(rows[3]['schedulable'])
