"""AI驱动多目标自动排课引擎 - 基于遗传算法的智能排课优化

核心算法: 改进型遗传算法(GA) + 多目标优化
支持约束: 硬约束(必须满足) + 软约束(尽量满足)
"""
import random
import numpy as np
from typing import List, Dict, Any, Tuple, Optional, Set
from copy import deepcopy
from dataclasses import dataclass, field
from collections import defaultdict
import json
import time
import uuid

from app.utils.departments import split_departments


# ========== 数据结构定义 ==========

@dataclass
class TimeSlot:
    """时间段"""
    day: int  # 1-5 (周一至周五)
    period: int  # 1-8 (节次)

    def __hash__(self):
        return hash((self.day, self.period))

    def __eq__(self, other):
        return self.day == other.day and self.period == other.period


@dataclass
class CourseAssignment:
    """课程分配 - 排课的基本单元（基因）"""
    course_id: int
    teacher_id: int
    class_id: int
    classroom_id: int
    time_slot: TimeSlot
    is_consecutive: bool = False  # 是否连排（连续2节）
    week_number: int = 1  # 教学周次

    def __hash__(self):
        return hash((self.course_id, self.teacher_id, self.class_id,
                    self.classroom_id, self.time_slot.day, self.time_slot.period))

    def to_dict(self) -> Dict:
        return {
            "course_id": self.course_id,
            "teacher_id": self.teacher_id,
            "class_id": self.class_id,
            "classroom_id": self.classroom_id,
            "day_of_week": self.time_slot.day,
            "period_start": self.time_slot.period,
            "period_end": self.time_slot.period + (1 if self.is_consecutive else 0),
            "week_number": self.week_number,
        }


@dataclass
class Schedule:
    """排课方案 - 一个完整的课表（个体/染色体）"""
    assignments: List[CourseAssignment] = field(default_factory=list)
    fitness: float = 0.0
    hard_violations: int = 0
    soft_violations: int = 0


# ========== 排课引擎 ==========

class SchedulingEngine:
    """改进型遗传算法排课引擎"""

    def __init__(self, config: Dict[str, Any] = None):
        """初始化排课引擎

        Args:
            config: 排课配置，包含算法参数和约束权重
        """
        self.config = {
            "population_size": 100,
            "max_generations": 500,
            "mutation_rate": 0.1,
            "crossover_rate": 0.8,
            "elite_count": 5,
            "tournament_size": 3,
            "early_stop_generations": 80,
            "early_stop_threshold": 0.001,
            # 约束权重
            "hard_penalty": 1000.0,  # 硬约束违反惩罚
            "soft_penalty_multiplier": 1.0,
            # 优化目标权重
            "weight_teacher_preference": 5.0,
            "weight_room_utilization": 3.0,
            "weight_time_distribution": 4.0,
            "weight_consecutive_reward": 2.0,
        }
        if config:
            self.config.update(config)

        # 数据存储
        self.courses: Dict[int, Dict] = {}
        self.teachers: Dict[int, Dict] = {}
        self.classes: Dict[int, Dict] = {}
        self.classrooms: Dict[int, Dict] = {}
        self.constraints: List[Dict] = []
        self.existing_schedule: List[Dict] = []
        # 已配置的约束检查项（含已停用规则）：用于判断是否用配置替代内置默认检查
        self.known_constraint_checks: Set[str] = set()
        # 启用中的约束规则及其解析结果
        self.constraint_rules: List[Dict[str, Any]] = []

        # 课程-教师关联映射
        self.course_teacher_map: Dict[int, List[int]] = defaultdict(list)
        # 课程-班级关联映射（按 department 匹配）
        self.course_class_map: Dict[int, List[int]] = defaultdict(list)

        # 统计信息
        self.generation_history: List[Dict] = []
        self.best_schedule: Optional[Schedule] = None
        self.execution_time: float = 0.0

    def load_data(self, courses: List[Dict], teachers: List[Dict],
                  classes: List[Dict], classrooms: List[Dict],
                  constraints: List[Dict] = None,
                  existing_schedule: List[Dict] = None):
        """加载排课所需的基础数据"""
        self.courses = {c["id"]: c for c in courses}
        self.teachers = {t["id"]: t for t in teachers}
        self.classes = {c["id"]: c for c in classes}
        self.classrooms = {r["id"]: r for r in classrooms}
        self.constraints = constraints or []
        self.existing_schedule = existing_schedule or []

        # 解析约束规则（含停用规则，用于关闭对应的内置默认检查）
        self._prepare_constraint_rules()

        # 构建课程-教师关联：从教师数据中解析可教课程，或基于部门匹配
        self._build_course_teacher_map()
        # 构建课程-班级关联：基于 department 字段匹配
        self._build_course_class_map()

    # ========== 约束规则解析 ==========

    @staticmethod
    def _parse_rule_expression(rule: Dict) -> Dict[str, Any]:
        raw = rule.get("rule_expression")
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str) and raw.strip():
            try:
                parsed = json.loads(raw)
                return parsed if isinstance(parsed, dict) else {}
            except (json.JSONDecodeError, TypeError):
                return {}
        return {}

    @staticmethod
    def _classify_rule(rule: Dict, expr: Dict[str, Any]) -> Optional[str]:
        """把一条约束规则映射到内部检查项，无法识别时返回 None。"""
        rule_type = (expr.get("type") or "").lower()
        fields = [str(f) for f in (expr.get("fields") or [])]
        category = (rule.get("category") or "").lower()

        if rule_type == "unique":
            if "teacher_id" in fields or category == "teacher":
                return "teacher_unique"
            if "classroom_id" in fields or category == "classroom":
                return "classroom_unique"
            if "class_id" in fields or category == "class":
                return "class_unique"

        if rule_type == "compare":
            if (expr.get("field1") == "room_capacity"
                    or expr.get("field2") in ("student_count", "capacity")
                    or category == "classroom"):
                return "capacity"

        if rule_type == "preference":
            return "teacher_preference"
        if rule_type == "distribution":
            return "distribution"
        if rule_type == "consecutive":
            return "consecutive"
        if rule_type == "balance":
            return "balance"

        # 兼容没有 rule_expression 的旧规则
        return {
            "teacher": "teacher_preference",
            "classroom": "capacity",
            "class": "class_unique",
            "time": "distribution",
            "course": "consecutive",
        }.get(category)

    def _prepare_constraint_rules(self):
        self.known_constraint_checks = set()
        self.constraint_rules = []

        for rule in self.constraints:
            expr = self._parse_rule_expression(rule)
            check = self._classify_rule(rule, expr)
            if not check:
                continue

            # 停用规则也记录检查项：表示该检查由配置管理且当前关闭，
            # 从而不再回退到内置默认检查。
            self.known_constraint_checks.add(check)
            if not rule.get("is_active", True):
                continue

            self.constraint_rules.append({
                "rule": rule,
                "expr": expr,
                "check": check,
            })

    def _build_course_teacher_map(self):
        """构建课程-教师关联映射

        匹配规则（严格精确匹配）：
        1. 教师 courses_can_teach 字段明确列出该课程ID → 匹配
        2. 教师与课程 department 相同且非空 → 匹配（同专业教师可教同专业课）
        3. 以上都不满足 → 不匹配（课程无教师，排课前报错提示用户分配）

        注意：课程无专业（department为空）不会自动分配给所有教师，
        必须在教师管理中明确为该课程分配教学教师。
        """
        self.course_teacher_map.clear()

        for course_id, course in self.courses.items():
            course_depts = set(split_departments(course.get("department")))

            for teacher_id, teacher in self.teachers.items():
                matched = False

                # 规则1：检查教师的 courses_can_teach 字段（明确指定可教课程ID）
                can_teach = teacher.get("courses_can_teach")
                if can_teach:
                    try:
                        teach_list = json.loads(can_teach) if isinstance(can_teach, str) else can_teach
                        if course_id in teach_list or str(course_id) in [str(x) for x in teach_list]:
                            matched = True
                    except (json.JSONDecodeError, TypeError):
                        pass

                # 规则2：基于部门匹配（同专业教师可教同专业/共享课程）
                if not matched and course_depts:
                    teacher_dept = (teacher.get("department") or "").strip()
                    if teacher_dept and teacher_dept in course_depts:
                        matched = True

                if matched and teacher_id not in self.course_teacher_map[course_id]:
                    self.course_teacher_map[course_id].append(teacher_id)

            # 确保每个课程在 map 中都有条目（即使为空列表）
            # 防止 _create_random_schedule 中的 .get() 兜底返回所有教师
            if course_id not in self.course_teacher_map:
                self.course_teacher_map[course_id] = []

    def get_courses_without_teachers(self) -> List[Dict]:
        """获取没有教师教授的课程列表，供排课前校验使用"""
        missing = []
        for course_id, course in self.courses.items():
            if not self.course_teacher_map.get(course_id):
                missing.append({
                    "course_id": course_id,
                    "course_name": course.get("name", ""),
                    "course_code": course.get("course_code", ""),
                })
        return missing

    def get_courses_without_classes(self) -> List[Dict]:
        """获取没有匹配班级的课程列表，供排课前校验使用"""
        missing = []
        for course_id, course in self.courses.items():
            eligible = self.course_class_map.get(course_id, [])
            if not eligible:
                missing.append({
                    "course_id": course_id,
                    "course_name": course.get("name", ""),
                    "course_code": course.get("course_code", ""),
                })
        return missing

    def _build_course_class_map(self):
        """构建课程-班级关联映射：基于 department 字段匹配

        规则：
        - 课程有 department 且班级有相同 department → 匹配
        - 课程没有 department（通用课）→ 匹配所有班级
        - 班级没有 department → 匹配所有课程
        - department 不匹配 → 不分配
        """
        self.course_class_map.clear()
        all_class_ids = list(self.classes.keys())

        for course_id, course in self.courses.items():
            course_depts = set(split_departments(course.get("department")))
            if not course_depts:
                # 通用课程，可分配给所有班级
                self.course_class_map[course_id] = all_class_ids.copy()
                continue

            eligible = []
            for class_id, cls in self.classes.items():
                class_dept = (cls.get("department") or "").strip()
                if not class_dept or class_dept in course_depts:
                    eligible.append(class_id)

            self.course_class_map[course_id] = eligible  # 不兜底，无匹配班级则留空

    def generate_initial_population(self) -> List[Schedule]:
        """生成初始种群"""
        population = []
        for _ in range(self.config["population_size"]):
            schedule = self._create_random_schedule()
            population.append(schedule)
        return population

    def _create_random_schedule(self) -> Schedule:
        """创建随机排课方案

        每个课程按 semester_sessions 展开完整学期排课：
        - 每门课每学期共 semester_sessions 次排课
        - 每周排 weekly_sessions 次
        - 跨度 = semester_sessions / weekly_sessions 周
        """
        import math
        assignments = []
        days = list(range(1, self.config.get("weekdays", 5) + 1))
        periods = list(range(1, self.config.get("periods_per_day", 8) + 1))

        # 获取所有可用的时间槽
        all_slots = []
        for day in days:
            for period in periods:
                all_slots.append(TimeSlot(day, period))

        # 学期总周数（默认 20 周，用于随机 fallback）
        default_total_weeks = self.config.get("total_weeks", 20)

        for course_id, course in self.courses.items():
            weekly_sessions = course.get("weekly_sessions", 1)
            semester_sessions = course.get("semester_sessions", 16)
            needs_consecutive = course.get("requires_consecutive", False)

            # 计算该课程跨越的教学周数
            num_weeks = max(1, math.ceil(semester_sessions / max(weekly_sessions, 1)))

            # 获取可教授该课程的教师（只从已匹配的教师中选取，不兜底）
            eligible_teachers = self.course_teacher_map.get(course_id, [])
            if not eligible_teachers:
                continue

            # 获取可用的教室
            eligible_rooms = list(self.classrooms.keys())
            if course.get("requires_lab"):
                eligible_rooms = [r_id for r_id, r in self.classrooms.items()
                                 if "实验室" in r.get("room_type", "") or "机房" in r.get("room_type", "")]
            if not eligible_rooms:
                eligible_rooms = list(self.classrooms.keys())

            # 获取该课程可分配的目标班级（只从已匹配的班级中选取，不兜底）
            eligible_classes = self.course_class_map.get(course_id, [])
            if not eligible_classes:
                continue

            # 一门课在一个学期内应始终归属同一个教学班和同一位教师，
            # 否则同一课程会被拆散到多个互不相关的班级/教师。
            assigned_class = random.choice(eligible_classes)
            assigned_teacher = random.choice(eligible_teachers)

            # 已分配的学期总次数
            total_assigned = 0
            # 为此课程在每个周次中选择时间槽
            for week in range(1, num_weeks + 1):
                if total_assigned >= semester_sessions:
                    break

                # 每周重新打乱时间槽，避免所有课程挤在同一天
                week_slots = list(all_slots)
                random.shuffle(week_slots)
                assigned_this_week = 0

                for slot in week_slots:
                    if total_assigned >= semester_sessions:
                        break
                    if assigned_this_week >= weekly_sessions:
                        break

                    # 连排课程需要使用连续的节次
                    if needs_consecutive:
                        next_slot = TimeSlot(slot.day, slot.period + 1)
                        if slot.period >= periods[-1] or not any(
                                s.day == next_slot.day and s.period == next_slot.period for s in week_slots):
                            continue
                        is_consecutive = True
                        # 连排一次课占 2 个学期次数（如果课程定义如此）
                        total_assigned += 2
                        assigned_this_week += 1
                    else:
                        is_consecutive = False
                        total_assigned += 1
                        assigned_this_week += 1

                    assignment = CourseAssignment(
                        course_id=course_id,
                        teacher_id=assigned_teacher,
                        class_id=assigned_class,
                        classroom_id=random.choice(eligible_rooms),
                        time_slot=slot,
                        is_consecutive=is_consecutive,
                        week_number=week
                    )
                    assignments.append(assignment)

        schedule = Schedule(assignments=assignments)
        self._evaluate_fitness(schedule)
        return schedule

    def _evaluate_fitness(self, schedule: Schedule):
        """评估排课方案的适应度（核心评估函数）

        适应度 = - (硬约束违反数 * 硬惩罚 + 软约束违反加权和)
        适应度越高 = 方案越好 = 违反越少

        数据库中启用中的 ConstraintRule 会接管对应的检查项（冲突、容量、偏好、
        分布、连排、均衡），并按其 rule_type / weight / penalty_score 计权；
        被停用的规则会关闭对应的内置默认检查，而不是悄悄回退到默认行为。
        """
        hard_violations = 0
        hard_penalty_sum = 0.0
        soft_violations = 0
        soft_penalty_sum = 0.0
        hard_penalty = self.config["hard_penalty"]

        def add_hard(count: int, severity: float = 1.0):
            nonlocal hard_violations, hard_penalty_sum
            if count <= 0:
                return
            hard_violations += count
            hard_penalty_sum += count * hard_penalty * severity

        def add_soft(count: int, penalty: float):
            nonlocal soft_violations, soft_penalty_sum
            if count <= 0:
                return
            soft_violations += count
            soft_penalty_sum += penalty

        # === 预计算占用/分布指标（按周分组，避免跨周累加） ===
        teacher_slot_map: Dict[Tuple[int, int, int, int], int] = defaultdict(int)
        room_slot_map: Dict[Tuple[int, int, int, int], int] = defaultdict(int)
        class_slot_map: Dict[Tuple[int, int, int, int], int] = defaultdict(int)
        teacher_weekly_hours: Dict[Tuple[int, int], int] = defaultdict(int)
        course_day_map: Dict[Tuple[int, int, int], int] = defaultdict(int)
        class_day_hours: Dict[Tuple[int, int, int], int] = defaultdict(int)
        room_day_usage: Dict[Tuple[int, int, int], int] = defaultdict(int)

        for a in schedule.assignments:
            periods = [a.time_slot.period]
            if a.is_consecutive:
                periods.append(a.time_slot.period + 1)
            for period in periods:
                teacher_slot_map[(a.teacher_id, a.week_number, a.time_slot.day, period)] += 1
                room_slot_map[(a.classroom_id, a.week_number, a.time_slot.day, period)] += 1
                class_slot_map[(a.class_id, a.week_number, a.time_slot.day, period)] += 1

            teacher_weekly_hours[(a.teacher_id, a.week_number)] += 2 if a.is_consecutive else 1
            course_day_map[(a.course_id, a.week_number, a.time_slot.day)] += 2 if a.is_consecutive else 1
            class_day_hours[(a.class_id, a.week_number, a.time_slot.day)] += 2 if a.is_consecutive else 1
            room_day_usage[(a.classroom_id, a.week_number, a.time_slot.day)] += 1

        teacher_duplicates = sum(max(0, v - 1) for v in teacher_slot_map.values())
        room_duplicates = sum(max(0, v - 1) for v in room_slot_map.values())
        class_duplicates = sum(max(0, v - 1) for v in class_slot_map.values())

        capacity_strict = 0
        capacity_tolerant = 0
        department_mismatches = 0
        unavailable_violations = 0
        preference_violations = 0

        for a in schedule.assignments:
            classroom = self.classrooms.get(a.classroom_id, {})
            class_info = self.classes.get(a.class_id, {})
            capacity = classroom.get("capacity") or 0
            students = class_info.get("student_count") or 0
            if capacity > 0 and students > capacity:
                capacity_strict += 1
            if capacity > 0 and students > capacity * 1.2:
                capacity_tolerant += 1

            eligible = self.course_class_map.get(a.course_id, [])
            if eligible and a.class_id not in eligible:
                department_mismatches += 1

            teacher = self.teachers.get(a.teacher_id, {})
            unavailable = teacher.get("unavailable_slots")
            if unavailable:
                try:
                    unavail = json.loads(unavailable) if isinstance(unavailable, str) else unavailable
                    if f"{a.time_slot.day}-{a.time_slot.period}" in unavail:
                        unavailable_violations += 1
                except (json.JSONDecodeError, TypeError):
                    pass

            preferred = teacher.get("preferred_time_slots")
            if preferred:
                try:
                    pref_slots = json.loads(preferred) if isinstance(preferred, str) else preferred
                    if pref_slots and f"{a.time_slot.day}-{a.time_slot.period}" not in pref_slots:
                        preference_violations += 1
                except (json.JSONDecodeError, TypeError):
                    pass

        # 每门课每周每天的课时分布（超过 max_per_day 的部分）
        distribution_excess = sum(max(0, hours - 2) for hours in course_day_map.values())

        # 每个班级每周的每日课时均衡度（超过 4 课时差距的部分）
        weekdays = self.config.get("weekdays", 5)
        class_week_hours: Dict[Tuple[int, int], List[int]] = {}
        for (class_id, week, day), hours in class_day_hours.items():
            class_week_hours.setdefault((class_id, week), [0] * weekdays)[day - 1] += hours
        balance_excess = sum(
            max(0, max(hours) - min(hours) - 4)
            for hours in class_week_hours.values()
            if any(hours)
        )

        # === 内置硬约束（未被配置规则接管的部分） ===
        for check, count in (
            ("teacher_unique", teacher_duplicates),
            ("classroom_unique", room_duplicates),
            ("class_unique", class_duplicates),
        ):
            if check not in self.known_constraint_checks:
                add_hard(count)

        if "capacity" not in self.known_constraint_checks:
            # 默认保留 20% 容忍度；配置了容量规则时由规则执行严格比较
            add_hard(capacity_tolerant)

        # 教师每周课时上限
        teacher_max_weekly: Dict[int, int] = defaultdict(int)
        for (t_id, _week), hours in teacher_weekly_hours.items():
            teacher_max_weekly[t_id] = max(teacher_max_weekly[t_id], hours)
        for t_id, max_hours in teacher_max_weekly.items():
            limit = self.teachers.get(t_id, {}).get("max_weekly_hours", 20)
            if limit and max_hours > limit:
                add_hard(max_hours - limit)

        # 课程-班级部门匹配、教师不可用时间始终是硬约束
        add_hard(department_mismatches)
        add_hard(unavailable_violations, severity=3.0)

        # === 内置软约束（未被配置规则接管的部分） ===
        if "teacher_preference" not in self.known_constraint_checks:
            add_soft(preference_violations,
                     preference_violations * self.config["weight_teacher_preference"] * 0.5)

        if "distribution" not in self.known_constraint_checks:
            add_soft(distribution_excess,
                     distribution_excess * self.config["weight_time_distribution"])

        if "balance" not in self.known_constraint_checks:
            add_soft(balance_excess,
                     balance_excess * self.config["weight_time_distribution"] * 0.5)

        # 教室利用率均衡（内置目标，暂不支持规则配置）
        for r_id in self.classrooms:
            for week in range(1, 21):
                day_usage = [room_day_usage.get((r_id, week, d), 0) for d in range(1, weekdays + 1)]
                if day_usage and max(day_usage) > 0:
                    variance = np.var(day_usage) if len(day_usage) > 1 else 0
                    soft_penalty_sum += variance * self.config["weight_room_utilization"] * 0.3

        # === 应用配置的约束规则（含停用规则对内置检查的接管） ===
        check_counts = {
            "teacher_unique": teacher_duplicates,
            "classroom_unique": room_duplicates,
            "class_unique": class_duplicates,
            "capacity": capacity_strict,
            "teacher_preference": preference_violations,
            "consecutive": 0,
        }

        for item in self.constraint_rules:
            check = item["check"]
            expr = item["expr"]
            rule = item["rule"]

            if check == "distribution":
                limit = int(expr.get("max_per_day", 2) or 2)
                count = sum(max(0, hours - limit) for hours in course_day_map.values())
            elif check == "balance":
                threshold = int(expr.get("max_diff", 4) or 4)
                count = sum(
                    max(0, max(hours) - min(hours) - threshold)
                    for hours in class_week_hours.values()
                    if any(hours)
                )
            elif check == "consecutive":
                count = sum(
                    1 for a in schedule.assignments
                    if self.courses.get(a.course_id, {}).get("requires_consecutive")
                    and not a.is_consecutive
                )
            else:
                count = check_counts.get(check, 0)

            if count <= 0:
                continue

            rule_type = (rule.get("rule_type") or "soft").lower()
            weight = float(rule.get("weight") if rule.get("weight") is not None else 1.0)
            penalty = float(rule.get("penalty_score")
                            if rule.get("penalty_score") is not None else 10.0)

            if rule_type == "hard":
                add_hard(count, severity=max(0.1, weight / 5.0))
            else:
                add_soft(count, count * max(0.1, weight) * max(0.1, penalty) / 10.0)

        # 计算总适应度（越高越好）
        total_penalty = (hard_penalty_sum +
                         soft_penalty_sum * self.config["soft_penalty_multiplier"])

        schedule.hard_violations = hard_violations
        schedule.soft_violations = soft_violations
        schedule.fitness = -total_penalty  # 负值，越接近0越好

    def _selection(self, population: List[Schedule]) -> Schedule:
        """锦标赛选择"""
        tournament = random.sample(population, min(self.config["tournament_size"], len(population)))
        return max(tournament, key=lambda s: s.fitness)

    def _crossover(self, parent1: Schedule, parent2: Schedule) -> Tuple[Schedule, Schedule]:
        """交叉操作 - 基于课程分组的均匀交叉"""
        if random.random() > self.config["crossover_rate"]:
            return deepcopy(parent1), deepcopy(parent2)

        child1 = Schedule()
        child2 = Schedule()

        # 按课程分组
        p1_by_course: Dict[int, List[CourseAssignment]] = defaultdict(list)
        p2_by_course: Dict[int, List[CourseAssignment]] = defaultdict(list)
        for a in parent1.assignments:
            p1_by_course[a.course_id].append(a)
        for a in parent2.assignments:
            p2_by_course[a.course_id].append(a)

        all_courses = set(list(p1_by_course.keys()) + list(p2_by_course.keys()))

        for course_id in all_courses:
            if random.random() < 0.5:
                child1.assignments.extend(deepcopy(p1_by_course.get(course_id, [])))
                child2.assignments.extend(deepcopy(p2_by_course.get(course_id, [])))
            else:
                child1.assignments.extend(deepcopy(p2_by_course.get(course_id, [])))
                child2.assignments.extend(deepcopy(p1_by_course.get(course_id, [])))

        for child in [child1, child2]:
            self._evaluate_fitness(child)

        return child1, child2

    def _mutation(self, schedule: Schedule):
        """变异操作"""
        if not schedule.assignments:
            return schedule

        for i, assignment in enumerate(schedule.assignments):
            if random.random() < self.config["mutation_rate"]:
                # 随机选择变异类型
                mutation_type = random.choice(["teacher", "classroom", "timeslot", "class", "swap"])

                if mutation_type == "teacher":
                    eligible = self.course_teacher_map.get(assignment.course_id, [])
                    if eligible and len(eligible) > 1:
                        # 同一门课的所有周次保持同一位教师
                        new_teacher = random.choice(eligible)
                        for other in schedule.assignments:
                            if other.course_id == assignment.course_id:
                                other.teacher_id = new_teacher

                elif mutation_type == "classroom":
                    course = self.courses.get(assignment.course_id, {})
                    eligible = list(self.classrooms.keys())
                    if course.get("requires_lab"):
                        lab_rooms = [r_id for r_id, r in self.classrooms.items()
                                    if "实验室" in r.get("room_type", "") or "机房" in r.get("room_type", "")]
                        if lab_rooms:
                            eligible = lab_rooms
                    if eligible:
                        assignment.classroom_id = random.choice(eligible)

                elif mutation_type == "class":
                    eligible = self.course_class_map.get(assignment.course_id, [])
                    if eligible and len(eligible) > 1:
                        current = assignment.class_id
                        others = [c for c in eligible if c != current]
                        if others:
                            # 同一门课的所有周次保持同一个教学班
                            new_class = random.choice(others)
                            for other in schedule.assignments:
                                if other.course_id == assignment.course_id:
                                    other.class_id = new_class

                elif mutation_type == "timeslot":
                    days = list(range(1, self.config.get("weekdays", 5) + 1))
                    max_period = self.config.get("periods_per_day", 8)
                    assignment.time_slot = TimeSlot(
                        day=random.choice(days),
                        period=random.randint(1, max_period - (1 if assignment.is_consecutive else 0))
                    )

                elif mutation_type == "swap" and len(schedule.assignments) > 1:
                    # 随机交换两个分配的时间槽
                    j = random.randint(0, len(schedule.assignments) - 1)
                    if i != j:
                        other = schedule.assignments[j]
                        assignment.time_slot, other.time_slot = other.time_slot, assignment.time_slot
                        assignment.classroom_id, other.classroom_id = other.classroom_id, assignment.classroom_id

        self._evaluate_fitness(schedule)
        return schedule

    def run(self, progress_callback=None) -> Dict[str, Any]:
        """运行遗传算法排课

        Args:
            progress_callback: 进度回调函数，接收(当前代数, 最佳适应度, 平均适应度)

        Returns:
            排课结果字典
        """
        start_time = time.time()
        self.generation_history = []

        # 生成初始种群
        population = self.generate_initial_population()

        best_fitness_history = []
        generations_no_improve = 0

        for gen in range(self.config["max_generations"]):
            # 评估所有个体
            for schedule in population:
                if schedule.fitness == 0 and schedule.hard_violations == 0:
                    self._evaluate_fitness(schedule)

            # 按适应度排序
            population.sort(key=lambda s: s.fitness, reverse=True)
            current_best = population[0]

            # 记录历史
            avg_fitness = np.mean([s.fitness for s in population])
            self.generation_history.append({
                "generation": gen,
                "best_fitness": current_best.fitness,
                "avg_fitness": float(avg_fitness),
                "hard_violations": current_best.hard_violations,
                "soft_violations": current_best.soft_violations,
            })

            # 进度回调
            if progress_callback:
                progress_callback(gen, current_best.fitness, avg_fitness)

            # 早停检查
            best_fitness_history.append(current_best.fitness)
            if len(best_fitness_history) > 1:
                if abs(best_fitness_history[-1] - best_fitness_history[-2]) < self.config["early_stop_threshold"]:
                    generations_no_improve += 1
                else:
                    generations_no_improve = 0

            if (generations_no_improve >= self.config["early_stop_generations"]
                    and current_best.hard_violations == 0):
                break

            # 创建下一代
            new_population = []

            # 精英保留
            elite_count = min(self.config["elite_count"], len(population))
            for i in range(elite_count):
                new_population.append(deepcopy(population[i]))

            # 生成新个体
            while len(new_population) < self.config["population_size"]:
                parent1 = self._selection(population)
                parent2 = self._selection(population)
                child1, child2 = self._crossover(parent1, parent2)

                self._mutation(child1)
                self._mutation(child2)

                new_population.append(child1)
                if len(new_population) < self.config["population_size"]:
                    new_population.append(child2)

            population = new_population

        # 最终排序
        population.sort(key=lambda s: s.fitness, reverse=True)
        self.best_schedule = population[0]
        self.execution_time = time.time() - start_time

        return self._build_result()

    def _build_result(self) -> Dict[str, Any]:
        """构建排课结果"""
        if not self.best_schedule:
            return {"success": False, "error": "未能生成有效排课方案"}

        entries = []
        for a in self.best_schedule.assignments:
            entry = {
                "course_id": a.course_id,
                "teacher_id": a.teacher_id,
                "class_id": a.class_id,
                "classroom_id": a.classroom_id,
                "day_of_week": a.time_slot.day,
                "period_start": a.time_slot.period,
                "period_end": a.time_slot.period + (1 if a.is_consecutive else 0),
                "week_number": a.week_number,
                "is_consecutive": a.is_consecutive,
                "course_name": self.courses.get(a.course_id, {}).get("name", ""),
                "teacher_name": self.teachers.get(a.teacher_id, {}).get("name", ""),
                "class_name": self.classes.get(a.class_id, {}).get("name", ""),
                "classroom_name": self.classrooms.get(a.classroom_id, {}).get("name", ""),
            }
            entries.append(entry)

        # 计算质量评分 (0-100)
        max_possible_fitness = 0  # 最佳情况适应度为0
        min_possible_fitness = -10000  # 假设最差情况
        fitness = self.best_schedule.fitness
        quality_score = max(0, min(100, 100 * (1 - abs(fitness) / abs(min_possible_fitness))))

        return {
            "success": True,
            "version": f"schedule_{int(time.time())}_{uuid.uuid4().hex[:8]}",
            "total_entries": len(entries),
            "hard_conflicts": self.best_schedule.hard_violations,
            "soft_conflicts": self.best_schedule.soft_violations,
            "quality_score": round(quality_score, 1),
            "execution_time": round(self.execution_time, 2),
            "algorithm": f"遗传算法(GA) - 种群{self.config['population_size']}, 进化{len(self.generation_history)}代",
            "generation_history": self.generation_history[-10:],  # 最后10代历史
            "entries": entries,
        }
