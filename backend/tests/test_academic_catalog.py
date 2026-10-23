import unittest
import test_debug_mode
from app.models.class_info import ClassInfo
from app.models.planning import AcademicProgram, CurriculumDocument
from app.services.academic_scope import curriculum_semester
from app.database import _migrate_academic_scope_columns


class AcademicCatalogTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=test_debug_mode.DebugModeTests.asyncSetUp
    asyncTearDown=test_debug_mode.DebugModeTests.asyncTearDown

    async def test_legacy_scope_migration_binds_only_exact_major_labels(self):
        self.db.add_all([
            CurriculumDocument(id=1,name='legacy',major='视觉传达设计',cohort='2026',revision=1,
                               original=b'x',sha256='hash',rows=[]),
            ClassInfo(name='视传2601',grade='2026',department='视觉传达设计'),
            ClassInfo(name='合作2601',grade='2026',department='视觉传达设计（合作办学）'),
        ])
        self.db.commit()
        _migrate_academic_scope_columns(self.engine)
        _migrate_academic_scope_columns(self.engine)
        program=self.db.query(AcademicProgram).filter_by(name='视觉传达设计').one()
        self.assertEqual(self.db.get(CurriculumDocument,1).program_id,program.id)
        self.assertEqual(self.db.query(ClassInfo).filter_by(name='视传2601').one().program_id,program.id)
        self.assertIsNone(self.db.query(ClassInfo).filter_by(name='合作2601').one().program_id)
        self.assertEqual(program.duration_semesters,8)

    async def test_curriculum_uses_configured_program_duration(self):
        doc=CurriculumDocument(name='five-year',major='Design',cohort='2025',revision=1,
            original=b'x',sha256='hash',duration_semesters=10,
            rows=[{'semester':10,'schedulable':True}])
        self.assertEqual(curriculum_semester(doc,'2030-03-04',2),10)

    async def test_restart_migration_preserves_immutable_legacy_documents(self):
        from app.services.immutable_records import install_immutable_triggers
        self.db.add(CurriculumDocument(name='archive',major='Design',cohort='2026',revision=1,
            original=b'archive',sha256='archived',rows=[]))
        self.db.commit()
        install_immutable_triggers(self.engine)
        _migrate_academic_scope_columns(self.engine)
        _migrate_academic_scope_columns(self.engine)
        self.assertIsNone(self.db.query(CurriculumDocument).one().program_id)


if __name__=='__main__':
    unittest.main()
