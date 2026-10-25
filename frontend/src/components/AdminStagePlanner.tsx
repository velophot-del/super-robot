import { useEffect, useRef, useState } from 'react';
import { Alert, AutoComplete, Button, Card, Empty, Input, Modal, Popconfirm, Select, Space, Spin, Table, Tag, Tooltip, Typography, message } from 'antd';
import { InfoCircleOutlined, MinusOutlined, PlusOutlined, MenuFoldOutlined, MenuUnfoldOutlined, RobotOutlined } from '@ant-design/icons';
import { planningApi as api } from '../api/planning';
import { weekDates } from '../lib/selectionGrid';
import { examWeeksFor } from '../lib/examWeeks';
import { matchesStageScope, normalizeCohort, stageClassScope, stageLanes, stageRowMetrics, stageTaskEditAction, stageRoomLabel,dropWeek } from '../lib/adminStageGrid';
import { weekdayLabel } from '../lib/weekdays';

type DragItem={course_id?:number;task_id?:number;duration?:number};
const MIME='application/x-college-stage';

export default function AdminStagePlanner({plan,classes=[],onChange,onEdit}:{plan:any;classes?:any[];onChange:()=>Promise<void>;onEdit:(task:any)=>void}){
  const [pool,setPool]=useState<any[]>([]),[search,setSearch]=useState(''),[groups,setGroups]=useState<string[]>([]);
  const [schedulePreview,setSchedulePreview]=useState<any>();
  const [previewMode,setPreviewMode]=useState<'ai-draft'|'genetic'>('genetic');
  const [aiOpen,setAiOpen]=useState(false),[aiLoading,setAiLoading]=useState(false),[aiResult,setAiResult]=useState<any>();
  const [fillResult,setFillResult]=useState<any>();
  const [newGroup,setNewGroup]=useState(''),[removeGroup,setRemoveGroup]=useState<string>();
  const [selected,setSelected]=useState<DragItem>(),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const [poolOpen,setPoolOpen]=useState(true);
  const [helpOpen,setHelpOpen]=useState(false),[selectedCohort,setSelectedCohort]=useState('__all__'),[selectedMajor,setSelectedMajor]=useState('__all__');
  const pointer=useRef<{item:DragItem;name:string}|null>(null);
  const [ghost,setGhost]=useState<{x:number;y:number;name:string}>();
  const weeks=Number(plan.weeks)||20;
  const cellWidth=100/weeks;
  const groupCohort=(group:string)=>normalizeCohort((plan.tasks||[]).find((task:any)=>task.group===group)?.cohort||classes.find((row:any)=>row.name===group)?.grade||plan.cohort);
  const groupRule=(group:string)=>plan.cohort_calendar_rules?.[groupCohort(group)];
  const groupExam=(group:string)=>groupRule(group)?new Set<number>(groupRule(group).exam_weeks||[]):examWeeksFor(plan,groupCohort(group),group,weeks);
  const groupWeeks=(group:string)=>Number(groupRule(group)?.weeks)||weeks;
  const editable=plan.state==='draft';
  const canEditGroups=plan.state!=='published';
  const groupKey=(plan.groups?.length?plan.groups:[...new Set<string>((plan.tasks||[]).map((t:any)=>t.group))]).join('|');
  const autoSchedule=async()=>{setPreviewMode('genetic');setBusy(true);try{setSchedulePreview(await api.previewAutoSchedule(plan.id,{algorithm:'genetic'}));}catch(e){message.error(e instanceof Error?e.message:'遗传算法未能生成可行候选');}finally{setBusy(false);}};
  const aiDraft=async()=>{setBusy(true);try{const result:any=await api.generateAiDraft(plan.id);message.success(`一键AI排课完成：已安排${result.scheduled}门课程（${result.draft_source==='llm'?`AI排序 · ${result.draft_model||'模型'}`:'规则排序兜底'}），可继续人工微调`);await onChange();}catch(e){message.error(e instanceof Error?e.message:'AI 课表初稿生成失败；请检查教师锁定、教学周段、学时和教室条件');}finally{setBusy(false);}};
  const aiAutofill=async()=>{setBusy(true);try{const result:any=await api.aiAutofill(plan.id,plan.revision);setFillResult(result);await onChange();}catch(e){message.error(e instanceof Error?e.message:'AI 自动填充失败，请核对周期版本与课程信息');}finally{setBusy(false);}};
  const aiReview=async()=>{setAiOpen(true);setAiLoading(true);setAiResult(undefined);try{setAiResult(await api.aiReview(plan.id));}catch(e){message.error(e instanceof Error?e.message:'AI 分析失败');}finally{setAiLoading(false);}};
  const applyAutoSchedule=async()=>{if(!schedulePreview)return;setBusy(true);try{const result=await api.applyAutoSchedule(plan.id,schedulePreview.preview_id);setSchedulePreview(undefined);message.success(`已应用${previewMode==='ai-draft'?'AI课表初稿':'遗传算法候选'}：${result.scheduled}门课程`);await onChange();}catch(e){message.error(e instanceof Error?e.message:'候选已失效或校验未通过，请重新生成');}finally{setBusy(false);}};
  useEffect(()=>{setGroups(groupKey?groupKey.split('|'):[]);},[groupKey]);
  useEffect(()=>{let active=true;void api.coursePool(plan.id).then(data=>{if(active){setPool(data.courses);setError('');}}).catch(e=>{if(active)setError(e instanceof Error?e.message:'课程列表读取失败');});return()=>{active=false;};},[plan.id,plan.revision]);
  const action=async(fn:()=>Promise<unknown>)=>{setBusy(true);try{await fn();await onChange();message.success('课表已保存');}catch(e){message.error(e instanceof Error?e.message:'操作失败，请刷新核对');}finally{setBusy(false);}};
  const updateGroups=async(next:string[])=>{
    setBusy(true);
    try{await api.savePlanGroups(plan.id,{revision:plan.revision,groups:next});await onChange();message.success('班级条目已更新');return true;}
    catch(e){message.error(e instanceof Error?e.message:'班级保存失败');return false;}
    finally{setBusy(false);}
  };
  const addGroupRow=async()=>{
    const name=newGroup.trim();
    if(!name)return;
    if(groups.includes(name)){message.info('该班级已在课表中');return;}
    if(await updateGroups([...groups,name]))setNewGroup('');
  };
  const removeGroupRow=async()=>{
    if(!removeGroup)return;
    if(await updateGroups(groups.filter(group=>group!==removeGroup)))setRemoveGroup(undefined);
  };
  const place=(group:string,week:number,item=selected)=>{
    if(!editable||busy||!item)return;
    if(item.course_id&&!item.duration){message.warning('请先填写该课程占用周数，方案未提供时不能猜定');return;}
    if(week>weeks){message.warning('不在周期内');return;}
    const moving=(plan.tasks||[]).find((task:any)=>task.id===item.task_id);
    const span=item.task_id?(moving?(moving.end_week-moving.start_week+1):1):(item.duration||1);
    const blocked=[...groupExam(group)].filter(examWeek=>examWeek>=week&&examWeek<week+span).sort((a,b)=>a-b);
    if(blocked.length){message.warning(`第${blocked.join('、')}周为该年级考试周，不能安排课程`);return;}
    void action(()=>api.placeCourse(plan.id,{...item,revision:plan.revision,group,start_week:week}));
  };
  const drag=(e:React.DragEvent,item:DragItem)=>{e.dataTransfer.setData(MIME,JSON.stringify(item));e.dataTransfer.effectAllowed='move';setSelected(item);};
  const beginPointer=(e:React.PointerEvent<HTMLElement>,item:DragItem,name:string)=>{
    if(!editable||busy)return;e.preventDefault();e.currentTarget.setPointerCapture(e.pointerId);
    pointer.current={item,name};setGhost({x:e.clientX,y:e.clientY,name});
  };
  const endPointer=(e:React.PointerEvent<HTMLElement>)=>{
    const current=pointer.current;pointer.current=null;setGhost(undefined);
    if(!current)return;
    const target=document.elementFromPoint(e.clientX,e.clientY)?.closest<HTMLElement>('[data-stage-group]');
    if(target){const box=target.getBoundingClientRect();place(target.dataset.stageGroup!,dropWeek(e.clientX,box.left,box.width,weeks),current.item);}
  };
  const configuredGroups=plan.groups?.length?plan.groups:[...new Set<string>((plan.tasks||[]).map((t:any)=>t.group))];
  const groupScope=(group:string)=>{
    const scope=stageClassScope(group,classes,plan.tasks||[]);
    return {cohort:scope.cohort||normalizeCohort(plan.cohort),major:scope.major||String(plan.major||'').trim()};
  };
  const cohortOptions=[...new Set<string>([
    ...classes.filter((row:any)=>row.is_active!==false).map((row:any)=>normalizeCohort(row.grade)),
    ...(plan.tasks||[]).map((task:any)=>normalizeCohort(task.cohort)),
    ...pool.map((course:any)=>normalizeCohort(course.cohort)),
  ].filter(Boolean))].sort();
  const majorOptions=[...new Set<string>([
    ...classes.filter((row:any)=>row.is_active!==false).map((row:any)=>String(row.department||'').trim()),
    ...(plan.tasks||[]).map((task:any)=>String(task.major||task.department||'').trim()),
    ...pool.map((course:any)=>String(course.major||'').trim()),
  ].filter(Boolean))].sort();
  const visibleGroups=configuredGroups.filter((group:string)=>matchesStageScope(groupScope(group),selectedCohort,selectedMajor));
  const visiblePool=pool.filter((course:any)=>matchesStageScope({cohort:normalizeCohort(course.cohort),major:course.major},selectedCohort,selectedMajor))
    .filter((course,index,rows)=>rows.findIndex(other=>other.id===course.id&&normalizeCohort(other.cohort)===normalizeCohort(course.cohort)&&other.major===course.major)===index);
  const visibleTasks=(plan.tasks||[]).filter((task:any)=>{
    const fallback=groupScope(task.group);
    return matchesStageScope({cohort:normalizeCohort(task.cohort)||fallback.cohort,major:task.major||task.department||fallback.major},selectedCohort,selectedMajor);
  });
  const placed=visibleTasks.filter((t:any)=>t.start_week&&t.end_week);
  const pending=visibleTasks.filter((t:any)=>!t.start_week);
  return <Space orientation="vertical" style={{width:'100%'}} size="middle">
    {ghost&&<div style={{position:'fixed',left:ghost.x+14,top:ghost.y+14,pointerEvents:'none',zIndex:2000,background:'#436684',color:'white',padding:'8px 12px',borderRadius:6}}>{ghost.name}</div>}
    {error&&<Alert showIcon type="error" title={error}/>}
    <Space wrap><Button icon={poolOpen?<MenuFoldOutlined/>:<MenuUnfoldOutlined/>} onClick={()=>setPoolOpen(open=>!open)}>{poolOpen?'收起课程池':'待排课程'}</Button>
      {editable&&<Button type="primary" icon={<RobotOutlined/>} loading={busy} onClick={()=>void aiAutofill()}>系统自动填充课程与节次</Button>}
      {plan.state==='matched'&&<><Button type="primary" icon={<RobotOutlined/>} loading={busy} onClick={()=>void aiDraft()}>生成节次教室初稿</Button><Button loading={busy} onClick={()=>void autoSchedule()}>预览遗传算法候选</Button></>}
      <Button icon={<RobotOutlined/>} loading={aiLoading} onClick={()=>void aiReview()}>AI 周期分析</Button>
      <Tooltip title={helpOpen?'收起编排说明':'展开编排说明'}><Button type="text" size="small" aria-label={helpOpen?'收起编排说明':'展开编排说明'} aria-expanded={helpOpen} icon={<InfoCircleOutlined/>} onClick={()=>setHelpOpen(open=>!open)}/></Tooltip>
      <Typography.Text type="secondary">显示范围</Typography.Text>
      <Select aria-label="按年级筛选" value={selectedCohort} onChange={setSelectedCohort} style={{width:150}} options={[{value:'__all__',label:'全部年级'},...cohortOptions.map((cohort:string)=>({value:cohort,label:`${cohort}级`}))]}/>
      <Select aria-label="按专业筛选" value={selectedMajor} onChange={setSelectedMajor} style={{width:190}} options={[{value:'__all__',label:'全部专业'},...majorOptions.map((major:string)=>({value:major,label:major}))]}/>
    </Space>
    {helpOpen&&<Alert showIcon type="info" title={`按班级和${weeks}周编排阶段课程`} description="从课程列表拖到班级对应的起始周，按方案上课周数形成课程块。也可点“选择放置”，再点目标周。拖动课程块可调整周段或班级；点击课程名称维护教师名额。考试周、授课周数和课程开始日期在“数据管理→开课周期与规则”按年级统一设置。周内节次为可选项，发布前核验周段、地点、教师与教学组冲突。"/>}
    <Modal title="AI 排课分析" open={aiOpen} onCancel={()=>setAiOpen(false)} footer={<Button onClick={()=>setAiOpen(false)}>关闭</Button>} width={760}>
      {aiLoading&&<div style={{textAlign:'center',padding:32}}><Spin size="large"/><div style={{marginTop:12,color:'#8c8c8c'}}>正在分析当前周期…</div></div>}
      {aiResult&&<Space direction="vertical" style={{width:'100%'}} size="middle">
        <Alert showIcon type={aiResult.source==='llm'?'success':'info'}
          title={aiResult.source==='llm'?`模型分析 · ${aiResult.model}`:'规则分析'}
          description={aiResult.reason||'基于当前周期的任务、教师、地点与考试周数据生成。'}/>
        <Typography.Paragraph style={{whiteSpace:'pre-wrap',lineHeight:1.8,marginBottom:0}}>{aiResult.text}</Typography.Paragraph>
        {aiResult.issues?.length>0&&<Table size="small" rowKey={(r:any)=>`${r.task_id}-${r.category}-${r.message}`}
          pagination={{pageSize:6}} dataSource={aiResult.issues} columns={[
            {title:'课程',dataIndex:'name'},{title:'教学组',dataIndex:'group'},{title:'问题',dataIndex:'message'},
          ]}/>}
      </Space>}
    </Modal>
    <Modal title="课程自动填充结果" open={!!fillResult} onCancel={()=>setFillResult(undefined)} footer={<Button type="primary" onClick={()=>setFillResult(undefined)}>返回课表微调</Button>} width={760}>
      {fillResult&&<Space direction="vertical" style={{width:'100%'}}>
        <Alert showIcon type={fillResult.source==='llm'?'success':'info'} title={`${fillResult.source==='llm'?`AI 课程顺序 · ${fillResult.model||'模型'}`:'按课程库规则排序'} · 已填入${fillResult.filled}/${fillResult.total_candidates}门课程`} description="课程按适用班级、专业方向和培养学期匹配，自动避开考试周及每周两门上限。已分配教师、节次和教室的课程不会由此操作生成；请在甘特图继续人工微调。"/>
        {fillResult.placed?.length>0&&<Table size="small" rowKey="task_id" pagination={{pageSize:6}} dataSource={fillResult.placed} columns={[
          {title:'课程',dataIndex:'course'},{title:'班级',dataIndex:'group'},{title:'专业',dataIndex:'major'},
          {title:'培养学期',dataIndex:'semester',render:(v:number)=>`第${v}学期`},{title:'周段',render:(_:unknown,row:any)=>`W${row.start_week}—W${row.end_week}`},
        ]}/>}
        {fillResult.unplaced?.length>0&&<Table size="small" rowKey={(r:any)=>`${r.course}-${r.group}`} dataSource={fillResult.unplaced} pagination={{pageSize:5}} columns={[
          {title:'未排课程',dataIndex:'course'},{title:'班级',dataIndex:'group'},{title:'原因',dataIndex:'reason'},
        ]}/>}
      </Space>}
    </Modal>
    <Modal title={previewMode==='ai-draft'?'AI 课表初稿':'遗传算法排课候选'} open={!!schedulePreview} onCancel={()=>setSchedulePreview(undefined)} onOk={()=>void applyAutoSchedule()} confirmLoading={busy} okText="校验并应用，继续人工微调" cancelText="暂不应用" width={820}>
      {schedulePreview&&<Space direction="vertical" style={{width:'100%'}}>
        <Alert type="info" showIcon title={`${previewMode==='ai-draft'?(schedulePreview.draft_source==='llm'?`AI排序建议 · ${schedulePreview.draft_model||'模型'}`:'规则排序（AI未配置或不可用）'):'遗传算法候选'} · 覆盖${schedulePreview.scheduled}门课程 · 评分${schedulePreview.score}`} description="课程周段、班级和教师保持不变。AI分析专业和培养学期并提供编排顺序；节次与教室由排课引擎在硬约束下生成。应用时会再次校验学时、考试周、班级/教师/教室冲突、教室容量与类型。应用后可继续人工微调；候选30分钟后过期。"/>
        {previewMode==='ai-draft'&&<Table size="small" rowKey="task_id" pagination={{pageSize:6}} dataSource={schedulePreview.ordering} columns={[
          {title:'编排顺序',render:(_:unknown,_row:any,index:number)=>index+1},{title:'课程',dataIndex:'name'},{title:'班级专业',dataIndex:'major',render:(v:string,row:any)=>`${v||'专业未标注'} · ${row.group}`},{title:'培养学期',dataIndex:'semester',render:(v:number)=>v?`第${v}学期`:'未标注'},
        ]}/>}
        <Table size="small" rowKey="task_id" pagination={{pageSize:8}} dataSource={schedulePreview.tasks} columns={[
          {title:'课程',dataIndex:'name'},{title:'班级',dataIndex:'group'},
          {title:'教师',dataIndex:'teacher_names',render:(names:string[])=>names?.filter(Boolean).join('、')||'已锁定'},
          {title:'教学周',render:(_:unknown,row:any)=>`W${row.start_week}—W${row.end_week}`},
          {title:'节次',dataIndex:'slots',render:(slots:any[])=>slots.map(s=>`周${s.day} ${s.start}-${s.start+s.count-1}${s.phase==='tail'?'（尾周）':''}`).join('；')},
          {title:'地点',dataIndex:'room_name'},
        ]}/>
      </Space>}
    </Modal>
    <div style={{display:'flex',gap:16,alignItems:'flex-start',flexWrap:'wrap'}}>
      {poolOpen&&<Card title="本周期课程库" size="small" style={{width:252,flexShrink:0}}>
        <Typography.Paragraph type="secondary">{plan.global_cycle?`全学院 · 第${plan.academic_term}学期 · 按班级年级、专业和课程库自动匹配`:`${plan.major||'未设置专业'} · ${normalizeCohort(plan.cohort)||'未设置年级'}级 · 第${plan.semester}学期`}</Typography.Paragraph>
        <Input.Search aria-label="搜索待排课程" placeholder="课程名称或编码" value={search} onChange={e=>setSearch(e.target.value)} style={{marginBottom:12}}/>
        {!visiblePool.length&&<Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={!pool.length?'课程管理中暂无匹配本周期的活动课程，请核对课程年级、专业和上课学期':'当前年级、专业筛选范围内没有课程'}/>}
        <div style={{maxHeight:640,overflowY:'auto'}}>{visiblePool.filter(c=>`${c.name} ${c.code}`.includes(search)).map(course=>{
          const weeks=course.teaching_weeks;
          const item={course_id:course.id,duration:weeks||undefined};
          const schedulable=Boolean(weeks);
          return <div key={`${course.id}:${course.cohort}:${course.major}`} draggable={editable&&!busy&&schedulable} onDragStart={e=>drag(e,item)} style={{border:`1px solid ${selected?.course_id===course.id?'#436684':'#e4e1ed'}`,background:'#f8f9fb',borderRadius:6,padding:10,marginBottom:10,cursor:editable&&schedulable?'grab':'default'}}>
            <Typography.Text strong>{course.name}</Typography.Text><Button size="small" style={{display:'block',marginTop:5,touchAction:'none',cursor:'grab'}} disabled={!editable||busy||!schedulable} aria-label={`拖拽放置 ${course.name}`} onPointerDown={e=>beginPointer(e,item,course.name)} onPointerMove={e=>{if(pointer.current)setGhost({x:e.clientX,y:e.clientY,name:pointer.current.name});}} onPointerUp={endPointer} onPointerCancel={()=>{pointer.current=null;setGhost(undefined);}}>拖拽放置</Button>
            {course.major&&<div style={{fontSize:11,color:'#436684',marginTop:4}}>{course.major} · {normalizeCohort(course.cohort)}级 · 第{course.semester}学期</div>}
            <div style={{fontSize:12,margin:'4px 0'}}>{course.credits}学分 · {course.required_hours}学时 · {course.weekly_hours??'未注明'}节/周 · 教学计划 {weeks??'待补录'} 周{course.weekdays?.length?` · ${weekdayLabel(course.weekdays)}`:''}</div>
            <Space wrap><Button size="small" disabled={!editable||busy||!schedulable} onClick={()=>{setSelected(item);message.info('请点击班级行中的起始周');}}>选择放置</Button></Space>
            {!schedulable&&<div style={{fontSize:11,color:'#e5484d',marginTop:4}}>课程库未提供授课周数，请先在课程数据中补齐</div>}
            {course.notes&&<Typography.Paragraph type="secondary" style={{fontSize:11,margin:'5px 0 0'}}>{course.notes}</Typography.Paragraph>}
          </div>;
        })}</div>
      </Card>}
      <div style={{flex:'1 1 620px',minWidth:0}}>
        {selected&&<Alert type="success" style={{marginBottom:10}} title="已选择课程：点击班级中的起始周，或直接拖拽放置" action={<Button size="small" onClick={()=>setSelected(undefined)}>取消选择</Button>}/>}
        {selectedCohort==='__all__'&&Object.keys(plan.cohort_calendar_rules||{}).length>1&&<Alert showIcon type="info" title="不同年级使用各自开课日期；选择单一年级可查看对应周日期。" style={{marginBottom:8}}/>}
        {!configuredGroups.length?<Empty description="先添加并保存开课班级，即可出现空白课表"/>:!visibleGroups.length?<Empty description="当前年级、专业筛选范围内没有班级"/>:<div style={{overflowX:'auto',border:'1px solid #ddd',borderRadius:8}}><table aria-label={`管理员${weeks}周班级课表`} style={{borderCollapse:'collapse',width:'100%',minWidth:304+weeks*64,tableLayout:'fixed'}}>
          <colgroup><col style={{width:68}}/><col style={{width:110}}/><col style={{width:126}}/>{Array.from({length:weeks},(_,i)=><col key={i}/>)}</colgroup>
          <thead>
            <tr><th rowSpan={2} style={{background:'#f3f4f6',border:'1px solid #ddd',position:'sticky',left:0,zIndex:4,fontSize:14,padding:'6px 3px'}}>年级</th><th rowSpan={2} style={{background:'#f3f4f6',border:'1px solid #ddd',position:'sticky',left:68,zIndex:4,fontSize:14,padding:'6px 3px'}}>专业</th><th rowSpan={2} style={{background:'#f3f4f6',border:'1px solid #ddd',position:'sticky',left:178,zIndex:4,fontSize:14,padding:'6px 3px'}}>开课班级</th>{Array.from({length:weeks},(_,i)=><th key={i} style={{border:'1px solid #ddd',padding:'8px 2px',background:'#f3f4f6',fontSize:12}}>第{i+1}周</th>)}</tr>
            <tr>{Array.from({length:weeks},(_,i)=><th key={i} style={{border:'1px solid #ddd',padding:'5px 1px',fontSize:12,fontWeight:400}}>{weekDates((selectedCohort!=='__all__'&&plan.cohort_calendar_rules?.[selectedCohort]?.start_date)||plan.start_date,i+1)}</th>)}</tr>
          </thead>
          <tbody>{visibleGroups.map((group:string)=>{
            const bars=stageLanes<any>(placed.filter((t:any)=>t.group===group));
            const {laneStep,rowHeight}=stageRowMetrics(bars);
            const examSet=groupExam(group);
            const scope=groupScope(group);
            return <tr key={group}><td title={scope.cohort?`${scope.cohort}级`:'未设置'} style={{border:'1px solid #ddd',padding:'5px 4px',position:'sticky',left:0,background:'white',zIndex:2,whiteSpace:'nowrap',fontSize:13,lineHeight:1.2}}>{scope.cohort?`${scope.cohort}级`:'未设置'}</td><td title={scope.major||'未设置'} style={{border:'1px solid #ddd',padding:'5px 5px',position:'sticky',left:68,background:'white',zIndex:2,fontSize:13,lineHeight:1.2,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{scope.major||'未设置'}</td><th title={group} style={{border:'1px solid #ddd',padding:'5px 5px',position:'sticky',left:178,background:'white',zIndex:2,fontSize:13,lineHeight:1.2,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{group}</th><td colSpan={weeks} style={{padding:0,border:'1px solid #ddd'}}>
              <div data-stage-group={group} style={{height:rowHeight,position:'relative'}} onDragOver={e=>{if(editable&&!busy&&e.dataTransfer.types.includes(MIME)){e.preventDefault();e.dataTransfer.dropEffect='move';}}} onDrop={e=>{e.preventDefault();try{const item=JSON.parse(e.dataTransfer.getData(MIME));const box=e.currentTarget.getBoundingClientRect();place(group,dropWeek(e.clientX,box.left,box.width,weeks),item);}catch{message.error('请从课程列表或现有课程块拖入');}}}>
              {Array.from({length:weeks},(_,i)=>{const w=i+1;const isExam=examSet.has(w),outsideGradeWeeks=w>groupWeeks(group);return <Button key={i} type="text" aria-label={`放置到 ${group} 第${w}周`} disabled={!editable||busy||isExam||outsideGradeWeeks} onClick={()=>place(group,w)} style={{position:'absolute',left:`${i*cellWidth}%`,width:`${cellWidth}%`,height:'100%',borderRadius:0,borderRight:'1px solid #eee',background:isExam?'#fbe9e9':outsideGradeWeeks?'#f3f3f3':selected?'#faf8ff':'white',padding:0,color:'#bbb',fontSize:11}}>{isExam?'考试':outsideGradeWeeks?'—':selected?'+':''}</Button>;})}
                {bars.map(({task,lane})=>{
                  const teacherNames=task.teacher_names?.filter(Boolean).join('、')||'未分配教师';
                  return <div key={task.id} draggable={editable&&!busy} onDragStart={e=>drag(e,{task_id:task.id})} style={{position:'absolute',left:`${(task.start_week-1)*cellWidth}%`,width:`${(task.end_week-task.start_week+1)*cellWidth}%`,top:lane*laneStep+2,height:84,background:'#edf3fa',border:'1px solid #b5c5d8',borderRadius:5,boxSizing:'border-box',padding:'3px 5px',cursor:editable?'grab':'default',overflow:'hidden'}}>
                    <Button type="text" size="small" title={task.name} onClick={stageTaskEditAction(task,onEdit)} style={{display:'flex',justifyContent:'flex-start',whiteSpace:'nowrap',height:'auto',minHeight:22,padding:0,fontSize:14,fontWeight:600,textAlign:'left',width:'100%',lineHeight:1.2,overflow:'hidden',textOverflow:'ellipsis'}}>{task.name}</Button>
                    <div title={teacherNames} style={{fontSize:12,marginTop:1,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{teacherNames}</div>
                    {stageRoomLabel(task.room_address||task.room_name)&&<div title={stageRoomLabel(task.room_address||task.room_name)} style={{fontSize:12,lineHeight:'15px',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{stageRoomLabel(task.room_address||task.room_name)}</div>}
                    {editable&&<Popconfirm title="移回待排？保留来源课程记录。" onConfirm={()=>action(()=>api.unplaceCourse(plan.id,task.id,plan.revision))}><Button size="small" type="link" disabled={busy} style={{padding:0,height:20,fontSize:12,lineHeight:'20px'}}>移回待排</Button></Popconfirm>}
                  </div>;
                })}
              </div>
            </td></tr>;
          })}</tbody>
        </table></div>}
      </div>
    </div>
    <Card size="small" title="班级条目" extra={<Space><Tag>已排{placed.length}项</Tag><Tag>待排{pending.length}项</Tag></Space>}>
      <Space wrap>
        <AutoComplete aria-label="新增班级名称" value={newGroup} onChange={setNewGroup} options={classes.filter((row:any)=>row.is_active!==false&&(!plan.global_cycle||groups.includes(row.name))).map((row:any)=>({value:row.name,label:`${row.grade?`${normalizeCohort(row.grade)}级 · `:''}${row.department?`${row.department} · `:''}${row.name}`}))}
          placeholder="输入或选择班级" style={{width:240}} disabled={!canEditGroups||busy}/>
        <Button type="primary" icon={<PlusOutlined/>} disabled={!canEditGroups||busy||!newGroup.trim()} onClick={()=>void addGroupRow()}>增加班级</Button>
        <Select aria-label="选择要移除的班级" value={removeGroup} onChange={setRemoveGroup} placeholder="选择要移除的班级" allowClear
          options={groups.map(group=>({value:group,label:group}))} style={{width:240}} disabled={!canEditGroups||busy}/>
        <Popconfirm title={removeGroup?`移除班级「${removeGroup}」？已有排课任务的班级不能移除。`:'请选择要移除的班级'} onConfirm={()=>void removeGroupRow()} disabled={!removeGroup}>
          <Button danger icon={<MinusOutlined/>} disabled={!canEditGroups||busy||!removeGroup}>减少班级</Button>
        </Popconfirm>
        <Typography.Text type="secondary">增加或减少后立即更新课程表条目。</Typography.Text>
      </Space>
      {!canEditGroups&&<Alert type="info" showIcon title="已发布周期的班级条目已冻结" style={{marginTop:12}}/>}
      {canEditGroups&&plan.state!=='draft'&&<Alert type="warning" showIcon title="非草稿阶段新增班级不会自动生成课程任务" style={{marginTop:12}}/>}
    </Card>
  </Space>;
}
