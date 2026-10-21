import { Tooltip } from 'antd';
import { QuestionCircleOutlined } from '@ant-design/icons';

export default function HelpTip({title}:{title:React.ReactNode}){
  return <Tooltip title={<div style={{maxWidth:460,lineHeight:1.7}}>{title}</div>}>
    <span tabIndex={0} role="button" aria-label="查看说明" style={{cursor:'help',color:'#64748d',display:'inline-flex',alignItems:'center'}}>
      <QuestionCircleOutlined style={{fontSize:16}}/>
    </span>
  </Tooltip>;
}
