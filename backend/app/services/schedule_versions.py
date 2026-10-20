"""排课版本解析工具。

排课条目按 `schedule_version` 分组保存。查询/导出/冲突检测在未显式指定版本时
必须固定到一个版本，否则会把多个版本的条目混在一起，产生重叠与假冲突。
版本字符串格式为 `schedule_{unix_timestamp}_{uuid8}`，按字符串倒序即为时间倒序。
"""
from typing import Optional

from sqlalchemy.orm import Session

from app.models.schedule import ScheduleEntry


def latest_schedule_version(db: Session) -> Optional[str]:
    """返回最新的排课版本号；没有任何排课时返回 None。"""
    return (
        db.query(ScheduleEntry.schedule_version)
        .filter(ScheduleEntry.schedule_version.isnot(None))
        .order_by(ScheduleEntry.schedule_version.desc())
        .limit(1)
        .scalar()
    )


def resolve_schedule_version(db: Session, version: Optional[str]) -> Optional[str]:
    """显式版本优先；未指定时退回到最新版本。"""
    version = (version or "").strip()
    return version or latest_schedule_version(db)
