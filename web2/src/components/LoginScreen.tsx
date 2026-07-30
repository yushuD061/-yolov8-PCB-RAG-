import React, { useState } from 'react';
import { Shield, Key, User, ArrowRight, RefreshCw, Eye, EyeOff, AlertCircle, HardDrive } from 'lucide-react';

interface LoginScreenProps {
  onLogin: (username: string) => void;
  isDarkMode: boolean;
  setIsDarkMode: (val: boolean) => void;
}

export const LoginScreen: React.FC<LoginScreenProps> = ({ onLogin, isDarkMode, setIsDarkMode }) => {
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('pcb_admin');
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [loadingStep, setLoadingStep] = useState('');
  const [error, setError] = useState<string | null>(null);

  const handleLogin = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!username.trim()) {
      setError('请输入系统账户名称');
      return;
    }
    if (password.length < 5) {
      setError('安全密钥长度过短，必须大于 5 个字符');
      return;
    }

    setIsLoading(true);

    const steps = [
      '正在连接推理引擎守护进程...',
      '正在执行安全签名校验...',
      '正在载入 PCB 检测沙盒...',
      '安全校验完成，即将进入系统...'
    ];

    let currentStep = 0;
    setLoadingStep(steps[0]);

    const interval = setInterval(() => {
      currentStep++;
      if (currentStep < steps.length) {
        setLoadingStep(steps[currentStep]);
      } else {
        clearInterval(interval);
        setIsLoading(false);
        onLogin(username === 'admin' ? 'PCB 检测系统管理员' : username);
      }
    }, 600);
  };

  const applyPreset = (role: 'admin' | 'guest') => {
    if (role === 'admin') {
      setUsername('admin');
      setPassword('pcb_admin');
    } else {
      setUsername('guest');
      setPassword('guest_pass');
    }
    setError(null);
  };

  return (
    <div id="login_terminal_view" className={`min-h-screen flex flex-col justify-between transition-colors duration-200 ${isDarkMode ? 'bg-[#09090b] text-[#f5f5f7]' : 'bg-[#f4f4f6] text-[#1c1c1e]'}`}>
      
      <div className="absolute top-0 left-0 w-full h-[320px] pointer-events-none overflow-hidden opacity-30">
        <div className="absolute inset-0 bg-[radial-gradient(#0a84ff_1.2px,transparent_1.2px)] [background-size:24px_24px] mask-gradient-b" />
      </div>

      <header className="relative z-10 px-8 py-6 flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="h-9 w-9 rounded-lg bg-[#0a84ff] flex items-center justify-center shadow-[0_0_15px_rgba(10,132,255,0.4)]">
            <Shield className="h-5 w-5 text-white" />
          </div>
          <div>
            <span className="text-sm font-bold tracking-wider font-mono">PCB DEFECT DETECTOR</span>
            <span className="text-xs text-[#8e8e93] block font-sans">PCB 缺陷检测系统</span>
          </div>
        </div>

        <button
          id="toggle_theme_btn"
          onClick={() => setIsDarkMode(!isDarkMode)}
          className={`px-3 py-1.5 rounded-full text-xs font-medium border cursor-pointer transition flex items-center space-x-1.5 ${
            isDarkMode 
              ? 'bg-[#1c1c1e] border-[#2c2c2e] text-[#a2a2a7] hover:text-white' 
              : 'bg-white border-[#d1d1d6] text-[#55555d] hover:bg-gray-50'
          }`}
        >
          <span>{isDarkMode ? '🌙 暗色视觉模式' : '☀️ 亮色视觉模式'}</span>
        </button>
      </header>

      <main className="relative z-10 flex-1 flex items-center justify-center p-4">
        <div className="w-full max-w-md">
          <div className={`p-8 rounded-2xl border transition-all duration-350 shadow-2xl ${
            isDarkMode 
              ? 'bg-[#1c1c1e]/80 border-[#2c2c2e] backdrop-blur-md' 
              : 'bg-white/95 border-[#e5e5ea] shadow-gray-200'
          }`}>
            
            <div className="text-center space-y-2 mb-8">
              <h2 className="text-xl font-bold tracking-tight font-sans">
                系统安全准入
              </h2>
              <p className="text-xs text-[#8e8e93] leading-relaxed max-w-xs mx-auto">
                使用管理员凭证登录 PCB 缺陷检测系统。
              </p>
            </div>

            {error && (
              <div className="mb-5 p-3 rounded-lg bg-red-500/10 border border-red-500/25 flex items-start space-x-2 text-xs text-[#ff453a] animate-headshake">
                <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
                <span className="font-medium">{error}</span>
              </div>
            )}

            <form onSubmit={handleLogin} className="space-y-5">
              <div className="space-y-1.5">
                <label className="text-[10px] text-[#8e8e93] block uppercase font-mono font-bold tracking-widest">
                  系统账户
                </label>
                <div id="username_field_group" className="relative flex items-center">
                  <User className="absolute left-3.5 h-4 w-4 text-[#8e8e93]" />
                  <input
                    type="text"
                    required
                    disabled={isLoading}
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    placeholder="管理员账户"
                    className={`w-full pl-10 pr-4 py-2.5 rounded-lg text-sm transition-all focus:outline-none focus:ring-1 focus:ring-[#0a84ff] border ${
                      isDarkMode 
                        ? 'bg-black/30 border-[#2c2c2e] text-[#f5f5f7]' 
                        : 'bg-gray-50 border-[#d1d1d6] text-[#1c1c1e]'
                    }`}
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <label className="text-[10px] text-[#8e8e93] uppercase font-mono font-bold tracking-widest">
                    安全密钥
                  </label>
                  <span className="text-[9px] text-[#0a84ff] hover:underline cursor-pointer">
                    重置
                  </span>
                </div>
                <div id="password_field_group" className="relative flex items-center">
                  <Key className="absolute left-3.5 h-4 w-4 text-[#8e8e93]" />
                  <input
                    type={showPassword ? 'text' : 'password'}
                    required
                    disabled={isLoading}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="请输入安全密钥"
                    className={`w-full pl-10 pr-11 py-2.5 rounded-lg text-sm transition-all focus:outline-none focus:ring-1 focus:ring-[#0a84ff] border ${
                      isDarkMode 
                        ? 'bg-black/30 border-[#2c2c2e] text-[#f5f5f7]' 
                        : 'bg-gray-50 border-[#d1d1d6] text-[#1c1c1e]'
                    }`}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 text-[#8e8e93] hover:text-[#0a84ff] p-1 transition cursor-pointer"
                  >
                    {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </div>

              <button
                type="submit"
                id="submit_login_btn"
                disabled={isLoading}
                className="w-full relative mt-2 py-3 rounded-lg bg-[#0a84ff] text-white hover:bg-[#0a84ff]/90 disabled:opacity-85 text-xs font-semibold tracking-wider transition-all shadow-lg shadow-[#0a84ff]/15 select-none flex items-center justify-center space-x-2 cursor-pointer"
                style={{ height: '42px' }}
              >
                {isLoading ? (
                  <>
                    <RefreshCw className="h-4 w-4 animate-spin text-white" />
                    <span>安全握手中...</span>
                  </>
                ) : (
                  <>
                    <span>确 认 登 录</span>
                    <ArrowRight className="h-4 w-4" />
                  </>
                )}
              </button>
            </form>

            <div className="mt-6 pt-5 border-t border-[#2c2c2e]/40 flex flex-col space-y-3">
              <span className="text-[10px] text-[#8e8e93] text-center font-mono font-bold tracking-widest uppercase">
                快速填充
              </span>
              <div className="grid grid-cols-2 gap-3">
                <button
                  type="button"
                  id="preset_admin"
                  disabled={isLoading}
                  onClick={() => applyPreset('admin')}
                  className={`py-2 rounded px-3 text-[10px] font-medium font-sans border text-center transition cursor-pointer ${
                    isDarkMode 
                      ? 'bg-black/40 border-[#2c2c2e] text-white hover:bg-black/80' 
                      : 'bg-gray-50 border-[#d1d1d6] text-gray-700 hover:bg-gray-100'
                  }`}
                >
                  管理员
                </button>
                <button
                  type="button"
                  id="preset_guest"
                  disabled={isLoading}
                  onClick={() => applyPreset('guest')}
                  className={`py-2 rounded px-3 text-[10px] font-medium font-sans border text-center transition cursor-pointer ${
                    isDarkMode 
                      ? 'bg-black/40 border-[#2c2c2e] text-white hover:bg-black/80' 
                      : 'bg-gray-50 border-[#d1d1d6] text-gray-700 hover:bg-gray-100'
                  }`}
                >
                  访客模式
                </button>
              </div>
            </div>

            {isLoading && (
              <div className="mt-4 text-center">
                <span className="inline-block px-3 py-1 rounded bg-[#ff9f0a]/10 border border-[#ff9f0a]/35 text-[#ff9f0a] font-mono text-[9px] animate-pulse">
                  {loadingStep}
                </span>
              </div>
            )}
          </div>
        </div>
      </main>

      <footer className="relative z-10 px-8 py-6 flex flex-col md:flex-row items-center justify-between text-[11px] text-[#8e8e93] font-mono border-t border-[#2c2c2e]/10 space-y-2 md:space-y-0">
        <div className="flex items-center space-x-2">
          <HardDrive className="h-3.5 w-3.5" />
          <span>本地推理引擎</span>
        </div>
        <div className="flex items-center space-x-4">
          <span>算法核心: YOLOv8 + PCB 缺陷检测</span>
          <span className="hidden md:inline text-white/20">|</span>
          <span>PCB 缺陷检测系统 2026</span>
        </div>
      </footer>
    </div>
  );
};
