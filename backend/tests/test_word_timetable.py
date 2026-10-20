from datetime import date
from io import BytesIO
from zipfile import ZipFile
from xml.etree import ElementTree as ET
import unittest
from app.services.word_timetable import build_word_timetable

N={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}


class WordTimetableTests(unittest.TestCase):
    def test_template_layout_dynamic_weeks_stage_spans_and_two_courses(self):
        tasks=[{'id':i,'group':'视传2601','code':str(i),'name':name,'start_week':1,'end_week':4,
            'teacher_names':['甲','乙'],'room_name':'设计实验室','credits':2,'required_hours':16,
            'student_count':30,'slots':[{'day':day,'start':1,'count':4}]} for i,name,day in [(1,'文字与版式设计',1),(2,'品牌设计',3)]]
        batches=[{'plan':{'name':'2026-2027第一学期','major':'视觉传达设计','cohort':'2026',
            'semester':1,'start_date':'2026-09-07','weeks':20},'tasks':tasks}]
        content=build_word_timetable(batches,'视觉传达设计',date(2026,10,20))
        with ZipFile(BytesIO(content)) as z:
            self.assertIsNone(z.testzip());root=ET.fromstring(z.read('word/document.xml'))
            self.assertIn('word/styles.xml',z.namelist())
        text=''.join(root.itertext())
        for value in ['文字与版式设计','品牌设计','周一','周三','甲','乙','设计实验室','2026级','9.7','9.13']:
            self.assertIn(value,text)
        self.assertNotIn('2016-2017',text);self.assertNotIn('13广告',text)
        table=root.find('.//w:tbl',N)
        self.assertEqual(len(table.findall('w:tblGrid/w:gridCol',N)),23)
        self.assertEqual(root.find('.//w:pgSz',N).get('{'+N['w']+'}orient'),'landscape')
        self.assertTrue(any(x.get('{'+N['w']+'}val')=='4' for x in table.findall('.//w:gridSpan',N)))
        first=table.findall('w:tr',N)[2]
        self.assertTrue(any('文字与版式设计' in ''.join(c.itertext()) and '品牌设计' in ''.join(c.itertext()) for c in first.findall('w:tc',N)))

    def test_cohorts_have_separate_pages_and_exam_weeks(self):
        base={'name':'Term','major':'Design','start_date':'2027-02-01','weeks':18,'semester':2}
        task={'id':1,'name':'A','group':'G','start_week':1,'end_week':1,'slots':[]}
        data=build_word_timetable([{'plan':{**base,'cohort':c},'tasks':[task]} for c in ['2025','2026']], 'Design')
        with ZipFile(BytesIO(data)) as z:r=ET.fromstring(z.read('word/document.xml'))
        self.assertEqual(len(r.findall('.//w:tbl',N)),2)
        self.assertIn('考试',''.join(r.itertext()))
        self.assertEqual(len(r.findall('.//w:br[@w:type="page"]',N)),1)
