import React, { useState } from 'react';
import { Monitor, Image, History, Sliders, User, BookOpen, ChevronLeft, PanelLeftClose, PanelLeftOpen } from 'lucide-react';
import { TabId } from '../types';

interface SidebarProps {
  activeTab: TabId;
  setActiveTab: (tab: TabId) => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ activeTab, setActiveTab }) => {
  const [collapsed, setCollapsed] = useState(false);

  const menuItems = [
    { id: 'live_detect' as TabId, name: 'RV1126B 实时检测', icon: Monitor },
    { id: 'image_rec' as TabId, name: 'PCB 图片检测', icon: Image },
    { id: 'history' as TabId, name: '检测历史', icon: History },
    { id: 'config' as TabId, name: '系统配置', icon: Sliders },
    { id: 'rag' as TabId, name: 'RAG 知识库', icon: BookOpen },
    { id: 'user' as TabId, name: '个人中心', icon: User },
  ];

  return (
    <aside className={`border-r border-[#2c2c2e] bg-[#1c1c1e] flex flex-col justify-between py-4 select-none transition-all duration-200 ${collapsed ? 'w-16' : 'w-64'}`}>
      <div>
        <div className={`flex items-center ${collapsed ? 'justify-center' : 'justify-end'} px-3 mb-2`}>
          <button onClick={() => setCollapsed(!collapsed)}
            className="p-1.5 rounded-lg text-[#8e8e93] hover:text-white hover:bg-[#2c2c2e] transition cursor-pointer">
            {collapsed ? <PanelLeftOpen className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
          </button>
        </div>
        <div className="space-y-1 px-2">
          {menuItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setActiveTab(item.id)}
                title={collapsed ? item.name : undefined}
                className={`w-full flex items-center ${collapsed ? 'justify-center' : 'space-x-3 px-4'} py-3 rounded-lg text-sm font-medium transition-all cursor-pointer ${
                  isActive
                    ? 'bg-[#0a84ff] text-white shadow-lg shadow-[#0a84ff]/10'
                    : 'text-[#8e8e93] hover:bg-[#2c2c2e] hover:text-[#f5f5f7]'
                }`}
              >
                <Icon className="h-5 w-5 shrink-0" />
                {!collapsed && <span>{item.name}</span>}
              </button>
            );
          })}
        </div>
      </div>

      {!collapsed && (
        <div className="px-6 text-xs text-[#8e8e93] font-mono leading-relaxed">
          <p>PCB DEFECT DETECTOR</p>
          <p className="mt-1">v1.0.0</p>
        </div>
      )}
    </aside>
  );
};
