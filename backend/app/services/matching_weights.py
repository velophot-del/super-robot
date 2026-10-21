"""管理员可调的教师课程匹配权重。"""
WEIGHT_ITEMS = (
    {'key': 'team', 'name': '团队成员', 'default': 40,
     'description': '教师已核实的团队课程编码命中时计满分'},
    {'key': 'direction', 'name': '专业方向', 'default': 20,
     'description': '教师专业方向与课程方向一致时计满分'},
    {'key': 'domain', 'name': '领域命中', 'default': 15,
     'description': '按课程领域标签的命中比例计分'},
    {'key': 'taught', 'name': '曾授课程', 'default': 15,
     'description': '教师已核实的曾授课程编码命中时计满分'},
    {'key': 'capacity', 'name': '剩余容量', 'default': 5,
     'description': '按教师剩余周容量比例计分'},
)
DEFAULT_WEIGHTS = {item['key']: item['default'] for item in WEIGHT_ITEMS}


def get_match_weights(plan_or_settings):
    settings = getattr(plan_or_settings, 'settings', plan_or_settings) or {}
    raw = settings.get('match_weights') or {}
    weights = {}
    for item in WEIGHT_ITEMS:
        try:
            value = int(raw.get(item['key'], item['default']))
        except (TypeError, ValueError):
            value = item['default']
        weights[item['key']] = max(0, min(100, value))
    if sum(weights.values()) <= 0:
        weights = dict(DEFAULT_WEIGHTS)
    return weights


def weights_total(weights):
    return sum(weights.values())


def weight_items(weights):
    return [{**item, 'weight': weights[item['key']]} for item in WEIGHT_ITEMS]
