"""Visual workbooks built solely from published snapshot batches, sized to each plan's weeks."""
from collections import defaultdict
from datetime import date, timedelta
from io import BytesIO
import math
import unicodedata
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from app.services.word_timetable import stage_runs
from app.services.exam_weeks import exam_weeks_for


def build_visual_excel(batches, title):
    weeks = max(int(b['plan'].get('weeks') or 20) for b in batches)
    last_col = get_column_letter(weeks + 3)
    wb = Workbook()
    ws = wb.active
    ws.title = f'{weeks}周课表'
    ws.sheet_view.showGridLines = False
    ws.merge_cells(f'A1:{last_col}1'); ws['A1'] = title
    start = date.fromisoformat(batches[0]['plan']['start_date'])
    ws.merge_cells(f'A2:{last_col}2')
    openings = {b['plan'].get('opening_date') or '未登记' for b in batches}
    opening_label = next(iter(openings)) if len(openings) == 1 else '各计划不同，详见课程明细'
    ws['A2'] = f"开学日期：{opening_label} · 第1教学周周一：{start.isoformat()} · 共{weeks}周 · 考试周按年级设置 · 仅含已发布课程"
    for col, label in enumerate(['专业', '年级', '教学组 / 班级'], 1):
        ws.cell(3, col, label); ws.merge_cells(start_row=3, end_row=4, start_column=col, end_column=col)
    for week in range(1, weeks + 1):
        col = week + 3
        ws.cell(3, col, f'第{week}周')
        begin = start + timedelta(weeks=week-1); end = begin + timedelta(days=6)
        ws.cell(4, col, f'{begin.month}.{begin.day}—{end.month}.{end.day}')
        ws.column_dimensions[get_column_letter(col)].width = 15
    for col, width in [('A', 20), ('B', 12), ('C', 24)]:
        ws.column_dimensions[col].width = width
    groups = defaultdict(list); group_plan = {}
    details = wb.create_sheet('课程明细')
    details.append(['课程名称','课程编码','教学组','学分','计划学时','起始周','结束周','周内分布','地点','任课教师','来源版本','专业','年级','周期','发布快照','开学日期'])
    for batch in batches:
        plan = batch['plan']
        for task in batch['tasks']:
            task_major=task.get('major') or plan.get('major') or '未注明专业'
            task_cohort=str(task.get('cohort') or plan.get('cohort') or '未注明')
            group_key=(task_major,task_cohort,task['group'])
            groups[group_key].append(task); group_plan[group_key]=plan
            details.append([task['name'],task['code'],task['group'],task['credits'],task['required_hours'],task['start_week'],task['end_week'],
                '；'.join(f"{'尾段 ' if s.get('phase')=='tail' else ''}周{s['day']} 第{s['start']}—{s['start']+s['count']-1}节" for s in task.get('slots',[])),
                task.get('room_name',''),'、'.join(task.get('teacher_names',[])),str(task.get('source',{})),task_major,task_cohort,plan.get('name',''),batch.get('snapshot_id'),plan.get('opening_date') or '未登记'])
    row = 5
    for (major, cohort, group), tasks in sorted(groups.items()):
        # Parallel courses use separate lanes so narrow single-week cells remain legible.
        lanes = []
        for task in sorted(tasks, key=lambda t:(t['start_week'],t['end_week'],t['name'])):
            lane = next((lane for lane in lanes if all(t['end_week'] < task['start_week'] or task['end_week'] < t['start_week'] for t in lane)), None)
            if lane is None: lane=[]; lanes.append(lane)
            lane.append(task)
        first = row
        plan_for_group=group_plan.get((major,cohort,group),batches[0]['plan'])
        exam=exam_weeks_for(plan_for_group,None if cohort=='未注明' else cohort,group,weeks)
        for lane in lanes:
            height = 110
            for begin, end, lines in stage_runs(lane, weeks, exam):
                col = begin + 4; last = end + 3
                ws.cell(row, col, '\n'.join(lines))
                if last > col: ws.merge_cells(start_row=row,end_row=row,start_column=col,end_column=last)
                width = 15 * (end-begin)
                line_count = sum(max(1, math.ceil(sum(2 if unicodedata.east_asian_width(c) in 'WF' else 1 for c in line)/width)) for line in lines)
                height = max(height, line_count * 16 + 20)
                ws.cell(row,col).fill = PatternFill('solid',fgColor='EEEEEE' if lines == ('考试',) else 'F0EDFA' if any(lines) else 'FFFFFF')
            ws.row_dimensions[row].height = min(409, height)
            row += 1
        for col, label in enumerate([major,cohort,group],1):
            ws.cell(first,col,label)
            if row-1>first:ws.merge_cells(start_row=first,end_row=row-1,start_column=col,end_column=col)
    line = Side(style='thin',color='D4D8E2')
    for sheet in wb:
        for cells in sheet:
            for cell in cells:
                if isinstance(cell.value,str):cell.data_type='s'
                cell.font=Font(name='微软雅黑',size=11,color='243247')
                cell.alignment=Alignment(horizontal='center',vertical='center',wrap_text=True)
                cell.border=Border(left=line,right=line,top=line,bottom=line)
        sheet.page_setup.orientation='landscape';sheet.page_setup.paperSize=sheet.PAPERSIZE_A3
        sheet.sheet_properties.pageSetUpPr.fitToPage=True
        sheet.page_setup.fitToWidth=1;sheet.page_setup.fitToHeight=0
    for cells in ws.iter_rows(min_row=3,max_row=4):
        for cell in cells:cell.fill=PatternFill('solid',fgColor='E4E9F4');cell.font=Font(name='微软雅黑',bold=True,size=11)
    ws['A1'].font=Font(name='微软雅黑',size=20,bold=True,color='243247')
    ws.row_dimensions[1].height=36;ws.row_dimensions[2].height=26
    ws.row_dimensions[3].height=28;ws.row_dimensions[4].height=24
    ws.freeze_panes='D5';ws.print_title_rows='1:4';ws.print_title_cols='A:C';ws.print_area=f'A1:{last_col}{max(row-1,4)}'
    for col in range(1,17):details.column_dimensions[get_column_letter(col)].width=24 if col not in [8,11] else 48
    for cell in details[1]:cell.fill=PatternFill('solid',fgColor='E4E9F4');cell.font=Font(name='微软雅黑',bold=True,size=11)
    for r in range(2,details.max_row+1):details.row_dimensions[r].height=60
    details.freeze_panes='D2';details.auto_filter.ref=details.dimensions;details.print_title_rows='1:1'
    output=BytesIO();wb.save(output);return output.getvalue()
