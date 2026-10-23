// Stripe 设计系统主题配置
// 参考: DESIGN.md - Stripe-Inspired Design Analysis

import type { ThemeConfig } from 'antd';

const theme: ThemeConfig = {
  token: {
    // === 品牌色 (Stripe 电光紫) ===
    colorPrimary: '#202124',
    colorPrimaryHover: '#42454a',
    colorPrimaryActive: '#101114',
    colorPrimaryBg: '#f0f1f3',
    colorPrimaryBgHover: '#e7e9ed',

    // === 文字色 (Stripe ink 深蓝墨色) ===
    colorText: '#252830',
    colorTextSecondary: '#273951',
    colorTextTertiary: '#64748d',
    colorTextQuaternary: '#61718a',

    // === 表面色 ===
    colorBgContainer: '#ffffff',
    colorBgLayout: '#f4f5f7',
    colorBgElevated: '#ffffff',
    colorBgSpotlight: '#252830',

    // === 边框 ===
    colorBorder: '#e3e8ee',
    colorBorderSecondary: '#e3e8ee',

    // === 其他 ===
    colorSuccess: '#10b981',
    colorWarning: '#f59e0b',
    colorError: '#ea2261',
    colorInfo: '#202124',

    // === 字体 ===
    fontFamily: `"Inter", -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", Roboto, sans-serif`,
    fontSize: 14,
    fontSizeHeading1: 32,
    fontSizeHeading2: 24,
    fontSizeHeading3: 20,
    fontSizeHeading4: 18,
    fontSizeHeading5: 16,

    // === 圆角 (紧凑) ===
    borderRadius: 6,
    borderRadiusLG: 8,
    borderRadiusSM: 4,

    // === 行高 ===
    lineHeight: 1.5,

    // === 间距 ===
    padding: 16,
    paddingLG: 24,
    paddingXS: 8,
    paddingSM: 12,
    paddingXL: 32,

    // === 控件 ===
    controlHeight: 36,
    controlHeightLG: 42,
    controlHeightSM: 30,
  },
  components: {
    Button: {
      borderRadius: 6,
      controlHeight: 36,
      paddingContentHorizontal: 16,
      fontWeight: 500,
    },
    Card: {
      borderRadius: 8,
      padding: 24,
    },
    Table: {
      borderRadius: 8,
      headerBg: '#f4f5f7',
      headerColor: '#252830',
      rowHoverBg: '#f4f5f7',
      borderColor: '#e3e8ee',
    },
    Menu: {
      itemBg: 'transparent',
      subMenuItemBg: 'transparent',
      darkItemBg: '#ffffff',
      darkSubMenuItemBg: '#152d47',
      darkItemColor: '#c8d2dc',
      darkItemSelectedBg: '#202124',
      darkItemHoverBg: 'rgba(83, 58, 253, 0.15)',
    },
    Layout: {
      siderBg: '#ffffff',
      triggerBg: '#252830',
      triggerColor: '#c8d2dc',
    },
    Input: {
      borderRadius: 6,
      controlHeight: 36,
      paddingInline: 12,
    },
    Select: {
      borderRadius: 6,
      controlHeight: 36,
    },
    Tag: {
      borderRadius: 9999,
    },
    Modal: {
      borderRadius: 10,
    },
    Tabs: {
      inkBarColor: '#202124',
      itemActiveColor: '#202124',
      itemHoverColor: '#42454a',
    },
    Progress: {
      defaultColor: '#202124',
    },
  },
};

export default theme;
