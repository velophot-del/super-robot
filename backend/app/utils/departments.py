"""专业归属解析工具。

课程可以被多个专业共享。为避免共享课程在导入时被最后一个专业覆盖，
`Course.department` 支持用逗号（中英文均可）分隔多个专业名称。
"""
import re
from typing import Any, Iterable, List, Optional

_SEPARATOR = re.compile(r"[,，;；/|]")


def split_departments(value: Any) -> List[str]:
    """把专业字段解析为去重后的专业列表。"""
    if value is None:
        return []

    if isinstance(value, (list, tuple, set)):
        raw_items: Iterable[Any] = value
    else:
        raw_items = _SEPARATOR.split(str(value))

    result: List[str] = []
    for item in raw_items:
        name = str(item).strip()
        if name and name not in result:
            result.append(name)
    return result


def merge_department(current: Any, new: Any) -> Optional[str]:
    """合并专业归属，返回新的 department 值。

    - 当前为空表示通用课程（匹配所有班级），保持为空，避免导入把通用课收窄到某个专业；
    - 当前专业与新专业相同则保持不变；
    - 否则把新专业追加到逗号分隔列表中。
    """
    current_value = str(current or "").strip()
    new_value = str(new or "").strip()

    if not current_value:
        return None
    if not new_value:
        return current_value

    departments = split_departments(current_value)
    if new_value not in departments:
        departments.append(new_value)
    return ",".join(departments)
