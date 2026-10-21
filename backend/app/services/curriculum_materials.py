import csv
import io
import math
import hashlib
import re
from collections import Counter
import zipfile
from xml.etree import ElementTree as ET
from fastapi import HTTPException

ALIASES={
    'code':['课程编码','课程代码','课程编号','code'], 'name':['课程名称','课程中文名称','name'],
    'credits':['学分','credits'], 'required_hours':['总学时','总课时','计划学时','学时','学时分配总计','学时分配合计','学时数总计','学时数合计','学时总计','学时合计','required_hours'],
    'semester':['开课学期','上课学期','建议学期','建议修读学期','建议开课学期','开设学期','学期','semester'],
    'category':['课程性质','课程类别','category'],
    'weekly_hours':['周课时','周学时','weekly_hours'],
    'teaching_weeks':['上课周数','授课周数','teaching_weeks'],
    'notes':['备注','说明','notes'],
    'direction':['专业方向','方向','direction'], 'tags':['领域标签','擅长领域','tags'],
}


def normalize_label(value):
    value = re.sub(r'\s+', '', value).casefold()
    return re.sub(r'[（(](?:学分|学时|小时|周|必填)[）)]', '', value)


CN_ORDINALS = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}
YEAR_LABEL = re.compile(r'第([一二三四五六七八九十])学年')


def _header_parts(lines):
    """把多行表头按列合并为若干原始标签，保留每一行的可读内容。"""
    width = max((len(line) for line in lines), default=0)
    return [list(dict.fromkeys(line[i] for line in lines if i < len(line) and line[i]))
            for i in range(width)]


def combine_header(lines):
    """组合相邻表头行；返回映射、原始标签和学期矩阵列。

    多行表头（如“学时 / 总学时”“第一学年 / 一”）必须整体识别，
    否则续行会被误当作课程数据。学期矩阵只在能明确对应到学年和学期时启用。
    """
    parts = _header_parts(lines)
    labels = [' / '.join(values) for values in parts]
    mapping = {}
    for key, aliases in ALIASES.items():
        expected = {normalize_label(alias) for alias in aliases}
        mapping[key] = next((index for index, values in enumerate(parts)
                             if any(normalize_label(value) in expected for value in values)
                             or normalize_label(''.join(values)) in expected), None)
    if any(mapping[key] is None for key in ('name', 'credits', 'required_hours')):
        return None
    # 合并单元格在续行中为空，需按行向左沿用最近一次出现的学年标签。
    years = {}
    for line in lines:
        current = None
        for index, value in enumerate(line):
            match = YEAR_LABEL.search(value) if value else None
            if match and match.group(1) in CN_ORDINALS:
                current = CN_ORDINALS[match.group(1)]
            if current:
                years[index] = current
    matrix = {}
    for index, values in enumerate(parts):
        ordinal = next((CN_ORDINALS[value] for value in values if value in CN_ORDINALS), None)
        if years.get(index) and ordinal:
            matrix[index] = (years[index] - 1) * 2 + ordinal
    return mapping, labels, matrix


def _is_header_continuation(values, mapping):
    """表头之后若关键列仍为空且内容仍像表头，则该行属于合并表头。"""
    if not any(values):
        return False
    name_index = mapping.get('name')
    if name_index is not None and name_index < len(values) and values[name_index]:
        return False
    for key in ('credits', 'required_hours'):
        index = mapping.get(key)
        if index is None or index >= len(values) or not values[index]:
            continue
        try:
            float(values[index])
        except ValueError:
            continue
        return False
    tokens = {normalize_label(alias) for aliases in ALIASES.values() for alias in aliases}
    tokens |= {'总计', '合计', '理论', '实践'}
    return any(YEAR_LABEL.search(value) or value in CN_ORDINALS or normalize_label(value) in tokens
               for value in values)


def find_header(table):
    """在工作表前部查找完整表头，支持最多 3 行合并表头。"""
    for start in range(min(len(table), 200)):
        for depth in range(1, 4):
            if start + depth > len(table):
                break
            candidate = combine_header(table[start:start + depth])
            if not candidate:
                continue
            following = table[start + depth] if start + depth < len(table) else None
            if following is not None and _is_header_continuation(following, candidate[0]):
                continue
            return start, start + depth - 1, candidate
    return None


def semester_number(value):
    if not value:
        return None
    match = re.fullmatch(r'(?:第)?\s*(\d+)\s*(?:学期)?', value)
    if not match:
        raise ValueError('开课学期不明确，请填写单一数字学期（如2或第2学期）')
    return int(match.group(1))


def extract_rows(filename,content,scope=''):
    """解析课程表格。

    `scope` 用于生成系统内部课程编码。它必须标识培养方案（专业/届次/修订号），
    否则不同专业中相同的表号、行号和课程名会生成相同编码并互相冲突。
    """
    if len(content)>10*1024*1024:raise HTTPException(413,'文件超过10MiB')
    suffix=filename.lower().rsplit('.',1)[-1]
    tables=[];sheet_names=[]
    try:
        if suffix=='csv':
            try: decoded=content.decode('utf-8-sig')
            except UnicodeDecodeError:decoded=content.decode('gb18030')
            tables=[list(csv.reader(io.StringIO(decoded)))]
        elif suffix in {'xlsx','docx'}:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                if sum(i.file_size for i in archive.infolist())>50*1024*1024:raise HTTPException(413,'压缩内容展开超过50MiB')
                if suffix=='docx':
                    xml=archive.read('word/document.xml')
                    if b'<!DOCTYPE' in xml:raise HTTPException(422,'不接受含DTD的文档')
                    root=ET.fromstring(xml); ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
                    for table in root.findall('.//w:tbl',ns):
                        tables.append([[''.join(cell.itertext()) if not cell.findall('.//w:t',ns) else ''.join(n.text or '' for n in cell.findall('.//w:t',ns))
                                        for cell in row.findall('w:tc',ns)] for row in table.findall('w:tr',ns)])
            if suffix=='xlsx':
                from openpyxl import load_workbook
                wb=load_workbook(io.BytesIO(content),read_only=True,data_only=False)
                try:
                    for ws in wb.worksheets:
                        if (ws.max_row or 0) > 20000 or (ws.max_column or 0) > 256:
                            raise HTTPException(413,f'工作表“{ws.title}”范围过大，请移除多余格式或拆分文件（最多20000行、256列）')
                        tables.append(list(ws.iter_rows(values_only=True)));sheet_names.append(ws.title)
                finally:wb.close()
        else:raise HTTPException(422,'支持CSV、XLSX和DOCX表格；PDF及扫描识别未实现')
    except HTTPException:raise
    except Exception as e:raise HTTPException(422,'文件无法解析，请使用规范课程表格') from e
    rows=[];errors=[]
    for table_no,table in enumerate(tables,1):
        header=None;labels=[];matrix={};history=[]
        location=f'工作表“{sheet_names[table_no-1]}”' if sheet_names else f'表{table_no}'
        first_data_line=1
        if suffix=='xlsx':
            # XLSX 表头可能横跨多行；先整体定位表头，避免续行被当成课程数据。
            normalized_table=[[str(v).strip() if v is not None else '' for v in line] for line in table]
            detected=find_header(normalized_table)
            if detected:
                _,header_end,(header,labels,matrix)=detected
                first_data_line=header_end+2
            else:
                first_data_line=len(normalized_table)+1
        for line_no,line in enumerate(table,1):
            if len(rows)>=10000:raise HTTPException(413,'课程行超过10000')
            if line_no<first_data_line:continue
            values=[str(v).strip() if v is not None else '' for v in line]
            if suffix!='xlsx':
                normalized=[normalize_label(v) for v in values]
                mapping={key:next((i for i,v in enumerate(normalized) if v in aliases),None) for key,aliases in ALIASES.items()}
                if all(mapping[k] is not None for k in ['name','credits','required_hours','semester']):
                    header=mapping;labels=values;continue
            if not header or not any(values):continue
            record={k:values[i] if i is not None and i<len(values) else '' for k,i in header.items()}
            # Summary and explanatory rows have no value in the course-name column.
            if not record['name'] and suffix!='xlsx':
                if record['code']:errors.append(f'{location}行{line_no}：课程名称必填')
                continue
            try:
                review=[];matrix_cells=[]
                if suffix=='xlsx':
                    if not record['name']:review.append('未填写课程名称，保留原始行待核对，不作为课程导入')
                    if any(v.startswith('=') for v in values):review.append('含公式，仅保留原始表达式，不执行计算；请核对后提供数值')
                    for key,label,maximum in [('credits','学分',30),('required_hours','总学时',400)]:
                        try:
                            number=float(record[key])
                            if not math.isfinite(number) or not 0<=number<=maximum or (key=='required_hours' and not number.is_integer()):raise ValueError()
                            record[key]=number if key=='credits' else int(number)
                        except (ValueError,TypeError):
                            record[key]=None;review.append(f'{label}非明确有效数值（说明、参考值、公式或空值），待核对，不自动排课')
                    try:record['semester']=semester_number(record['semester'])
                    except ValueError:record['semester']=None
                    for column,semester in matrix.items():
                        raw=values[column] if column<len(values) else ''
                        try:number=float(raw)
                        except (ValueError,TypeError):continue
                        if math.isfinite(number) and number>0:matrix_cells.append((semester,raw))
                    if len(matrix_cells)==1:
                        # 学期矩阵只有单列有正数时，才能确定开课学期与周学时。
                        semester,raw=matrix_cells[0]
                        if record['semester'] is None:record['semester']=semester
                        record['weekly_hours']=raw
                    elif len(matrix_cells)>1:
                        review.append('学期周学时存在多个正数，无法确定开课学期，待核对')
                    if record['semester'] is not None and not 1<=record['semester']<=12:
                        record['semester']=None;review.append('开课学期超出范围，待核对')
                    record['record_type']='review' if review or record['semester'] is None or record['name'] in {'课程单独列出','合计','小计','总计'} else 'course'
                else:
                    if any(v.startswith('=') for v in values):raise ValueError('课程字段不能使用公式')
                    record['credits']=float(record['credits']);record['required_hours']=int(record['required_hours'])
                    record['semester']=semester_number(record['semester'])
                    if not math.isfinite(record['credits']) or not 0<=record['credits']<=30 or not 0<=record['required_hours']<=400 or (record['semester'] is not None and not 1<=record['semester']<=12):
                        raise ValueError('学分、学时或学期超出范围')
                record['raw_fields']={label:values[i] if i<len(values) else '' for i,label in enumerate(labels) if label}
                if len(matrix_cells)==1:
                    semester,raw=matrix_cells[0]
                    record['raw_fields'][f'学期{semester}周学时']=raw
                record['source_table']=table_no;record['source_row']=line_no
                if sheet_names:record['source_sheet']=sheet_names[table_no-1]
                record['code_generated']=not bool(record['code']) or not bool(record['name'])
                if record['code_generated']:
                    identity=f"{scope}:{table_no}:{line_no}:{record['name']}:{record['semester']}"
                    record['code']='SYS-'+hashlib.sha256(identity.encode()).hexdigest()[:16].upper()
                record['tags']=[s.strip() for s in record['tags'].replace('，',',').split(',') if s.strip()]
                for key in ['weekly_hours','teaching_weeks']:
                    value=record[key]
                    record[key]=int(value) if re.fullmatch(r'\d+',value) else None
                tail=re.search(r'最后一周\s*(\d+)\s*(?:课时|学时|节)',record['notes'])
                record['tail_hours']=int(tail.group(1)) if tail else None
                record['review_notes']=review
                if record['code_generated']:record['review_notes'].append('无原始课程编码，使用系统内部编号')
                if record['semester'] is None:record['review_notes'].append('开课学期待核对，暂不生成任务')
                if record['required_hours'] is None:record['review_notes'].append('授课学时缺失待核对，暂不生成任务')
                elif not record['required_hours']:record['review_notes'].append('不计授课学时，暂不生成任务')
                if record['name'] in {'课程单独列出','合计','小计','总计'}:record['review_notes'].append('汇总或占位条目，暂不生成任务')
                record['schedulable']=bool(record.get('record_type')!='review' and record['semester'] and record['required_hours'] and record['name'] not in {'课程单独列出','合计','小计','总计'})
                rows.append(record)
            except (ValueError,TypeError) as e:errors.append(f'{location}行{line_no}：{e}')
    counts=Counter((r['name'],r['semester']) for r in rows if r['name'])
    for record in rows:
        if record['name'] and counts[(record['name'],record['semester'])]>1:
            record['review_notes'].append('同名同学期有多条原始记录，未合并；须核对后单独配置任务')
            record['schedulable']=False
    if not rows:
        detail='；已检查工作表：'+ '、'.join(sheet_names) if sheet_names else ''
        errors.append('没有识别到课程表：需要课程名称、学分、总学时（或总课时）；开课学期可缺省并标记待核对，课程编码可缺省'+detail)
    if len({r['code'] for r in rows})!=len(rows):errors.append('课程编码重复，须核对后再上传')
    return rows,errors
