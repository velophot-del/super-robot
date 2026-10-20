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
    'code':['课程编码','课程代码','code'], 'name':['课程名称','name'],
    'credits':['学分','credits'], 'required_hours':['总学时','计划学时','学时','required_hours'],
    'semester':['开课学期','上课学期','建议学期','学期','semester'],
    'category':['课程性质','课程类别','category'],
    'weekly_hours':['周课时','周学时','weekly_hours'],
    'teaching_weeks':['上课周数','授课周数','teaching_weeks'],
    'notes':['备注','说明','notes'],
    'direction':['专业方向','方向','direction'], 'tags':['领域标签','擅长领域','tags'],
}


def extract_rows(filename,content,scope=''):
    """解析课程表格。

    `scope` 用于生成系统内部课程编码。它必须标识培养方案（专业/届次/修订号），
    否则不同专业中相同的表号、行号和课程名会生成相同编码并互相冲突。
    """
    if len(content)>10*1024*1024:raise HTTPException(413,'文件超过10MiB')
    suffix=filename.lower().rsplit('.',1)[-1]
    tables=[]
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
                tables=[list(ws.iter_rows(values_only=True)) for ws in wb.worksheets];wb.close()
        else:raise HTTPException(422,'支持CSV、XLSX和DOCX表格；PDF及扫描识别未实现')
    except HTTPException:raise
    except Exception as e:raise HTTPException(422,'文件无法解析，请使用规范课程表格') from e
    rows=[];errors=[]
    for table_no,table in enumerate(tables,1):
        header=None;labels=[]
        for line_no,line in enumerate(table,1):
            if len(rows)>=10000:raise HTTPException(413,'课程行超过10000')
            values=[str(v).strip() if v is not None else '' for v in line]
            normalized=[re.sub(r'\s+','',v) for v in values]
            mapping={key:next((i for i,v in enumerate(normalized) if v in aliases),None) for key,aliases in ALIASES.items()}
            if all(mapping[k] is not None for k in ['name','credits','required_hours','semester']):
                header=mapping;labels=values;continue
            if not header or not any(values):continue
            record={k:values[i] if i is not None and i<len(values) else '' for k,i in header.items()}
            # Summary and explanatory rows have no value in the course-name column.
            if not record['name']:
                if record['code']:errors.append(f'表{table_no}行{line_no}：课程名称必填')
                continue
            try:
                if any(v.startswith('=') for v in values):raise ValueError('课程字段不能使用公式')
                record['credits']=float(record['credits']);record['required_hours']=int(record['required_hours'])
                record['semester']=int(record['semester']) if record['semester'] else None
                if not math.isfinite(record['credits']) or not 0<=record['credits']<=30 or not 0<=record['required_hours']<=400 or (record['semester'] is not None and not 1<=record['semester']<=12):
                    raise ValueError('学分、学时或学期超出范围')
                record['raw_fields']={label:values[i] if i<len(values) else '' for i,label in enumerate(labels) if label}
                record['source_table']=table_no;record['source_row']=line_no
                record['code_generated']=not bool(record['code'])
                if record['code_generated']:
                    identity=f"{scope}:{table_no}:{line_no}:{record['name']}:{record['semester']}"
                    record['code']='SYS-'+hashlib.sha256(identity.encode()).hexdigest()[:16].upper()
                record['tags']=[s.strip() for s in record['tags'].replace('，',',').split(',') if s.strip()]
                for key in ['weekly_hours','teaching_weeks']:
                    value=record[key]
                    record[key]=int(value) if re.fullmatch(r'\d+',value) else None
                tail=re.search(r'最后一周\s*(\d+)\s*(?:课时|学时|节)',record['notes'])
                record['tail_hours']=int(tail.group(1)) if tail else None
                record['review_notes']=[]
                if record['code_generated']:record['review_notes'].append('无原始课程编码，使用系统内部编号')
                if record['semester'] is None:record['review_notes'].append('开课学期待核对，暂不生成任务')
                if not record['required_hours']:record['review_notes'].append('不计授课学时，暂不生成任务')
                if record['name'] in {'课程单独列出','合计','小计','总计'}:record['review_notes'].append('汇总或占位条目，暂不生成任务')
                record['schedulable']=bool(record['semester'] and record['required_hours'] and record['name'] not in {'课程单独列出','合计','小计','总计'})
                rows.append(record)
            except (ValueError,TypeError) as e:errors.append(f'表{table_no}行{line_no}：{e}')
    counts=Counter((r['name'],r['semester']) for r in rows)
    for record in rows:
        if counts[(record['name'],record['semester'])]>1:
            record['review_notes'].append('同名同学期有多条原始记录，未合并；须核对后单独配置任务')
            record['schedulable']=False
    if not rows:errors.append('没有识别到课程表：需要课程名称、学分、总学时和开课学期（兼容上课学期）；课程编码可缺省')
    if len({r['code'] for r in rows})!=len(rows):errors.append('课程编码重复，须核对后再上传')
    return rows,errors
