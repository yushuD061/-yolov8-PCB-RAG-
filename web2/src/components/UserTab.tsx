import React, { useState } from 'react';
import { User, Mail, ShieldCheck, Calendar, Save, LogOut } from 'lucide-react';

interface UserTabProps {
  logs: string[];
  currentUser?: string;
  onLogout?: () => void;
}

export const UserTab: React.FC<UserTabProps> = ({ currentUser = 'PCB 检测系统管理员', onLogout }) => {
  const [adminName, setAdminName] = useState<string>(currentUser);
  const [isEditingName, setIsEditingName] = useState<boolean>(false);
  const [tempName, setTempName] = useState<string>(adminName);

  const loginEmail = 'admin@pcb-detector.local';

  const handleSaveName = () => {
    setAdminName(tempName);
    setIsEditingName(false);
  };

  return (
    <div id="user_profile_view" className="flex-1 p-6 overflow-y-auto select-none transition-colors duration-150">
      <div className="max-w-3xl mx-auto space-y-6">
        
        {/* 个人信息 */}
        <div className="bg-[#1c1c1e] p-6 rounded-xl border border-[#2c2c2e] space-y-6">
          <div className="flex items-center space-x-3 border-b border-[#2c2c2e] pb-4">
            <User className="h-5 w-5 text-[#0a84ff]" />
            <h3 className="text-base font-semibold text-white font-sans">个人中心</h3>
          </div>

          <div className="flex items-start space-x-6">
            <div className="relative">
              <div className="h-20 w-20 rounded-full bg-gradient-to-tr from-[#0a84ff] to-[#bf5af2] flex items-center justify-center shadow-lg shadow-[#0a84ff]/20">
                <span className="text-2xl font-bold font-sans text-white">AD</span>
              </div>
              <span className="absolute bottom-0 right-0 h-5 w-5 rounded-full bg-[#30d158] border-2 border-[#1c1c1e] flex items-center justify-center" title="在线" />
            </div>

            <div className="flex-1 space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-[10px] text-[#8e8e93] block uppercase font-mono tracking-wider mb-1">管理员名称</label>
                  {isEditingName ? (
                    <div className="flex items-center space-x-2">
                      <input
                        type="text"
                        value={tempName}
                        onChange={(e) => setTempName(e.target.value)}
                        className="bg-black/40 border border-[#2c2c2e] px-2 py-1 rounded text-xs text-white focus:outline-none focus:border-[#0a84ff] w-full"
                      />
                      <button
                        onClick={handleSaveName}
                        className="p-1 rounded bg-[#30d158]/20 hover:bg-[#30d158]/30 text-[#30d158] transition cursor-pointer"
                      >
                        <Save className="h-4 w-4" />
                      </button>
                    </div>
                  ) : (
                    <div className="flex items-center space-x-2">
                      <span className="text-sm font-semibold text-white">{adminName}</span>
                      <button
                        onClick={() => {
                          setTempName(adminName);
                          setIsEditingName(true);
                        }}
                        className="text-xs text-[#0a84ff] hover:underline transition cursor-pointer"
                      >
                        [编辑]
                      </button>
                    </div>
                  )}
                </div>

                <div>
                  <label className="text-[10px] text-[#8e8e93] block uppercase font-mono tracking-wider mb-1">注册邮箱</label>
                  <div className="flex items-center space-x-1.5 text-xs text-white">
                    <Mail className="h-3.5 w-3.5 text-[#8e8e93]" />
                    <span>{loginEmail}</span>
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4 pt-4 border-t border-[#2c2c2e]/40">
                <div className="space-y-1">
                  <span className="text-[10px] text-[#8e8e93] block uppercase font-mono tracking-wider">系统角色</span>
                  <div className="flex items-center space-x-1.5 text-xs text-[#30d158] font-semibold">
                    <ShieldCheck className="h-3.5 w-3.5" />
                    <span>管理员</span>
                  </div>
                </div>

                <div className="space-y-1">
                  <span className="text-[10px] text-[#8e8e93] block uppercase font-mono tracking-wider">最后登录时间</span>
                  <div className="flex items-center space-x-1.5 text-xs text-white/90 font-mono">
                    <Calendar className="h-3.5 w-3.5 text-[#8e8e93]" />
                    <span>2026-06-19 22:04:42</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* 合规说明 */}
        <div className="bg-[#1c1c1e]/60 p-4 rounded-xl border border-[#2c2c2e]/60 flex items-center space-x-3">
          <ShieldCheck className="h-5 w-5 text-[#0a84ff] shrink-0" />
          <div className="text-[10px] text-[#8e8e93] leading-relaxed">
            <strong>安全合规:</strong> 所有检测数据在本地处理，不经过外部服务器。
          </div>
        </div>

        {/* 退出登录 */}
        {onLogout && (
          <div className="pt-2 flex justify-start">
            <button
              onClick={onLogout}
              className="px-5 py-2.5 rounded-lg bg-[#ff453a]/10 hover:bg-[#ff453a]/20 border border-[#ff453a]/25 text-[#ff453a] hover:text-[#ff453a] text-xs font-semibold tracking-wider transition cursor-pointer flex items-center space-x-2"
            >
              <LogOut className="h-4 w-4" />
              <span>退出登录</span>
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
