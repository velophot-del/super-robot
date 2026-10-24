"""课程导入编码规则：年级后两位 + 专业方向 + 学期 + 学期内顺序。"""
import re

from fastapi import HTTPException


DIRECTION_CODES = {
    '视觉传达设计': '01',
    '包装设计': '02',
    '数字艺术': '03',
    '时尚传播': '04',
    '智能交互设计': '05',
}


def direction_code(department):
    text = str(department or '').strip()
    matches = [code for name, code in DIRECTION_CODES.items() if name in text]
    if len(matches) != 1:
        return None
    return matches[0]


def course_code_prefix(row):
    cohort = str(row.get('cohort') or '').strip().removesuffix('级').removesuffix('届')
    if not re.fullmatch(r'\d{4}', cohort):
        raise HTTPException(422, '自动生成课程编码需要填写四位适用年级，如2024')
    code = direction_code(row.get('department'))
    if not code:
        raise HTTPException(422, f"课程“{row.get('name') or ''}”所属专业无法匹配专业方向编码，请补充规范专业名称或手工填写课程编码")
    try:
        semester = int(row.get('semester'))
    except (TypeError, ValueError):
        semester = 0
    if not 1 <= semester <= 12:
        raise HTTPException(422, '自动生成课程编码需要填写1至12的开课学期')
    return f'{cohort[-2:]}{code}{semester:02d}'


def assign_course_codes(db, rows):
    """为无编码行按输入顺序分配号段；已有编码不会重写。"""
    from app.models.course import Course

    counters = {}
    reserved = set()
    submitted_codes = set()
    for row in rows:
        value = str(row.get('course_code') or '').strip()
        if value:
            submitted_codes.add(value)
    for row in rows:
        if str(row.get('course_code') or '').strip():
            continue
        prefix = course_code_prefix(row)
        if prefix not in counters:
            existing = db.query(Course.course_code).filter(Course.course_code.like(f'{prefix}%')).all()
            suffixes = []
            for (code,) in existing:
                match = re.fullmatch(re.escape(prefix) + r'(\d{2})', str(code or ''))
                if match:
                    suffixes.append(int(match.group(1)))
            counters[prefix] = max(suffixes, default=0)
            reserved.update(str(code) for (code,) in existing)
        counters[prefix] += 1
        while (f'{prefix}{counters[prefix]:02d}' in reserved
               or f'{prefix}{counters[prefix]:02d}' in submitted_codes):
            counters[prefix] += 1
        if counters[prefix] > 99:
            raise HTTPException(409, f'编码段{prefix}已达到99门课程上限')
        row['course_code'] = f'{prefix}{counters[prefix]:02d}'
        reserved.add(row['course_code'])
    return rows
