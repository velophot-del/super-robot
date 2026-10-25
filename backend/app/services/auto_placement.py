"""为已匹配的阶段任务生成可独立校验的周期重复节次与教室候选。"""
from itertools import product
from collections import defaultdict
from copy import deepcopy
from datetime import timedelta
import random
from fastapi import HTTPException
from app.models.classroom import Classroom
from app.models.teacher import Teacher
from app.models.planning import AcademicPlan,PeriodSlot,TeachingAssignment,TeachingTask
from app.services.stage_planning import task_dict,validate_tasks,capacity


def _int(value):
    try:return int(float(value))
    except (TypeError,ValueError):return None


def _chunks(hours,unit,consecutive):
    if hours<=0 or unit<=0:return []
    sizes=[];remaining=hours
    while remaining:
        size=min(unit,remaining)
        if consecutive and size<2:return []
        sizes.append(size);remaining-=size
    return sizes


def _patterns(hours,unit,consecutive,days=None,limit=32):
    sizes=_chunks(hours,unit,consecutive)
    if not sizes:return []
    allowed=sorted({day for day in (days or []) if isinstance(day,int) and 1<=day<=7}) or [1,2,3,4,5]
    candidates=[[(day,start,size) for day in allowed for start in range(1,10-size)] for size in sizes]
    found=[];nodes=0
    def visit(index,chosen):
        nonlocal nodes
        if len(found)>=250 or nodes>=12000:return
        if index==len(sizes):
            found.append(tuple(sorted(chosen)));return
        for block in candidates[index]:
            nodes+=1
            day,start,size=block
            if any(day==d and start<p+length and p<start+size for d,p,length in chosen):continue
            visit(index+1,[*chosen,block])
    visit(0,[])
    def score(pattern):
        days=[d for d,_,_ in pattern]
        return (-len(set(days)),sum(start for _,start,_ in pattern),pattern)
    return sorted(set(found),key=score)[:limit]


def _task_patterns(task):
    metadata=(task.get('source') or {}).get('course_metadata') or {}
    span=task['end_week']-task['start_week']+1
    tail_weeks=max(0,min(span,int(task.get('tail_weeks') or 0)))
    normal_weeks=span-tail_weeks
    required=_int(task.get('required_hours'))
    if required is None or required<1:raise ValueError('计划学时缺失或无效')
    weekly=_int(metadata.get('weekly_hours'))
    tail=_int(metadata.get('tail_hours')) if metadata.get('tail_hours') not in (None,'') else None
    if not tail_weeks:
        if weekly is None:
            if required%span:raise ValueError('总学时不能均分到教学周，需补充周课时或尾周学时')
            weekly=required//span
        tail=0
    elif tail is None:
        if weekly is None:
            if required%span:raise ValueError('缺少周课时和尾周学时，无法确定节次')
            weekly=required//span
        tail=weekly
    elif weekly is None:
        remaining=required-tail*tail_weeks
        if normal_weeks<=0 or remaining%normal_weeks:raise ValueError('总学时与尾周学时不匹配，无法确定节次')
        weekly=remaining//normal_weeks
    if weekly*normal_weeks+tail*tail_weeks!=required:
        raise ValueError('周课时、尾周学时与总学时不一致')
    unit=_int(metadata.get('hours_per_session')) or 2
    consecutive=bool(metadata.get('requires_consecutive') or task.get('requires_consecutive'))
    days=metadata.get('weekdays') or task.get('weekdays') or []
    normal_patterns=_patterns(weekly,unit,consecutive,days) if normal_weeks else [()]
    tail_patterns=_patterns(tail or 0,unit,consecutive,days) if tail_weeks and tail else [()]
    if not normal_patterns or not tail_patterns:raise ValueError('周课时无法拆分为每天1至8节的可排时段')
    return [tuple([*normal,*tail]) for normal,tail in product(normal_patterns,tail_patterns)][:128],normal_weeks,tail_weeks


def _room_candidates(db,task,usage):
    metadata=(task.get('source') or {}).get('course_metadata') or {}
    required=task.get('max_students') or task.get('student_count') or 0
    room_type=task.get('room_type') or metadata.get('room_type') or ''
    needs_lab=metadata.get('requires_lab') or task.get('requires_lab')
    rows=[r for r in db.query(Classroom).filter(Classroom.is_available.is_(True)).all()
        if (not required or r.capacity>=required)
        and (not room_type or room_type==r.room_type)
        and (not needs_lab or any(word in (r.room_type or '') for word in ('实验室','机房')))]
    rows.sort(key=lambda r:(usage[r.id],r.capacity,r.id))
    if task.get('room_id'):
        rows=[r for r in rows if r.id==task['room_id']]
    return rows


def _slots_for_pattern(task,pattern,normal_weeks,tail_weeks):
    if task.get('slots'):
        return [{key:slot.get(key,default) for key,default in [('day',1),('start',1),('count',1),('phase','normal')]}
                for slot in task['slots']]
    metadata=(task.get('source') or {}).get('course_metadata') or {}
    weekly=_int(metadata.get('weekly_hours'))
    tail=_int(metadata.get('tail_hours')) if metadata.get('tail_hours') not in (None,'') else None
    if not tail_weeks:
        weekly=_int(task['required_hours'])//(task['end_week']-task['start_week']+1);tail=0
    elif weekly is None:
        tail=tail if tail is not None else 0
        weekly=(_int(task['required_hours'])-tail*tail_weeks)//normal_weeks
    else:
        tail=tail if tail is not None else weekly
    unit=_int(metadata.get('hours_per_session')) or 2
    normal_size=len(_chunks(weekly or 0,unit,bool(metadata.get('requires_consecutive') or task.get('requires_consecutive'))))
    slots=[{'day':d,'start':start,'count':count,'phase':'normal'} for d,start,count in pattern[:normal_size]]
    if tail_weeks and tail:
        slots.extend({'day':d,'start':start,'count':count,'phase':'tail'} for d,start,count in pattern[normal_size:])
    return slots


def _soft_score(tasks):
    room_usage=defaultdict(int);group_day=defaultdict(int);teacher_day=defaultdict(int)
    for task in tasks:
        if task.get('room_id'):room_usage[task['room_id']]+=1
        for slot in task.get('slots',[]):
            phase=slot.get('phase','normal')
            weeks=range(task['start_week'],task['end_week']+1)
            for week in weeks:
                tail_weeks=int(task.get('tail_weeks') or 0)
                actual_phase='tail' if tail_weeks and week>task['end_week']-tail_weeks else 'normal'
                if phase!=actual_phase:continue
                group_day[(task['group'],week,slot['day'])]+=slot['count']
                for teacher_id in task.get('teacher_ids',[]):
                    teacher_day[(teacher_id,week,slot['day'])]+=slot['count']
    group_loads=list(group_day.values());teacher_loads=list(teacher_day.values())
    balance=sum(max(0,value-4) for value in group_loads)+sum(max(0,value-6) for value in teacher_loads)
    room_spread=max(room_usage.values(),default=0)-min(room_usage.values(),default=0) if len(room_usage)>1 else 0
    late_periods=sum(max(0,slot['start']+slot['count']-7) for task in tasks for slot in task.get('slots',[]))
    return float(balance*3+room_spread+late_periods*0.1)


def _published_teacher_tasks(db,plan):
    from app.services.stage_planning import task_dict
    from app.services.plan_versions import superseded_plan_ids
    chosen=defaultdict(list);supersedes=(plan.settings or {}).get('supersedes_plan_id')
    superseded = superseded_plan_ids(db)
    end_date=plan.start_date+timedelta(weeks=plan.weeks)
    for other_plan in db.query(AcademicPlan).filter(AcademicPlan.state=='published',AcademicPlan.id!=plan.id,AcademicPlan.id!=supersedes):
        if other_plan.id in superseded:continue
        if not (other_plan.start_date<end_date and other_plan.start_date+timedelta(weeks=other_plan.weeks)>plan.start_date):continue
        for assignment in db.query(TeachingAssignment):
            other_task=db.get(TeachingTask,assignment.task_id)
            if not other_task or other_task.plan_id!=other_plan.id:continue
            data=task_dict(db,other_task)
            for teacher_id in assignment.teacher_ids:chosen[teacher_id].append((data,other_plan))
    return chosen


def _draft_task_order(tasks):
    def key(task):
        metadata=(task.get('source') or {}).get('course_metadata') or {}
        return (str(task.get('major') or task.get('department') or (task.get('source') or {}).get('major') or ''),
            _int(metadata.get('semester')) or 99,task.get('start_week') or 99,
            -(_int(task.get('required_hours')) or 0),task['id'])
    return sorted(tasks,key=key)


def build_auto_schedule_candidate(db,plan,algorithm='genetic',task_order=None):
    if plan.state!='matched':raise HTTPException(409,'自动编排仅在教师匹配审核阶段运行')
    from app.api.planning import profile_for,assigned_tasks
    tasks=tasks_for_plan(db,plan)
    if not tasks:raise HTTPException(409,'周期没有课程任务')
    blocked=[];pending=[]
    for task in tasks:
        if not task.get('start_week') or not task.get('end_week'):
            blocked.append({'task_id':task['id'],'name':task['name'],'reason':'尚未安排教学周段'});continue
        if not task.get('locked') or len(task.get('teacher_ids') or [])!=task.get('teacher_count'):
            blocked.append({'task_id':task['id'],'name':task['name'],'reason':'教师安排尚未审核锁定'});continue
        if not task.get('slots') or not task.get('room_id'):
            try:
                if task.get('slots'):
                    patterns,normal_weeks,tail_weeks=[()],0,0
                else:
                    patterns,normal_weeks,tail_weeks=_task_patterns(task)
                pending.append((task,patterns,normal_weeks,tail_weeks))
            except ValueError as exc:
                blocked.append({'task_id':task['id'],'name':task['name'],'reason':str(exc)})
    if blocked:raise HTTPException(409,{'message':'存在未满足自动编排条件的任务，未生成候选','blocked':blocked})

    scheduled=[];usage=defaultdict(int)
    pending_ids={item[0]['id'] for item in pending}
    for task in tasks:
        if task.get('slots') and task['id'] not in pending_ids:
            scheduled.append(task)
            if task.get('room_id'):usage[task['room_id']]+=1
    teacher_chosen=_published_teacher_tasks(db,plan)
    for task in scheduled:
        for teacher_id in task.get('teacher_ids',[]):
            teacher_chosen[teacher_id].append((task,plan))

    priority={task_id:index for index,task_id in enumerate(task_order or [])}
    pending.sort(key=lambda item:(priority.get(item[0]['id'],len(priority)+item[0]['id']),
        len(_room_candidates(db,item[0],usage)),len(item[1]),-item[0].get('required_hours',0)))
    options=[]
    for task,patterns,normal_weeks,tail_weeks in pending:
        task_options=[]
        for pattern in patterns:
            slots=_slots_for_pattern(task,pattern,normal_weeks,tail_weeks)
            for room in _room_candidates(db,task,usage):
                task_options.append({**task,'room_id':room.id,'room_type':task.get('room_type') or room.room_type,
                    'room_name':room.name,'slots':slots})
        options.append(task_options[:160])
    if any(not choices for choices in options):
        raise HTTPException(409,{'message':'没有符合容量、类型和有效状态的教室候选','blocked':[
            {'task_id':task['id'],'name':task['name'],'reason':'没有可用教室或节次候选'}
            for (task,*_),choices in zip(pending,options) if not choices]})

    def valid_selected(selected):
        complete=[*scheduled,*selected]
        try:
            validate_tasks(db,plan,complete)
            from app.api.stage_designer import validate_spans
            validate_spans(plan,complete,db)
        except HTTPException:
            return None
        chosen={teacher:list(rows) for teacher,rows in teacher_chosen.items()}
        for candidate in selected:
            for teacher_id in candidate['teacher_ids']:
                existing=chosen.get(teacher_id,[])
                reasons,_=capacity(db,plan,candidate,teacher_id,profile_for(db,teacher_id),existing)
                if reasons:return None
                chosen.setdefault(teacher_id,[]).append((candidate,plan))
        return selected

    def validate_genes(genes):
        selected=[choices[index] for choices,index in zip(options,genes)]
        return valid_selected(selected)

    rng=random.Random((plan.id or 0)*100003+plan.revision)
    seed_genes=[];seed_rows=[];nodes=0;max_nodes=12000
    def seed_search(index,genes):
        nonlocal nodes,seed_genes,seed_rows
        if index==len(options):
            rows=validate_genes(genes)
            if rows is not None:seed_genes=list(genes);seed_rows=rows;return True
            return False
        choices=list(range(len(options[index])));rng.shuffle(choices)
        for choice in choices:
            nodes+=1
            if nodes>max_nodes:return False
            partial=[options[i][gene] for i,gene in enumerate([*genes,choice])]
            if valid_selected(partial) is None:continue
            if seed_search(index+1,[*genes,choice]):return True
        return False
    if options and not seed_search(0,[]):
        raise HTTPException(409,{'message':'当前硬约束下未找到完整课表候选，原课表未改变','blocked':[
            {'task_id':task['id'],'name':task['name'],'reason':'无可行时段或教室组合'} for task,*_ in pending]})

    algorithm=algorithm if algorithm in {'genetic','backtracking'} else 'genetic'
    best_genes=list(seed_genes);best_rows=seed_rows;best_score=_soft_score([*scheduled,*best_rows]);generations=0
    if algorithm=='genetic' and options:
        population=[list(seed_genes)]
        for _ in range(23):population.append([rng.randrange(len(choices)) for choices in options])
        scored=[]
        for generation in range(24):
            scored=[]
            for genes in population:
                rows=validate_genes(genes)
                if rows is None:score=float('inf')
                else:
                    score=_soft_score([*scheduled,*rows])
                    if score<best_score:best_score=score;best_genes=list(genes);best_rows=rows
                scored.append((score,genes))
            scored.sort(key=lambda item:item[0])
            generations=generation+1
            next_population=[list(genes) for _,genes in scored[:4]]
            while len(next_population)<24:
                first=rng.choice(scored[:max(4,len(scored)//2)])[1]
                second=rng.choice(scored[:max(4,len(scored)//2)])[1]
                pivot=rng.randrange(len(options)) if options else 0
                child=list(first[:pivot])+list(second[pivot:])
                if child and rng.random()<0.35:
                    gene=rng.randrange(len(child));child[gene]=rng.randrange(len(options[gene]))
                next_population.append(child)
            population=next_population

    solution=best_rows
    teacher_names={row.id:row.name for row in db.query(Teacher)}
    return {'success':True,'algorithm':algorithm,'score':best_score,'generations':generations,
        'scheduled':len(solution),'tasks':[{'task_id':task['id'],'name':task['name'],'group':task['group'],
            'major':task.get('major') or task.get('department') or (task.get('source') or {}).get('major') or '',
            'semester':((task.get('source') or {}).get('course_metadata') or {}).get('semester'),
            'teacher_ids':task['teacher_ids'],'teacher_names':[teacher_names.get(tid,'') for tid in task['teacher_ids']],
            'start_week':task['start_week'],'end_week':task['end_week'],
            'room_id':task['room_id'],'room_name':task['room_name'],'room_type':task['room_type'],
            'slots':task['slots']} for task in solution]}


def build_ai_draft_candidate(db,plan):
    """AI supplies a course order; the constraint solver remains responsible for placements."""
    from app.services.ai_config import LLMError,call_llm,resolve_config
    tasks=tasks_for_plan(db,plan)
    ordered=_draft_task_order(tasks)
    config=resolve_config(db)
    source='rules';model=None
    if db is not None:db.rollback()
    if config and config.get('api_key'):
        context=[{'task_id':task['id'],'name':task['name'],'group':task.get('group',''),
            'major':task.get('major') or task.get('department') or (task.get('source') or {}).get('major') or '',
            'cohort':task.get('cohort') or (task.get('source') or {}).get('cohort') or '',
            'semester':((task.get('source') or {}).get('course_metadata') or {}).get('semester'),
            'course_type':((task.get('source') or {}).get('course_metadata') or {}).get('course_type'),
            'start_week':task.get('start_week'),'end_week':task.get('end_week'),
            'required_hours':task.get('required_hours')} for task in ordered]
        try:
            result=call_llm(config,
                '你是课程编排助手。只返回JSON对象，格式为{"task_ids":[整数...]}。按专业培养逻辑、开课学期、课程先后衔接给出任务优先顺序。只能使用输入中的task_id，必须完整且不重复；不要调整课程周段，不要生成节次、教师或教室。',
                '请排序以下课程任务：\n'+json.dumps(context,ensure_ascii=False),max_tokens=2000,json_mode=True)
            payload=json.loads(result.get('text',''))
            ids=payload.get('task_ids') if isinstance(payload,dict) else None
            known={task['id'] for task in tasks}
            if isinstance(ids,list) and len(ids)==len(known) and set(ids)==known:
                ordered=sorted(tasks,key=lambda task:ids.index(task['id']))
                source='llm';model=result.get('model')
        except (LLMError,ValueError,TypeError,AttributeError):
            pass
    candidate=build_auto_schedule_candidate(db,plan,'backtracking',[task['id'] for task in ordered])
    candidate.update({'draft_source':source,'draft_model':model,
        'ordering':[{'task_id':task['id'],'name':task['name'],'major':task.get('major') or task.get('department') or
            (task.get('source') or {}).get('major') or '',
            'semester':((task.get('source') or {}).get('course_metadata') or {}).get('semester')} for task in ordered]})
    return candidate


def apply_auto_schedule_candidate(db,plan,user,candidate,preview_record=None):
    from app.api.planning import write,event
    current=tasks_for_plan(db,plan);by_id={task['id']:task for task in current}
    pending_ids={task['id'] for task in current if not task.get('slots') or not task.get('room_id')}
    proposed=candidate.get('tasks') or []
    if {row.get('task_id') for row in proposed}!=pending_ids:
        raise HTTPException(409,'候选课程范围与当前周期不一致，请重新生成')
    merged=[]
    for row in proposed:
        source=by_id.get(row['task_id'])
        if not source:raise HTTPException(409,'候选包含已不存在的课程任务，请重新生成')
        merged.append({**source,'room_id':row['room_id'],'room_type':row['room_type'],'slots':row['slots']})
    complete=[task for task in current if task['id'] not in pending_ids]+merged
    validate_tasks(db,plan,complete)
    from app.api.stage_designer import validate_spans
    validate_spans(plan,complete,db)
    from app.api.planning import profile_for
    published_teachers=_published_teacher_tasks(db,plan)
    chosen=defaultdict(list)
    for task in complete:
        for teacher_id in task['teacher_ids']:
            external=published_teachers.get(teacher_id,[])
            reasons,_=capacity(db,plan,task,teacher_id,profile_for(db,teacher_id),external+chosen[teacher_id])
            if reasons:raise HTTPException(409,'；'.join(reasons))
            chosen[teacher_id].append((task,plan))
    with write(db):
        if preview_record:
            from datetime import datetime
            db.refresh(plan)
            db.refresh(preview_record)
            if plan.state!='matched':
                raise HTTPException(409,'排课周期状态已变化，不能应用该候选')
            if preview_record.used_at:
                raise HTTPException(409,'该排课候选已应用，请重新生成')
            if preview_record.expires_at<datetime.utcnow():
                raise HTTPException(409,'排课候选已过期，请重新生成')
            if preview_record.plan_revision!=plan.revision or preview_record.plan_id!=plan.id:
                raise HTTPException(409,'排课周期已变化，请重新生成候选')
            preview_record.used_at=datetime.utcnow()
        for row in merged:
            task=db.get(TeachingTask,row['id'])
            task.payload={**task.payload,'room_id':row['room_id'],'room_type':row['room_type']}
            db.query(PeriodSlot).filter_by(task_id=task.id).delete()
            for slot in row['slots']:db.add(PeriodSlot(task_id=task.id,**slot))
        settings={**(plan.settings or {}),'auto_schedule_revision':int((plan.settings or {}).get('auto_schedule_revision',0))+1}
        plan.settings=settings
        event(db,user,'auto_schedule',{'algorithm':candidate.get('algorithm'),'scheduled':len(merged),
            'task_ids':[task['id'] for task in merged],'revision':settings['auto_schedule_revision']},plan.id)
    return {'success':True,'scheduled':len(merged),'algorithm':candidate.get('algorithm'),
        'revision':settings['auto_schedule_revision'],'tasks':candidate.get('tasks',[])}


def generate_auto_placement(db,plan,user):
    candidate=build_auto_schedule_candidate(db,plan,'genetic')
    return apply_auto_schedule_candidate(db,plan,user,candidate)


def tasks_for_plan(db,plan):
    from app.api.planning import tasks_for
    return tasks_for(db,plan)
