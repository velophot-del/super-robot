"""AI 排课分析与建议。

优先调用已配置的大模型服务；未配置、超时或返回异常时，
自动回退到基于规则的分析文本，保证接口始终可用。
"""
import json

from app.services.ai_config import LLMError, call_llm, resolve_config

SYSTEM_PROMPT = """你是学院排课系统的分析助手。根据给定的 JSON 排课数据，用中文给出简洁、可执行的审核意见。
要求：
- 只依据数据，不编造课程、教师、教室或冲突。
- 按“总体判断 / 主要风险 / 可执行建议”三部分输出。
- 主要风险按严重程度排序，引用具体课程名和教学组。
- 可执行建议 3 到 5 条，每条一句话。
- 全文不超过 500 字。"""

CATEGORY_SUGGESTIONS = (
    ('missing_weeks', '先为待排课程确认教学周段，并避开该年级考试周。'),
    ('missing_slots', '为已落实周段的课程配置周内节次，核对学时合计。'),
    ('missing_room', '为课程选择容量与类型匹配的可用教室。'),
    ('unassigned', '完成教师匹配审核并锁定授课教师。'),
    ('capacity', '调整超限教师的授课任务，或降低其周课时/课程数。'),
    ('exam_week', '调整与考试周冲突的课程周段。'),
    ('span_out_of_range', '修正超出周期范围的课程周段。'),
)


def rule_based_advice(context):
    """不依赖外部服务的确定性分析，作为兜底与降级结果。"""
    plan = context.get('plan') or {}
    stats = context.get('stats') or {}
    issues = context.get('issues') or []
    state_names = {'draft': '计划草稿', 'open': '开放填报', 'matched': '匹配待审核', 'published': '已发布'}
    lines = [
        f"【总体判断】周期「{plan.get('name', '')}」当前为{state_names.get(plan.get('state'), plan.get('state', ''))}，"
        f"共 {stats.get('total', 0)} 门课程任务；已落实周段 {stats.get('placed', 0)} 门、"
        f"周内节次 {stats.get('with_slots', 0)} 门、地点 {stats.get('with_room', 0)} 门、"
        f"授课教师 {stats.get('locked', 0)} 门。"
        + (f"仍存在 {len(issues)} 个阻塞项，暂不满足发布条件。" if issues else "当前未发现阻塞项。")
    ]
    lines.append("")
    lines.append("【主要风险】")
    if issues:
        for issue in issues[:8]:
            lines.append(f"· {issue.get('name', '')}（{issue.get('group', '')}）：{issue.get('message', '')}")
        if len(issues) > 8:
            lines.append(f"· 其余 {len(issues) - 8} 项略。")
    else:
        lines.append("· 未发现阻塞项。")
    lines.append("")
    lines.append("【可执行建议】")
    categories = {issue.get('category') for issue in issues}
    suggestions = [text for category, text in CATEGORY_SUGGESTIONS if category in categories]
    if not suggestions:
        suggestions = ['当前无阻塞项，可按流程发布；发布后如需调整请通过调课申请发起修订。']
    for index, suggestion in enumerate(suggestions, 1):
        lines.append(f"{index}. {suggestion}")
    return {'source': 'rules', 'text': '\n'.join(lines), 'issues': issues,
            'stats': stats, 'issue_count': len(issues)}


def generate_ai_advice(context, db=None):
    """生成排课分析；任何失败都回退到规则文本，且不向调用方泄露密钥或原始错误正文。"""
    fallback = rule_based_advice(context)
    config = resolve_config(db)
    if not config or not config.get('api_key'):
        return {**fallback, 'reason': '未配置 AI 服务，已使用规则分析'}
    user_text = '以下是排课周期的结构化数据：\n' + json.dumps(context, ensure_ascii=False)
    try:
        result = call_llm(config, SYSTEM_PROMPT, user_text, max_tokens=2000)
    except LLMError as exc:
        return {**fallback, 'reason': f'{exc}，已使用规则分析'}
    return {**fallback, 'source': 'llm', 'provider': config.get('provider'),
            'model': result.get('model'), 'text': result.get('text', ''),
            'usage': result.get('usage') or {}}
