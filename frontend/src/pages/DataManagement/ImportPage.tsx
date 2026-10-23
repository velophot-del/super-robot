// CSV数据导入页面
import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Card, Upload, Button, Select, Space, Typography, Alert, message, Steps, Table, Tag } from 'antd';
import { InboxOutlined, DownloadOutlined, UploadOutlined, CheckCircleOutlined } from '@ant-design/icons';
import { ioApi } from '../../api/client';

const { Title, Text } = Typography;
const { Dragger } = Upload;

const entityOptions = [
  { label: '班级数据', value: 'classes' },
  { label: '教师数据', value: 'teachers' },
  { label: '课程数据', value: 'courses' },
  { label: '教室数据', value: 'classrooms' },
];

export default function ImportPage() {
  const [searchParams] = useSearchParams();
  const [entityType, setEntityType] = useState<string>(searchParams.get('entity')==='courses'?'courses':'classes');
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<any>(null);
  const [xlsxPreview,setXlsxPreview]=useState<any>(null);
  const [loading, setLoading] = useState(false);

  const handleDownloadTemplate = async () => {
    try {
      const isXlsx=entityType==='courses';
      const template=isXlsx?await ioApi.downloadCoursesXlsxTemplate():await ioApi.downloadTemplate(entityType);
      const blob = new Blob([template as any], { type: isXlsx?'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet':'text/csv' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${entityType}_template.${isXlsx?'xlsx':'csv'}`;
      a.click();
      URL.revokeObjectURL(url);
      message.success('模板下载成功');
    } catch (e: any) {
      message.error(`下载失败: ${e.message}`);
    }
  };

  const handleImport = async () => {
    if (!file) {
      message.warning('请先选择数据文件');
      return;
    }
    setLoading(true);
    try {
      if(file.name.toLowerCase().endsWith('.xlsx')){
        const preview=await ioApi.previewCoursesXlsx(file);
        setXlsxPreview(preview);setResult(null);
        message.success(`预览完成：新增${preview.counts.new}，重复${preview.counts.duplicate}，需修正${preview.counts.invalid}`);
      }else{
        const res = await ioApi.importCsv(entityType, file);
        setResult(res);if ((res as any).success)message.success((res as any).summary || '导入成功');
      }
    } catch (e: any) {
      message.error(`导入失败: ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: 900 }}>
      <Title level={4} style={{ color: '#0d253d', marginBottom: 20 }}>{entityType==='courses'?'课程批量导入':'批量数据导入'}</Title>

      <Steps
        current={result ? 2 : file ? 1 : 0}
        size="small"
        style={{ marginBottom: 24 }}
        items={[
          { title: '选择数据类型', icon: <CheckCircleOutlined /> },
          { title: '上传数据文件', icon: <UploadOutlined /> },
          { title: '查看导入结果', icon: <CheckCircleOutlined /> },
        ]}
      />

      <Card bordered style={{ borderColor: '#e3e8ee', marginBottom: 20 }}>
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <div>
            <Text strong style={{ display: 'block', marginBottom: 8, color: '#0d253d' }}>
              1. 选择要导入的数据类型
            </Text>
            <Select
              options={entityOptions}
              value={entityType}
              onChange={(v) => { setEntityType(v); setResult(null); setFile(null); }}
              style={{ width: 200 }}
            />
          </div>

          <div>
            <Text strong style={{ display: 'block', marginBottom: 8, color: '#0d253d' }}>
              2. 下载导入模板（按模板格式填写数据）
            </Text>
            <Button icon={<DownloadOutlined />} onClick={handleDownloadTemplate}>
              下载{entityOptions.find(e => e.value === entityType)?.label}模板
            </Button>
          </div>

          <div>
            <Text strong style={{ display: 'block', marginBottom: 8, color: '#0d253d' }}>
              3. 上传填写好的数据文件
            </Text>
            <Dragger
              accept={entityType==='courses'?'.csv,.xlsx':'.csv'}
              maxCount={1}
              beforeUpload={(f) => { setFile(f); setResult(null); setXlsxPreview(null); return false; }}
              onRemove={() => { setFile(null); setResult(null); }}
              style={{ background: '#f6f9fc' }}
            >
              <p className="ant-upload-drag-icon"><InboxOutlined style={{ color: '#533afd' }} /></p>
              <p className="ant-upload-text">点击或拖拽数据文件到此区域</p>
              <p className="ant-upload-hint">{entityType==='courses'?'课程支持.csv和.xlsx，Excel需先预览确认':'支持.csv格式文件，请按模板格式填写数据'}</p>
              {entityType==='courses'&&<p className="ant-upload-hint">课程负责人（工号）为选填项，需填写已有教师工号；重复课程跳过，不覆盖负责人。</p>}
            </Dragger>
          </div>

          <Button
            type="primary"
            icon={<UploadOutlined />}
            onClick={handleImport}
            loading={loading}
            disabled={!file}
            size="large"
          >
            开始导入
          </Button>
        </Space>
      </Card>

      {entityType==='teachers'&&<Alert type="info" showIcon style={{marginBottom:16}} message="教师导入会创建工号登录账号，初始密码为123456；首次登录必须修改密码并完善资料。重复导入不重置密码，账号冲突不会自动覆盖。"/>}
      {/* 导入结果 */}
      {xlsxPreview&&<Card title={`Excel 导入预览 · SHA-256 ${xlsxPreview.file_sha256.slice(0,16)}…`} style={{marginBottom:20}}>
        <Alert type="info" showIcon message={`新增 ${xlsxPreview.counts.new} · 重复 ${xlsxPreview.counts.duplicate} · 错误 ${xlsxPreview.counts.invalid}`} description="确认前不会写入课程；重复课程编码将跳过，错误行需要修正后重新上传。预览令牌30分钟有效且只能确认一次。"/>
        <Table style={{marginTop:12}} rowKey={(r:any)=>`${r.source_sheet}-${r.source_row}`} dataSource={xlsxPreview.rows} pagination={{pageSize:10}} columns={[
          {title:'工作表 / 行',render:(_:unknown,r:any)=>`${r.source_sheet} / ${r.source_row}`},{title:'课程编码',dataIndex:'course_code'},{title:'课程名称',dataIndex:'name'},
          {title:'状态',dataIndex:'status',render:(v:string)=><Tag color={v==='new'?'green':v==='duplicate'?'gold':'red'}>{v==='new'?'新增':v==='duplicate'?'重复':'错误'}</Tag>},
          {title:'问题',dataIndex:'issues',render:(v:string[])=>v?.join('；')||'—'}
        ]}/>
        <Button type="primary" disabled={xlsxPreview.counts.new===0} onClick={async()=>{try{const r=await ioApi.confirmCoursesXlsx(xlsxPreview.preview_id,xlsxPreview.token);setResult(r);setXlsxPreview(null);message.success(r.summary);}catch(e){message.error(String(e));}}}>确认导入有效新增课程</Button>
      </Card>}

      {result && (
        <Card title="导入结果" bordered style={{ borderColor: '#e3e8ee' }}>
          {result.success ? (
            <Alert type="success" message={result.summary} showIcon style={{ marginBottom: 12 }} />
          ) : (
            <Alert type="warning" message={result.summary} showIcon style={{ marginBottom: 12 }} />
          )}

          {result.errors?.length > 0 && (
            <div style={{ marginTop: 12 }}>
              <Text strong style={{ color: '#ea2261' }}>错误信息：</Text>
              <ul style={{ marginTop: 4 }}>
                {result.errors.map((err: string, i: number) => (
                  <li key={i}><Text type="danger">{err}</Text></li>
                ))}
              </ul>
            </div>
          )}
          {result.warnings?.length > 0 && (
            <div style={{ marginTop: 12 }}>
              <Text strong style={{ color: '#f59e0b' }}>警告信息：</Text>
              <ul style={{ marginTop: 4 }}>
                {result.warnings.map((warn: string, i: number) => (
                  <li key={i}><Text type="warning">{warn}</Text></li>
                ))}
              </ul>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
