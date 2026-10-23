// 主布局组件 - 侧边导航 + 内容区
import { useState } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { Layout, Menu, Button, Typography, Dropdown, Avatar, Space, message } from 'antd';
import {
  TeamOutlined,
  UserOutlined,
  BookOutlined,
  BankOutlined,
  ScheduleOutlined,
  ImportOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  ThunderboltOutlined,
  LogoutOutlined,
} from '@ant-design/icons';
import { useAuth } from '../contexts/AuthContext';
import DebugToolbar from './DebugToolbar';
import { can, requiresAccountSetup } from '../lib/accessPolicy';

const { Header, Sider, Content, Footer } = Layout;
const { Text } = Typography;

const dataMenu = [
  {
    key: 'data',
    icon: <TeamOutlined />,
    label: '数据管理',
    children: [
      { key: '/data/classes', icon: <TeamOutlined />, label: '班级管理' },
      { key: '/data/teachers', icon: <UserOutlined />, label: '教师管理' },
      { key: '/data/courses', icon: <BookOutlined />, label: '课程管理' },
      { key: '/data/classrooms', icon: <BankOutlined />, label: '教室管理' },
      { key: '/data/import', icon: <ImportOutlined />, label: '数据导入' },
    ],
  },
];

export default function AppLayout() {
  const [collapsed, setCollapsed] = useState(true);
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuth();
  const visibleMenuItems = can(user,'admin') ? [
    {key:'/planning',icon:<BookOutlined/>,label:'排课周期计划'},
    {key:'/planning/review',icon:<ScheduleOutlined/>,label:'匹配与审核'},
    ...dataMenu,
    {key:'/timetable',icon:<ScheduleOutlined/>,label:'历史课表'},
  ] : [
    ...(can(user,'teaching') ? [{key:'/profile',icon:<UserOutlined/>,label:'个人资料'}] : []),
    { key:'/planning', icon:<BookOutlined />, label:can(user,'teaching')?'选课工作台':'计划、匹配与审核' },
    ...(can(user,'teaching')&&(can(user,'admin')||can(user,'review')||can(user,'publish')) ? [{key:'/planning/review',icon:<ScheduleOutlined/>,label:user?.grants?.some(g=>g.capability==='lead')?'教研室主任审核':'管理与审核工作台'}] : []),
    ...(can(user,'admin') ? dataMenu : []),
    ...(can(user,'teaching') ? [{key:'/planning/matches',icon:<BookOutlined/>,label:'我的匹配结果'}] : []),
    { key:'/timetable', icon:<ScheduleOutlined />, label:can(user,'teaching')?'我的课表':'历史课表查看' },
  ];

  const selectedKey = location.pathname === '/' ? '/' : location.pathname;

  const handleLogout = () => {
    logout();
    message.success('已退出登录');
    navigate('/login', { replace: true });
  };

  // 找到展开的子菜单
  const openKeys = visibleMenuItems
    .filter((item) => 'children' in item)
    .filter((item) => item.children?.some((child) => selectedKey.startsWith(child.key)))
    .map((item) => item.key);

  return (
    <Layout style={{ minHeight: '100vh' }}>
      {/* 侧边栏 */}
      <Sider
        trigger={null}
        collapsible
        collapsed={collapsed}
        width={216}
        style={{
          background: '#ffffff',
          borderRight: '1px solid #e6e8ec',
        }}
      >
        {/* Logo */}
        <div
          style={{
            height: 56,
            display: 'flex',
            alignItems: 'center',
            justifyContent: collapsed ? 'center' : 'flex-start',
            padding: collapsed ? 0 : '0 20px',
            borderBottom: '1px solid #e6e8ec',
          }}
        >
          <ThunderboltOutlined
            style={{ fontSize: 24, color: '#c26345', marginRight: collapsed ? 0 : 10 }}
          />
          {!collapsed && (
            <Text
              strong
              style={{
                color: '#292c32',
                fontSize: 16,
                letterSpacing: 0,
              }}
            >
              AI 智能排课
            </Text>
          )}
        </div>

        {/* 菜单 */}
        <Menu
          theme="light"
          mode="inline"
          selectedKeys={[selectedKey]}
          defaultOpenKeys={openKeys}
          onClick={({ key }) => navigate(key)}
          items={requiresAccountSetup(user) ? visibleMenuItems.filter(item => item.key === '/profile') : visibleMenuItems}
          style={{
            background: 'transparent',
            borderRight: 'none',
            marginTop: 8,
          }}
        />
      </Sider>

      {/* 主内容区 */}
      <Layout>
        <DebugToolbar />
        <Header
          style={{
            padding: '0 24px',
            background: '#ffffff',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            borderBottom: '1px solid #e3e8ee',
            height: 56,
          }}
        >
          <Space size={14}><Button
            type="text"
            aria-label={collapsed?'展开导航':'收起导航'}
            icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            onClick={() => setCollapsed(!collapsed)}
          /><div><Text strong style={{fontSize:16}}>视觉传达设计学院</Text><div style={{fontSize:12,color:'#7c838e',lineHeight:'18px'}}>课程教学管理</div></div></Space>
          <Space size={16}>
            <Text className="header-context" type="secondary" style={{ fontSize: 13 }}>
              学院教学管理 · 排课与选课
            </Text>
            <Dropdown
              menu={{
                items: [
                  {
                    key: 'username',
                    label: `当前用户：${user?.username || ''}`,
                    disabled: true,
                  },
                  { type: 'divider' },
                  {
                    key: 'logout',
                    icon: <LogoutOutlined />,
                    label: '退出登录',
                    danger: true,
                  },
                ],
                onClick: ({ key }) => {
                  if (key === 'logout') {
                    handleLogout();
                  }
                },
              }}
            >
              <Avatar
                style={{ backgroundColor: '#516c65', cursor: 'pointer' }}
                icon={<UserOutlined />}
              />
            </Dropdown>
          </Space>
        </Header>

        <Content
          style={{
            margin: 0,
            padding: '20px 24px',
            background: '#f4f5f7',
            borderRadius: 0,
            minHeight: 280,
            overflow: 'auto',
          }}
        >
          <Outlet />
        </Content>

        <Footer
          style={{
            textAlign: 'center',
            color: '#64748d',
            fontSize: 12,
            background: 'transparent',
            padding: '12px 24px',
          }}
        >
          学院课程教学管理
        </Footer>
      </Layout>
    </Layout>
  );
}
