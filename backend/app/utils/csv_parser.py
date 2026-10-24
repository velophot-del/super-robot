"""CSV模板解析工具 - 支持批量导入排课实体数据"""
import csv
import io
import re
from typing import List, Dict, Any, Tuple


# CSV模板字段映射定义
CSV_TEMPLATES = {
    "classes": {
        "required_fields": ["name", "grade"],
        "optional_fields": ["student_count", "department", "program_code", "is_active", "homeroom_teacher", "remarks"],
        "field_names": {
            "name": "班级名称",
            "grade": "年级",
            "student_count": "学生人数",
            "department": "所属专业",
            "program_code": "专业编码",
            "is_active": "纳入排课",
            "homeroom_teacher": "班主任",
            "remarks": "备注",
        }
    },
    "teachers": {
        "required_fields": ["name", "teacher_code"],
        "optional_fields": ["department", "offering_unit_code", "title", "email", "phone", "max_weekly_hours", "remarks"],
        "field_names": {
            "name": "姓名",
            "teacher_code": "工号",
            "department": "所属部门",
            "offering_unit_code": "教研室编码",
            "title": "职称",
            "email": "邮箱",
            "phone": "电话",
            "max_weekly_hours": "每周最大课时",
            "remarks": "备注",
        }
    },
    "courses": {
        "required_fields": ["name", "semester", "total_hours"],
        "optional_fields": ["course_type", "course_nature", "cohort", "teaching_weeks", "tail_hours", "weekdays",
                          "credits", "requires_consecutive",
                          "requires_lab", "priority", "department", "program_code", "direction_name", "remarks", "leader_teacher_code", "offering_unit_code"],
        "field_names": {
            "name": "课程名称",
            "course_code": "课程编码",
            "course_type": "课程类型",
            "course_nature": "课程性质",
            "semester": "上课学期",
            "cohort": "适用年级",
            "teaching_weeks": "授课周数",
            "tail_hours": "尾周学时",
            "leader_teacher_code": "课程负责人（工号）",
            "offering_unit_code": "开课单位编码",
            "weekdays": "每周上课日",
            "total_hours": "总课时",
            "credits": "学分",
            "requires_consecutive": "需连排",
            "requires_lab": "需实验室",
            "priority": "优先级",
            "department": "所属专业",
            "program_code": "专业编码",
            "direction_name": "专业方向",
            "remarks": "备注",
        }
    },
    "classrooms": {
        "required_fields": ["name", "room_code", "capacity"],
        "optional_fields": ["building", "floor", "room_type", "has_multimedia", "remarks"],
        "field_names": {
            "name": "教室名称",
            "room_code": "教室编号",
            "building": "教学楼",
            "floor": "楼层",
            "capacity": "容量",
            "room_type": "教室类型",
            "has_multimedia": "多媒体",
            "remarks": "备注",
        }
    },
}


def parse_csv_content(content: str, entity_type: str, overrides: dict | None = None) -> Tuple[List[Dict[str, Any]], List[str]]:
    """解析CSV内容

    Args:
        content: CSV文件内容（字符串）
        entity_type: 实体类型 (classes/teachers/courses/classrooms)
        overrides: 解析后强制覆盖的字段（如从年级页签导入时统一归属年级）

    Returns:
        (parsed_data, errors) - 解析成功的数据行和错误信息列表
    """
    if entity_type not in CSV_TEMPLATES:
        return [], [f"未知的实体类型: {entity_type}"]

    template = CSV_TEMPLATES[entity_type]
    required_fields = template["required_fields"]
    all_fields = required_fields + template["optional_fields"]
    overrides = overrides or {}

    data_rows = []
    errors = []

    try:
        reader = csv.DictReader(io.StringIO(content))

        # 检查CSV表头
        if reader.fieldnames is None:
            return [], ["CSV文件为空或格式错误"]

        # 创建中文表头到英文字段的映射
        header_map = {}
        field_name_map = template["field_names"]
        legacy_course_headers = {
            "学期教学次数": "semester_sessions",
            "每周上课次数": "weekly_sessions",
            "每次课时": "hours_per_session",
            "每次学时": "hours_per_session",
            "semester_sessions": "semester_sessions",
            "weekly_sessions": "weekly_sessions",
            "hours_per_session": "hours_per_session",
        }

        for header in reader.fieldnames:
            header = header.strip()
            found = False
            if entity_type == "courses" and header in legacy_course_headers:
                header_map[header] = legacy_course_headers[header]
                continue
            for eng_field, chinese_name in field_name_map.items():
                if header == chinese_name or header == eng_field:
                    header_map[header] = eng_field
                    found = True
                    break
            if not found:
                errors.append(f"警告: 无法识别的列名 '{header}'，已忽略")

        # 检查必填字段是否存在；页签指定的字段视为已提供。
        mapped_fields = set(header_map.values()) | set(overrides)
        if entity_type == "courses":
            missing_required = [f for f in ("name", "semester") if f not in mapped_fields]
            if "total_hours" not in mapped_fields and "semester_sessions" not in mapped_fields:
                missing_required.append("total_hours")
        else:
            missing_required = [f for f in required_fields if f not in mapped_fields]
        if missing_required:
            missing_names = [field_name_map.get(f, f) for f in missing_required]
            return [], [f"缺少必填字段: {', '.join(missing_names)}"]

        # 逐行解析
        for row_num, row in enumerate(reader, start=2):
            try:
                parsed_row = {}
                for orig_header, value in row.items():
                    orig_header = orig_header.strip()
                    if orig_header in header_map:
                        field = header_map[orig_header]
                        value = value.strip() if value else None
                        parsed_row[field] = _convert_field_value(field, value)

                # 页签指定的年级等字段优先，忽略文件中的同名列。
                if overrides:
                    parsed_row.update(overrides)

                if entity_type == "courses":
                    _normalize_course_schedule_fields(parsed_row)

                # 检查必填字段值
                row_errors = []
                row_required = ("name", "semester", "total_hours") if entity_type == "courses" else required_fields
                for field in row_required:
                    if field not in parsed_row or parsed_row[field] is None or parsed_row[field] == "":
                        row_errors.append(f"第{row_num}行: 必填字段'{field_name_map.get(field, field)}'为空")

                if row_errors:
                    errors.extend(row_errors)
                    continue

                data_rows.append(parsed_row)

            except Exception as e:
                errors.append(f"第{row_num}行解析失败: {str(e)}")

    except Exception as e:
        errors.append(f"CSV解析错误: {str(e)}")

    return data_rows, errors


_WEEKDAY_CHARS = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '日': 7, '天': 7}


def _parse_weekdays(value: Any) -> List[int]:
    """解析每周上课日：支持“周一,周三”“星期一、星期五”“1,3”等写法。"""
    if value is None or value == '':
        return []
    parts = list(value) if isinstance(value, (list, tuple, set)) else re.split(r'[,，、;；/\s]+', str(value).strip())
    days = set()
    for part in parts:
        text = str(part).strip()
        if not text:
            continue
        if not any(char in _WEEKDAY_CHARS for char in text):
            days.update(int(digit) for digit in re.findall(r'[1-7]', text))
            continue
        match = re.search(r'([一二三四五六日天])', text)
        if match:
            days.add(_WEEKDAY_CHARS[match.group(1)])
    return sorted(days)


def _normalize_course_schedule_fields(row: Dict[str, Any]) -> None:
    """将旧课程表的次数/每次课时字段转换为当前课程字段。"""
    legacy_values = {field: row.pop(field, None)
                     for field in ("semester_sessions", "weekly_sessions", "hours_per_session")}
    sessions = legacy_values["semester_sessions"]
    weekly_sessions = legacy_values["weekly_sessions"] or 1
    hours_per_session = legacy_values["hours_per_session"] or 2
    try:
        sessions = int(sessions) if sessions not in (None, "") else None
        weekly_sessions = max(1, int(weekly_sessions))
        hours_per_session = int(hours_per_session)
    except (TypeError, ValueError):
        return
    if row.get("total_hours") in (None, "") and sessions is not None:
        row["total_hours"] = sessions * hours_per_session
    if row.get("teaching_weeks") in (None, "") and sessions is not None:
        row["teaching_weeks"] = (sessions + weekly_sessions - 1) // weekly_sessions


def _convert_field_value(field: str, value: Any) -> Any:
    """转换字段值到正确的类型"""
    if value is None or value == "":
        return None

    # 数值类型字段
    if field == 'credits':
        try:return float(value)
        except (ValueError,TypeError):return value
    if field == 'weekdays':
        return _parse_weekdays(value)
    if field in ("student_count", "max_weekly_hours", "semester_sessions", "weekly_sessions", "hours_per_session",
                 "semester", "teaching_weeks", "tail_hours", "total_hours",
                 "priority", "capacity", "floor"):
        try:
            return int(value)
        except (ValueError, TypeError):
            return value

    # 布尔类型字段
    if field in ("requires_consecutive", "requires_lab", "has_multimedia", "is_available", "is_active"):
        if isinstance(value, str):
            return value.lower() in ("yes", "true", "是", "1", "y")
        return bool(value)

    return value


def generate_csv_template(entity_type: str) -> str:
    """生成CSV导入模板

    Args:
        entity_type: 实体类型

    Returns:
        CSV模板内容（字符串，含表头）
    """
    if entity_type not in CSV_TEMPLATES:
        return ""

    template = CSV_TEMPLATES[entity_type]
    field_names = template["field_names"]
    all_fields = template["required_fields"] + template["optional_fields"]

    output = io.StringIO()
    writer = csv.writer(output)

    # 写入中文表头
    headers = [field_names.get(f, f) for f in all_fields]
    writer.writerow(headers)

    # 写入示例数据行
    examples = _get_example_data(entity_type)
    example_row = [examples.get(f, "") for f in all_fields]
    writer.writerow(example_row)

    return output.getvalue()


def _get_example_data(entity_type: str) -> Dict[str, Any]:
    """获取示例数据"""
    examples = {
        "classes": {
            "name": "计科1班", "grade": "2026", "student_count": "50", "is_active": "是",
            "department": "计算机科学", "homeroom_teacher": "张老师", "remarks": "示范数据"
        },
        "teachers": {
            "name": "李明", "teacher_code": "T001", "department": "计算机学院",
            "title": "教授", "email": "liming@university.edu.cn",
            "phone": "13800001001", "max_weekly_hours": "16", "remarks": "示范数据"
        },
        "courses": {
            "name": "数据结构", "course_code": "", "semester": "2", "cohort": "2026",
            "teaching_weeks": "16", "tail_hours": "", "weekdays": "周一,周三",
            "course_type": "专业课", "course_nature": "必修课",
            "total_hours": "32", "credits": "4",
            "requires_consecutive": "否", "requires_lab": "否",
            "priority": "5", "department": "计算机科学", "remarks": "示范数据"
        },
        "classrooms": {
            "name": "教学楼A-101", "room_code": "A101", "building": "教学楼A",
            "floor": "1", "capacity": "60", "room_type": "普通教室",
            "has_multimedia": "是", "remarks": "示范数据"
        },
    }
    return examples.get(entity_type, {})
