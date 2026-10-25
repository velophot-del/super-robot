"""Build stage timetables from published snapshots using the college's Word styles."""
from collections import defaultdict
from copy import deepcopy
from datetime import date, timedelta
from io import BytesIO
import math
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile, ZIP_DEFLATED
from app.services.exam_weeks import exam_weeks_for
from app.services.academic_scope import grade_label

W='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
NS={'w':W}
ET.register_namespace('w',W)
TEMPLATE=Path(__file__).resolve().parents[1]/'templates'/'college_stage_timetable.docx'
DAYS=['周一','周二','周三','周四','周五','周六','周日']


def element(name, **attributes):
    return ET.Element('{'+W+'}'+name,{'{'+W+'}'+k:str(v) for k,v in attributes.items()})


def set_property(parent,name,**attributes):
    old=parent.find('w:'+name,NS)
    if old is not None:parent.remove(old)
    value=element(name,**attributes);parent.append(value);return value


def paragraph(text,prototype=None,size=18,bold=False):
    p=element('p')
    if prototype is not None:
        properties=prototype.find('w:pPr',NS)
        if properties is not None:p.append(deepcopy(properties))
    properties=p.find('w:pPr',NS)
    if properties is None:properties=element('pPr');p.append(properties)
    for name in ['ind','pageBreakBefore','sectPr']:
        old=properties.find('w:'+name,NS)
        if old is not None:properties.remove(old)
    set_property(properties,'jc',val='center')
    set_property(properties,'spacing',before=0,after=0,line=220,lineRule='auto')
    run=element('r');rp=element('rPr')
    set_property(rp,'rFonts',ascii='Times New Roman',eastAsia='宋体')
    set_property(rp,'sz',val=size);set_property(rp,'szCs',val=size)
    if bold:rp.append(element('b'))
    run.append(rp);textnode=element('t');textnode.text=text;run.append(textnode);p.append(run)
    return p


def cell(lines,width,prototype,span=1,vertical=None,size=18):
    c=element('tc');props=deepcopy(prototype.find('w:tcPr',NS))
    if props is None:props=element('tcPr')
    for name in ['gridSpan','vMerge','tcBorders']:
        old=props.find('w:'+name,NS)
        if old is not None:props.remove(old)
    set_property(props,'tcW',w=width,type='dxa')
    set_property(props,'vAlign',val='center')
    if span>1:props.append(element('gridSpan',val=span))
    if vertical:props.append(element('vMerge',val=vertical))
    c.append(props)
    for line in lines or ['']:c.append(paragraph(line,prototype.find('w:p',NS),size=size))
    return c


def stage_runs(tasks,weeks,exam_weeks=None):
    """Merge only adjacent weeks whose displayed teaching content is identical."""
    exam=set(exam_weeks) if exam_weeks is not None else {weeks}
    # Process drafts may contain tasks whose weeks have not been placed yet.
    placed=[task for task in tasks if task.get('start_week') and task.get('end_week')]
    content=[]
    for week in range(1,weeks+1):
        lines=[]
        for task in sorted(placed,key=lambda t:(t.get('name') or '',t.get('id',0))):
            if not task['start_week']<=week<=task['end_week']:continue
            phase='tail' if task.get('tail_weeks',0) and week>task['end_week']-task['tail_weeks'] else 'normal'
            slots=[s for s in (task.get('slots') or []) if s.get('phase','normal')==phase]
            lines.extend([task.get('name') or '未命名课程',
                '、'.join(task.get('teacher_names') or []) or '教师待分配',
                '【'+(task.get('room_name') or '地点待落实')+'】',
                '；'.join(f"{DAYS[s.get('day',1)-1]}{s.get('start',1)}—{s.get('start',1)+s.get('count',1)-1}节" for s in slots),
                f"{task.get('credits') or 0}学分 / {task.get('required_hours') or 0}学时"])
        if not lines:lines=['考试'] if week in exam else ['']
        content.append(tuple(lines))
    runs=[]
    for index,lines in enumerate(content):
        if runs and runs[-1][2]==lines:runs[-1]=(runs[-1][0],index+1,lines)
        else:runs.append((index,index+1,lines))
    return runs


def academic_title(plan):
    from app.services.academic_scope import academic_start_year,plan_term
    first=academic_start_year(plan['start_date'])
    term='第一' if plan_term(plan)==1 else '第二'
    return f'{first}—{first+1}学年{term}学期'


def build_word_timetable(batches,major,prepared_on=None):
    prepared_on=prepared_on or date.today()
    with ZipFile(TEMPLATE) as archive:
        package={name:archive.read(name) for name in archive.namelist()}
    original=ET.fromstring(package['word/document.xml']);source_body=original.find('w:body',NS)
    source_table=source_body.find('w:tbl',NS);source_rows=source_table.findall('w:tr',NS)
    source_cells=source_rows[2].findall('w:tc',NS)
    title_source=source_body.find('w:p',NS)
    header_source=source_rows[0].findall('w:tc',NS)[1]
    # Keep page dimensions, border styles and the template's vertical college/major labels.
    section=deepcopy(source_body.find('w:sectPr',NS))
    root=element('document');body=element('body');root.append(body)
    grid_widths=[int(c.get('{'+W+'}w')) for c in source_table.findall('w:tblGrid/w:gridCol',NS)]
    left=grid_widths[:3];total=sum(grid_widths[3:])
    grouped=defaultdict(list)
    for batch in batches:
        p=batch['plan'];calendar_rules=p.get('cohort_calendar_rules') or {}
        by_cohort=defaultdict(list)
        for task in batch['tasks']:
            cohort=task.get('cohort') or p.get('cohort') or '未设置年级'
            by_cohort[cohort].append(task)
        if not by_cohort:by_cohort[p.get('cohort') or '未设置年级']=[]
        for cohort,tasks in by_cohort.items():
            rule=calendar_rules.get(str(cohort).removesuffix('级').removesuffix('届')) or {}
            key=(cohort,rule.get('start_date') or p['start_date'],min(int(rule.get('weeks') or p['weeks']),int(p['weeks'])),p.get('semester',1))
            grouped[key].append({'plan':p,'tasks':tasks})
    page_index=0
    for key,group in sorted(grouped.items(),key=lambda item:str(item[0])):
        plan=group[0]['plan'];weeks=plan['weeks'];start=date.fromisoformat(plan['start_date'])
        widths=left+[total//weeks+(1 if w<total%weeks else 0) for w in range(weeks)]
        tasks=[t for b in group for t in b['tasks']]
        by_group=defaultdict(list)
        for task in tasks:by_group[task.get('group') or '未设置教学组'].append(task)
        # Pack rows conservatively. Word can repeat the two header rows on overflow.
        pages=[];page=[];used=0
        for label,items in sorted(by_group.items()):
            exam=exam_weeks_for(plan,items[0].get('cohort') if items else None,label,weeks)
            runs=stage_runs(items,weeks,exam)
            heights=[]
            for a,b,lines in runs:
                chars_per_line=max(2,sum(widths[3+a:3+b])/180)
                heights.append(sum(max(1,math.ceil(len(line)/chars_per_line)) for line in lines)*11+8)
            estimated=max(70,max(heights,default=70))
            if page and (len(page)>=5 or used+estimated>350):pages.append(page);page=[];used=0
            page.append((label,items,runs));used+=estimated
        if page:pages.append(page)
        # A blank process draft still needs one page with the template header.
        if not pages:pages=[[]]
        for rows in pages:
            if page_index:
                p=element('p');r=element('r');r.append(element('br',type='page'));p.append(r);body.append(p)
            page_index+=1
            college='视觉传达设计学院'
            title=f"{college}{academic_title(plan)}专业课总表（{grade_label(key[0])}）"
            body.append(paragraph(title,title_source,size=28,bold=True))
            body.append(paragraph(f"专业：{major}    制表时间：{prepared_on.year}年{prepared_on.month}月{prepared_on.day}日",size=18))
            table=element('tbl');props=deepcopy(source_table.find('w:tblPr',NS))
            floating=props.find('w:tblpPr',NS)
            if floating is not None:props.remove(floating)
            set_property(props,'tblW',w=sum(widths),type='dxa');table.append(props)
            grid=element('tblGrid')
            for width in widths:grid.append(element('gridCol',w=width))
            table.append(grid)
            for header in range(2):
                row=element('tr');rp=element('trPr');rp.append(element('tblHeader'));row.append(rp)
                row.append(cell(['周次 / 日期','学院  专业  班级'] if header==0 else [''],sum(left),header_source,span=3,vertical='restart' if header==0 else 'continue'))
                for week in range(weeks):
                    day=start+timedelta(weeks=week);end=day+timedelta(days=6)
                    lines=[str(week+1)] if header==0 else [f'{day.month}.{day.day}—',f'{end.month}.{end.day}']
                    row.append(cell(lines,widths[3+week],header_source,size=16))
                table.append(row)
            for row_index,(label,items,runs) in enumerate(rows):
                row=element('tr');rp=element('trPr');rp.append(element('trHeight',val=1200,hRule='atLeast'));row.append(rp)
                for index,text in enumerate([college,major]):
                    row.append(cell([text] if row_index==0 else [''],widths[index],source_cells[index],vertical=('restart' if row_index==0 else 'continue') if len(rows)>1 else None))
                count=max((int(t.get('student_count') or 0) for t in items),default=0)
                row.append(cell([label]+([f'【{count}人】'] if count else []),left[2],source_cells[2]))
                for a,b,lines in runs:row.append(cell(lines,sum(widths[3+a:3+b]),source_cells[3],span=b-a,size=16))
                table.append(row)
            body.append(table)
            unplaced=[task for task in tasks
                      if not task.get('start_week') or not task.get('end_week')]
            if unplaced:
                names='、'.join((task.get('name') or '未命名课程') for task in unplaced[:12])
                more=f' 等{len(unplaced)}门' if len(unplaced)>12 else ''
                body.append(paragraph(f'待安排周段：{names}{more}',size=16))
            if not tasks:
                body.append(paragraph('暂无课程任务（空白稿）',size=16))
            body.append(paragraph('注：格内课程按阶段周段合并；同周两门上下排列，各自注明教师、地点和时段。考试周按年级设置。',size=16))
    body.append(section)
    package['word/document.xml']=ET.tostring(root,encoding='utf-8',xml_declaration=True)
    # Original author metadata and old year titles do not belong to the generated timetable.
    core='http://schemas.openxmlformats.org/package/2006/metadata/core-properties'
    package['docProps/core.xml']=f'<?xml version="1.0" encoding="UTF-8"?><cp:coreProperties xmlns:cp="{core}"/>'.encode()
    if 'docProps/custom.xml' in package:
        package['docProps/custom.xml']=b'<?xml version="1.0" encoding="UTF-8"?><Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/custom-properties"/>'
    out=BytesIO()
    with ZipFile(out,'w',ZIP_DEFLATED) as archive:
        for name,content in package.items():archive.writestr(name,content)
    return out.getvalue()
