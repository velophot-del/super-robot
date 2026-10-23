import unittest

from app.utils.csv_parser import generate_csv_template, parse_csv_content
from app.services.course_library import normalize_course_classification


class CsvTemplateTaxonomyTests(unittest.TestCase):
    def test_class_template_matches_cohort_and_active_fields(self):
        template = generate_csv_template('classes').splitlines()
        self.assertEqual(template[0], '班级名称,年级,学生人数,所属专业,专业编码,纳入排课,班主任,备注')
        self.assertIn('是', template[1])

    def test_course_template_uses_separate_canonical_fields(self):
        template = generate_csv_template('courses').splitlines()
        self.assertIn('上课学期', template[0])
        self.assertIn('课程类型', template[0])
        self.assertIn('课程性质', template[0])
        self.assertIn('专业课', template[1])
        self.assertIn('必修课', template[1])
        rows, errors = parse_csv_content(generate_csv_template('courses'), 'courses')
        self.assertEqual(errors, [])
        self.assertEqual(rows[0]['semester'], 2)

    def test_curriculum_syllabus_template_is_removed(self):
        self.assertEqual(generate_csv_template('syllabus'), '')
        rows, errors = parse_csv_content('班级名称,年级\n设计1班,2026\n', 'syllabus')
        self.assertEqual(rows, [])
        self.assertIn('未知的实体类型', errors[0])

    def test_legacy_course_values_normalize_to_the_two_taxonomies(self):
        self.assertEqual(normalize_course_classification('公共选修课', '选修'), ('学科通识课', '限选课'))
        self.assertEqual(normalize_course_classification('思政任选课', ''), ('德育通识课', '任选课'))


if __name__ == '__main__':
    unittest.main()
