"""排课约束自学习与动态优化服务

基于历史排课数据，通过统计分析和机器学习方法：
1. 分析各约束在历史方案中的被满足频率
2. 评估约束冲突的严重程度
3. 量化约束对最终方案质量的影响
4. 动态调整约束权重以优化未来排课
"""
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict
import json
from datetime import datetime


class ConstraintLearningService:
    """约束自学习服务"""

    def __init__(self):
        self.history_data: List[Dict] = []
        self.analysis_results: Dict[str, Any] = {}

    def load_history(self, history_data: List[Dict]):
        """加载历史排课数据

        Args:
            history_data: 历史排课记录，每条包含约束条件、排课方案、质量评估
        """
        self.history_data = history_data

    def analyze_constraint_satisfaction(self, constraints: List[Dict],
                                        schedule_data: List[Dict]) -> List[Dict]:
        """分析各约束的满足情况

        Args:
            constraints: 约束规则列表
            schedule_data: 排课方案数据

        Returns:
            各约束的满足率分析结果
        """
        results = []
        total_entries = max(1, len(schedule_data))

        for constraint in constraints:
            rule_type = constraint.get("rule_type", "soft")
            category = constraint.get("category", "")
            rule_expr = constraint.get("rule_expression", "{}")

            try:
                expr = json.loads(rule_expr) if isinstance(rule_expr, str) else rule_expr
            except (json.JSONDecodeError, TypeError):
                expr = {}

            # 统计该约束在方案中的违反次数
            violation_count = self._count_violations(constraint, schedule_data)

            # 计算满足率
            satisfaction_rate = 1.0 - (violation_count / total_entries)
            satisfaction_rate = max(0.0, min(1.0, satisfaction_rate))

            # 计算冲突严重程度(0-10)
            severity = min(10.0, violation_count * constraint.get("penalty_score", 1.0) / total_entries * 10)

            results.append({
                "rule_id": constraint.get("id"),
                "rule_name": constraint.get("name", "未命名规则"),
                "rule_type": rule_type,
                "category": category,
                "satisfaction_rate": round(satisfaction_rate, 4),
                "violation_count": violation_count,
                "conflict_severity_mean": round(severity, 2),
                "is_active": constraint.get("is_active", True),
            })

        return results

    def learn_from_history(self, historical_schedules: List[Dict],
                          historical_constraints: List[Dict]) -> Dict[str, Any]:
        """从历史数据中学习约束权重和模式

        Args:
            historical_schedules: 历史排课方案列表
            historical_constraints: 历史上使用的约束

        Returns:
            学习结果，包含推荐的约束调整
        """
        if not historical_schedules:
            return {"message": "历史数据不足，无法进行有效学习"}

        # 1. 统计各约束的历史满足率
        constraint_stats = defaultdict(lambda: {
            "violations": [], "satisfaction_rates": [],
            "quality_scores": [], "names": set(),
        })

        for schedule_record in historical_schedules:
            quality = schedule_record.get("quality_score", 50)
            constraints_used = schedule_record.get("constraints", [])
            violations = schedule_record.get("violations", {})
            rates = schedule_record.get("constraint_satisfaction_rates", {})
            total_entries = max(1, schedule_record.get("total_entries") or 1)

            for c in constraints_used:
                c_id = c.get("id") if c.get("id") is not None else c.get("name")
                v_count = violations.get(str(c_id), 0)
                constraint_stats[c_id]["violations"].append(v_count)
                constraint_stats[c_id]["quality_scores"].append(quality)
                constraint_stats[c_id]["names"].add(c.get("name", ""))

                if str(c_id) in rates:
                    rate = float(rates[str(c_id)])
                else:
                    rate = 1.0 - (v_count / total_entries)
                constraint_stats[c_id]["satisfaction_rates"].append(
                    max(0.0, min(1.0, rate))
                )

        # 2. 分析每个约束的影响
        constraint_impacts = []
        for c_id, stats in constraint_stats.items():
            violations_arr = np.array(stats["violations"])
            quality_arr = np.array(stats["quality_scores"])
            rates_arr = np.array(stats["satisfaction_rates"])

            avg_violations = float(np.mean(violations_arr)) if len(violations_arr) > 0 else 0
            avg_quality = float(np.mean(quality_arr)) if len(quality_arr) > 0 else 0
            avg_satisfaction = float(np.mean(rates_arr)) if len(rates_arr) > 0 else 1.0

            # 计算违反次数与方案质量的相关性
            correlation = 0.0
            if len(violations_arr) > 2 and len(quality_arr) > 2:
                try:
                    corr_matrix = np.corrcoef(violations_arr, quality_arr)
                    correlation = float(corr_matrix[0, 1]) if not np.isnan(corr_matrix[0, 1]) else 0.0
                except Exception:
                    correlation = 0.0

            # 生成推荐
            if avg_violations > 5:
                recommendation = f"该约束平均违反{avg_violations:.1f}次，建议降低权重或调整为软约束"
                suggested_weight = max(0.5, 5.0 - avg_violations * 0.5)
            elif correlation < -0.3:
                recommendation = f"该约束与方案质量呈负相关(r={correlation:.2f})，建议保留并适当提高权重"
                suggested_weight = min(10.0, 5.0 + abs(correlation) * 10)
            else:
                recommendation = "该约束表现正常，建议维持当前设置"
                suggested_weight = 5.0

            names = [name for name in stats["names"] if name]
            constraint_impacts.append({
                "rule_id": c_id,
                "rule_name": names[0] if names else str(c_id),
                "avg_violations": round(avg_violations, 2),
                "satisfaction_rate": round(avg_satisfaction, 4),
                "conflict_severity_mean": round(min(10.0, (1.0 - avg_satisfaction) * 10), 2),
                "impact_on_quality": round(correlation, 3),
                "avg_quality_when_active": round(avg_quality, 1),
                "recommendation": recommendation,
                "suggested_weight": round(suggested_weight, 1),
            })

        # 3. 全局分析
        constraint_impacts.sort(key=lambda x: abs(x["impact_on_quality"]), reverse=True)

        # 计算理想权重分配
        total_impact = sum(abs(c["impact_on_quality"]) for c in constraint_impacts) or 1
        for c in constraint_impacts:
            c["normalized_importance"] = round(abs(c["impact_on_quality"]) / total_impact, 4)

        self.analysis_results = {
            "analysis_time": datetime.now().isoformat(),
            "total_historical_records": len(historical_schedules),
            "constraint_impacts": constraint_impacts,
            "summary": self._generate_learning_summary(constraint_impacts),
        }

        return self.analysis_results

    def recommend_constraint_adjustments(self, current_constraints: List[Dict],
                                        learning_results: Dict) -> List[Dict]:
        """根据学习结果推荐约束调整

        Args:
            current_constraints: 当前约束配置
            learning_results: 学习分析结果

        Returns:
            推荐的约束调整列表
        """
        recommendations = []
        impacts = {
            str(c["rule_id"]): c
            for c in learning_results.get("constraint_impacts", [])
        }

        for constraint in current_constraints:
            c_id = constraint.get("id") if constraint.get("id") is not None else constraint.get("name")
            impact = impacts.get(str(c_id))

            if impact:
                adjustment = {
                    "rule_id": constraint.get("id"),
                    "rule_name": constraint.get("name"),
                    "current_weight": constraint.get("weight", 5.0),
                    "suggested_weight": impact.get("suggested_weight", 5.0),
                    "current_type": constraint.get("rule_type"),
                    "suggested_type": constraint.get("rule_type"),
                    "reason": impact.get("recommendation", ""),
                    "confidence": round(abs(impact.get("impact_on_quality", 0)), 2),
                }

                # 如果违反频繁且为软约束，建议降低权重
                if impact.get("avg_violations", 0) > 8 and constraint.get("rule_type") == "hard":
                    adjustment["suggested_type"] = "soft"
                    adjustment["reason"] += "。由于频繁违反，建议将此硬约束降级为软约束"

                recommendations.append(adjustment)

        return recommendations

    @staticmethod
    def _rule_expression(constraint: Dict) -> Dict[str, Any]:
        raw = constraint.get("rule_expression")
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str) and raw.strip():
            try:
                parsed = json.loads(raw)
                return parsed if isinstance(parsed, dict) else {}
            except (json.JSONDecodeError, TypeError):
                return {}
        return {}

    def count_violations(self, constraint: Dict, schedule_data: List[Dict]) -> int:
        """统计特定约束在方案中的违反次数（公开接口）。"""
        return self._count_violations(constraint, schedule_data)

    def _count_violations(self, constraint: Dict, schedule_data: List[Dict]) -> int:
        """统计特定约束在方案中的违反次数（按周分组，并解析 rule_expression）。"""
        expr = self._rule_expression(constraint)
        rule_type = (expr.get("type") or "").lower()

        if rule_type == "unique":
            fields = [str(f) for f in (expr.get("fields") or [])]
            if fields:
                return self._count_unique_violations(schedule_data, fields)
        elif rule_type == "compare":
            return self._count_compare_violations(schedule_data, expr)
        elif rule_type == "preference":
            return self._count_preference_violations(schedule_data, expr)
        elif rule_type == "distribution":
            return self._count_time_violations(schedule_data, expr)
        elif rule_type == "consecutive":
            return self._count_course_violations(schedule_data)
        elif rule_type == "balance":
            return self._count_balance_violations(schedule_data, expr)

        # 兼容没有 rule_expression 的旧规则：按 category 回退
        category = constraint.get("category", "")
        if category == "teacher":
            return self._count_unique_violations(
                schedule_data, ["teacher_id", "week_number", "day_of_week", "period_start"])
        if category == "classroom":
            return self._count_unique_violations(
                schedule_data, ["classroom_id", "week_number", "day_of_week", "period_start"])
        if category == "class":
            return self._count_unique_violations(
                schedule_data, ["class_id", "week_number", "day_of_week", "period_start"])
        if category == "time":
            return self._count_time_violations(schedule_data, expr)
        if category == "course":
            return self._count_course_violations(schedule_data)
        return 0

    @staticmethod
    def _count_unique_violations(data: List[Dict], fields: List[str]) -> int:
        """按字段组合（自动展开连续节次和教学周）统计重复占用。"""
        slot_map = defaultdict(int)
        for entry in data:
            values = {field: entry.get(field) for field in fields}
            # 规则通常只写 day_of_week + period_start，周次必须参与唯一性判断
            week = entry.get("week_number", 1)
            values.setdefault("week_number", week)

            if "period_start" in fields:
                start = entry.get("period_start", 1)
                end = entry.get("period_end", start)
                periods = range(start, end + 1)
            else:
                periods = [None]

            for period in periods:
                key_values = dict(values)
                if period is not None:
                    key_values["period_start"] = period
                slot_map[tuple(sorted(key_values.items()))] += 1

        return sum(max(0, count - 1) for count in slot_map.values())

    @staticmethod
    def _count_compare_violations(data: List[Dict], expr: Dict) -> int:
        field1 = expr.get("field1")
        field2 = expr.get("field2")
        op = (expr.get("op") or "gte").lower()
        if not field1 or not field2:
            return 0

        count = 0
        for entry in data:
            left = entry.get(field1)
            right = entry.get(field2)
            if left is None or right is None:
                continue
            try:
                left_value = float(left)
                right_value = float(right)
            except (TypeError, ValueError):
                continue
            if op in ("gte", ">="):
                violated = left_value < right_value
            elif op in ("lte", "<="):
                violated = left_value > right_value
            elif op in ("gt", ">"):
                violated = left_value <= right_value
            elif op in ("lt", "<"):
                violated = left_value >= right_value
            elif op in ("eq", "=="):
                violated = left_value != right_value
            else:
                violated = False
            if violated:
                count += 1
        return count

    @staticmethod
    def _count_preference_violations(data: List[Dict], expr: Dict) -> int:
        field = expr.get("field") or "preferred_time_slots"
        count = 0
        for entry in data:
            preferred = entry.get(field)
            if not preferred:
                continue
            try:
                slots = json.loads(preferred) if isinstance(preferred, str) else preferred
            except (json.JSONDecodeError, TypeError):
                continue
            if slots and f"{entry.get('day_of_week')}-{entry.get('period_start')}" not in slots:
                count += 1
        return count

    @staticmethod
    def _count_time_violations(data: List[Dict], expr: Dict) -> int:
        limit = int(expr.get("max_per_day", 2) or 2)
        course_day = defaultdict(int)
        for entry in data:
            hours = (entry.get("period_end", entry.get("period_start"))
                     - entry.get("period_start", 1) + 1)
            key = (entry.get("course_id"), entry.get("week_number", 1), entry.get("day_of_week"))
            course_day[key] += max(1, hours)
        return sum(max(0, count - limit) for count in course_day.values())

    @staticmethod
    def _count_balance_violations(data: List[Dict], expr: Dict) -> int:
        threshold = int(expr.get("max_diff", 4) or 4)
        class_week_hours: Dict[Tuple[int, int], Dict[int, int]] = defaultdict(
            lambda: defaultdict(int)
        )
        for entry in data:
            hours = (entry.get("period_end", entry.get("period_start"))
                     - entry.get("period_start", 1) + 1)
            class_week_hours[(entry.get("class_id"), entry.get("week_number", 1))][
                entry.get("day_of_week")
            ] += max(1, hours)

        total = 0
        for day_hours in class_week_hours.values():
            hours = [day_hours.get(day, 0) for day in range(1, 6)]
            total += max(0, max(hours) - min(hours) - threshold)
        return total

    @staticmethod
    def _count_course_violations(data: List[Dict]) -> int:
        return sum(1 for e in data
                  if e.get("requires_consecutive")
                  and (e.get("period_end", e.get("period_start"))
                      - e.get("period_start", 1) < 1))

    def _generate_learning_summary(self, impacts: List[Dict]) -> str:
        """生成学习分析摘要"""
        if not impacts:
            return "暂无足够数据进行约束学习分析。"

        high_impact = [c for c in impacts if abs(c.get("impact_on_quality", 0)) > 0.5]
        low_satisfaction = [c for c in impacts if c.get("avg_violations", 0) > 5]

        parts = []
        if high_impact:
            parts.append(f"发现{len(high_impact)}个约束对方案质量有显著影响")
        if low_satisfaction:
            parts.append(f"{len(low_satisfaction)}个约束的历史满足率偏低")

        if parts:
            return "；".join(parts) + "。建议根据分析结果调整约束权重和类型。"
        return "各约束表现稳定，无需重大调整。"
