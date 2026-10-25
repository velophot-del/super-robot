"""Keep published history while excluding replaced plans from current occupancy."""
from app.models.planning import AcademicPlan


def superseded_plan_ids(db):
    plans = {plan.id: plan for plan in db.query(AcademicPlan)}
    superseded = set()
    for plan in plans.values():
        if plan.state != 'published':
            continue
        seen = {plan.id}
        parent_id = (plan.settings or {}).get('supersedes_plan_id')
        while parent_id in plans and parent_id not in seen:
            seen.add(parent_id)
            superseded.add(parent_id)
            parent_id = (plans[parent_id].settings or {}).get('supersedes_plan_id')
    return superseded
