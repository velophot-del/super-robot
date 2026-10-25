"""匹配结果的可解释性：用自然语言说清“为什么推荐这位教师”。

- 规则版：直接使用 score_candidate 生成的 explanation 字段（确定性，始终可用）。
- AI 版：在规则评分基础上让模型润色为更通顺的审核话术；任何失败都回退到规则版。
"""
import json

from app.services.ai_config import LLMError, call_llm, resolve_config

SYSTEM_PROMPT = """你是学院排课系统的匹配审核助手。根据给定的候选教师与规则评分，为每个候选写一句简洁的中文推荐理由。
要求：
- 只能依据给定数据，不编造教师经历或课程信息。
- 说明推荐依据（专业方向、领域命中、曾授课程、课时余量等）以及一个需要审核人留意的点（如余量偏紧）。
- 每句不超过 60 字。
- 只输出 JSON：{"items":[{"task_id":1,"teacher_id":3,"reason":"..."}]}"""


def rule_based_explanations(candidates):
    """兜底：直接复用每个候选已生成的规则说明。"""
    return [{'task_id': c.get('task_id'), 'teacher_id': c.get('teacher_id'),
             'reason': c.get('explanation', '') or '规则评分已生成，无需额外说明'}
            for c in candidates]


def _parse_items(text):
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
    items = data.get('items')
    if not isinstance(items, list) or not items:
        raise ValueError('AI 未返回推荐理由')
    return items


def explain_match_candidates(db, candidates, teacher_names, task_names):
    """为一批匹配候选生成自然语言理由；失败自动回退规则版。"""
    fallback = rule_based_explanations(candidates)
    config = resolve_config(db)
    if db is not None:
        db.rollback()
    if not config or not config.get('api_key'):
        return {'source': 'rules', 'reason': '未配置 AI 服务，使用规则说明', 'items': fallback}

    payload = []
    for c in candidates:
        if not c.get('complete'):
            continue
        payload.append({
            'task_id': c.get('task_id'),
            'teacher_id': c.get('teacher_id'),
            'task_name': task_names.get(c.get('task_id'), ''),
            'teacher_name': teacher_names.get(c.get('teacher_id'), ''),
            'professional_fit': c.get('professional_fit'),
            'normalized_total': c.get('normalized_total'),
            'components': {comp.get('name'): comp.get('score') for comp in (c.get('components') or [])},
        })
    if not payload:
        return {'source': 'rules', 'reason': '没有可解释的候选', 'items': fallback}

    user_text = '候选教师与评分如下：\n' + json.dumps(payload, ensure_ascii=False)
    try:
        result = call_llm(config, SYSTEM_PROMPT, user_text, max_tokens=2000, json_mode=True)
        items = _parse_items(result.get('text', ''))
    except (LLMError, ValueError, TypeError, AttributeError) as exc:
        return {'source': 'rules', 'reason': f'{exc}，已回退规则说明', 'items': fallback}

    by_key = {(c.get('task_id'), c.get('teacher_id')): c for c in candidates}
    merged = []
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            task_id = int(item.get('task_id'))
            teacher_id = int(item.get('teacher_id'))
        except (TypeError, ValueError):
            continue
        key = (task_id, teacher_id)
        if key in seen:
            continue
        seen.add(key)
        reason = str(item.get('reason') or '').strip()
        if not reason:
            continue
        base = by_key.get(key) or {}
        merged.append({'task_id': task_id, 'teacher_id': teacher_id,
                       'teacher_name': teacher_names.get(teacher_id, ''),
                       'reason': reason,
                       'rule_reason': base.get('explanation', '')})
    # 模型漏掉的候选，补回规则版。
    for c in candidates:
        key = (c.get('task_id'), c.get('teacher_id'))
        if key not in seen:
            merged.append({'task_id': key[0], 'teacher_id': key[1],
                           'teacher_name': teacher_names.get(key[1], ''),
                           'reason': c.get('explanation', ''),
                           'rule_reason': c.get('explanation', '')})
    return {'source': 'llm', 'provider': config.get('provider'), 'model': result.get('model'),
            'items': merged}
