"""AI 辅助的批量导入清洗：课程去重归一、教师别名与格式纠错。

规则版始终可用：基于归一化文本（全半角、空白、括号限定词、罗马数字）做确定性识别。
AI 版：让模型在规则结果之上判断“是否为同一实体”并给出规范名与修复建议；失败回退规则版。
"""
import json
import re

from app.services.ai_config import LLMError, call_llm, resolve_config

SYSTEM_PROMPT = """你是学院教务系统的数据清洗助手。给定一批待导入记录，找出疑似重复和格式问题。
要求：
- 疑似重复：同一门课/同一位教师因写法不同（括号、大小写、简称、罗马数字、繁简）被拆成多条，归为一组并给出规范名。
- 格式问题：编码缺失/重复、邮箱/电话格式异常、学分开课学期越界等，逐条指出并给修复建议。
- 只依据给定数据，不确定的不要断言；宁可少报也不误报。
- 只输出 JSON：{"duplicates":[{"canonical":"规范名","members":["原名1","原名2"],"reason":"判断依据"}],"issues":[{"name":"记录名","type":"类型","message":"问题","suggestion":"建议"}]}"""


def normalize_text(value):
    """归一化用于比对：转半角、去空白、去括号限定、罗马数字统一为阿拉伯。"""
    s = (value or '').strip()
    s = ''.join(chr(ord(c) - 0xFEE0) if 0xFF01 <= ord(c) <= 0xFF5E else c for c in s)
    s = re.sub(r'\s+', '', s)
    s = s.replace('（', '(').replace('）', ')')
    s = re.sub(r'[\(（][^）\)]*[\)）]', '', s)
    for roman, arab in [('Ⅰ', '1'), ('Ⅱ', '2'), ('Ⅲ', '3'), ('Ⅳ', '4'),
                        ('Ⅴ', '5'), ('Ⅵ', '6'), ('Ⅶ', '7'), ('Ⅷ', '8')]:
        s = s.replace(roman, arab)
    return s.casefold()


def rule_review(records, kind):
    """确定性的清洗审查：返回 {duplicates, issues}。"""
    duplicates = []
    issues = []
    buckets = {}
    code_field = 'code' if kind == 'course' else 'teacher_code'
    for index, record in enumerate(records):
        name = record.get('name', '')
        code = record.get(code_field, '')
        norm = normalize_text(name)
        buckets.setdefault(norm, []).append(record)
        if not code:
            issues.append({'name': name or f'第{index + 1}行', 'type': 'missing_code',
                           'message': '缺少编码', 'suggestion': '补填唯一编码，或允许系统自动生成内部编号'})
        elif code in {r.get(code_field) for i, r in enumerate(records) if i != index}:
            issues.append({'name': name, 'type': 'duplicate_code', 'message': f'编码 {code} 重复',
                           'suggestion': '核对是否同一实体，去重或改为唯一编码'})
        if kind == 'teacher':
            email = record.get('email', '')
            phone = record.get('phone', '')
            if email and not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', email):
                issues.append({'name': name, 'type': 'bad_email', 'message': f'邮箱 {email} 格式异常',
                               'suggestion': '修正邮箱或留空'})
            if phone and not re.fullmatch(r'[\d\-+]{6,20}', phone):
                issues.append({'name': name, 'type': 'bad_phone', 'message': f'电话 {phone} 格式异常',
                               'suggestion': '修正电话或留空'})
    for norm, members in buckets.items():
        if len(members) > 1:
            names = [m.get('name') for m in members]
            duplicates.append({'canonical': names[0], 'members': names,
                               'reason': '归一化后名称相同'})
    return {'duplicates': duplicates, 'issues': issues}


def _parse_result(text):
    text = (text or '').strip()
    if text.startswith('```'):
        parts = text.split('\n', 1)
        text = parts[1] if len(parts) > 1 else ''
        if text.rstrip().endswith('```'):
            text = text.rstrip()[:-3]
    start, end = text.find('{'), text.rfind('}')
    if start < 0 or end <= start:
        raise ValueError('AI 未返回有效 JSON')
    data = json.loads(text[start:end + 1])
    if not isinstance(data, dict):
        raise ValueError('AI 未返回有效 JSON')
    return {'duplicates': data.get('duplicates') or [], 'issues': data.get('issues') or []}


def review_batch(db, kind, records):
    """清洗审查入口；kind 为 'course' 或 'teacher'。任何失败回退规则版。"""
    if not isinstance(records, list):
        raise ValueError('records 必须是列表')
    fallback = rule_review(records, kind)
    config = resolve_config(db)
    if db is not None:
        db.rollback()
    if not config or not config.get('api_key'):
        return {'source': 'rules', 'reason': '未配置 AI 服务，已使用规则清洗', **fallback}
    if len(records) > 500:
        return {'source': 'rules', 'reason': '记录过多，使用规则清洗', **fallback}

    user_text = (f'待导入的{"课程" if kind == "course" else "教师"}记录如下：\n'
                 + json.dumps(records, ensure_ascii=False))
    try:
        result = call_llm(config, SYSTEM_PROMPT, user_text, max_tokens=3000, json_mode=True)
        ai = _parse_result(result.get('text', ''))
    except (LLMError, ValueError, TypeError, AttributeError) as exc:
        return {'source': 'rules', 'reason': f'{exc}，已使用规则清洗', **fallback}
    # 合并规则与 AI：AI 结果优先，规则结果中 AI 未覆盖的部分保留，避免漏报。
    ai_names = {name for group in ai['duplicates'] for name in group.get('members', [])}
    merged_dup = ai['duplicates'] + [g for g in fallback['duplicates']
                                     if any(n not in ai_names for n in g['members'])]
    ai_issue_names = {i.get('name') for i in ai['issues']}
    merged_issues = ai['issues'] + [i for i in fallback['issues'] if i.get('name') not in ai_issue_names]
    return {'source': 'llm', 'provider': config.get('provider'), 'model': result.get('model'),
            'duplicates': merged_dup, 'issues': merged_issues}
