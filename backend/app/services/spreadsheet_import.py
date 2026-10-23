"""课程 XLSX 解析和逐行校验。"""
from io import BytesIO
from openpyxl import load_workbook
from app.utils.csv_parser import CSV_TEMPLATES, _convert_field_value
from app.services.course_library import normalize_course_classification


def parse_course_workbook(content: bytes):
    workbook=load_workbook(BytesIO(content),read_only=True,data_only=True)
    fields=CSV_TEMPLATES['courses']['required_fields']+CSV_TEMPLATES['courses']['optional_fields']
    aliases={name:field for field,name in CSV_TEMPLATES['courses']['field_names'].items()}
    aliases.update({field:field for field in fields})
    rows=[];errors=[]
    for sheet in workbook.worksheets:
        values=list(sheet.iter_rows(values_only=True))
        header_index=None;header_map={}
        for index,raw in enumerate(values[:15]):
            mapped={}
            for column,value in enumerate(raw):
                key=str(value or '').strip()
                if key in aliases:mapped[column]=aliases[key]
            if {'name','course_code','semester','total_hours'}.issubset(set(mapped.values())):
                header_index=index;header_map=mapped;break
        if header_index is None:
            if any(any(value not in (None,'') for value in row) for row in values):
                errors.append({'sheet':sheet.title,'row':None,'message':'前15行未找到课程名称、课程编码、上课学期、总课时表头'})
            continue
        for index,raw in enumerate(values[header_index+1:],start=header_index+2):
            if not any(value not in (None,'') for value in raw):continue
            row={}
            for column,field in header_map.items():
                if column<len(raw):row[field]=_convert_field_value(field,raw[column])
            row['_source_sheet']=sheet.title;row['_source_row']=index
            rows.append(row)
    workbook.close()
    return rows,errors


def course_row_issues(row, db):
    issues=[]
    for field,label in [('name','课程名称'),('course_code','课程编码'),('semester','上课学期'),('total_hours','总课时')]:
        if row.get(field) in (None,''):
            issues.append(f'{label}不能为空')
    try:
        if not 1<=int(row.get('semester'))<=12:issues.append('上课学期须为1至12')
    except (TypeError,ValueError):issues.append('上课学期须为1至12')
    try:
        if int(row.get('total_hours'))<1:issues.append('总课时须大于0')
    except (TypeError,ValueError):issues.append('总课时须为整数')
    weekdays=row.get('weekdays') or []
    if weekdays and (not isinstance(weekdays,list) or any(not isinstance(day,int) or not 1<=day<=7 for day in weekdays)):
        issues.append('每周上课日须为周一至周日')
    if row.get('cohort') and not str(row['cohort']).strip().removesuffix('级').isdigit():
        issues.append('适用年级请填写年份，如2026')
    if row.get('teaching_weeks') not in (None, ''):
        try:
            if not 1<=int(row['teaching_weeks'])<=20:issues.append('授课周数须为1至20')
        except (TypeError,ValueError):issues.append('授课周数须为整数')
    from app.models.teacher import Teacher
    from app.models.planning import OfferingUnit
    code=row.get('leader_teacher_code')
    teacher=db.query(Teacher).filter_by(teacher_code=str(code).strip()).first() if code else None
    if code and not teacher:issues.append(f'课程负责人工号“{code}”不存在')
    unit_code=row.get('offering_unit_code')
    unit=db.query(OfferingUnit).filter_by(code=str(unit_code).strip()).first() if unit_code else None
    if unit_code and not unit:issues.append(f'开课单位编码“{unit_code}”不存在')
    return issues,teacher.id if teacher else None,unit.id if unit else None


def normalize_course_row(row, teacher_id=None, unit_id=None):
    from app.models.course import Course
    allowed={column.name for column in Course.__table__.columns}
    result={key:value for key,value in row.items() if key in allowed and key not in {'id','created_at','updated_at'}}
    result['course_type'],result['course_nature']=normalize_course_classification(
        result.get('course_type') or '',result.get('course_nature') or '')
    if teacher_id:result['leader_teacher_id']=teacher_id
    if unit_id:result['offering_unit_id']=unit_id
    return result
