import React from 'react';
import { Zap, Sun, Moon } from 'lucide-react';
import { TelemetryMetrics } from '../types';

interface HeaderProps {
  metrics: TelemetryMetrics;
  wsConnected: boolean;
  isDarkMode: boolean;
  setIsDarkMode: (dark: boolean) => void;
}

export const Header: React.FC<HeaderProps> = ({ metrics, wsConnected, isDarkMode, setIsDarkMode }) => {
  return (
    <header className="h-16 border-b border-[#2c2c2e] bg-[#1c1c1e] px-6 flex items-center justify-between z-10 select-none transition-colors duration-250">
      <div className="flex items-center space-x-3">
        <div className="relative flex h-3 w-3">
          <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${wsConnected ? 'bg-[#30d158]' : 'bg-[#ff453a]'}`} />
          <span className={`relative inline-flex rounded-full h-3 w-3 ${wsConnected ? 'bg-[#30d158]' : 'bg-[#ff453a]'}`} />
        </div>
        <h1 className="text-lg font-bold tracking-tight font-sans text-white">
          PCB 缺陷检测系统 <span className="text-xs text-[#8e8e93] font-normal font-mono">v1.0.0</span>
        </h1>
      </div>

      <div className="flex items-center space-x-4 text-sm font-mono">
        <div className="flex items-center space-x-2 text-[#8e8e93] bg-black/40 px-3 py-1.5 rounded-lg border border-[#2c2c2e]">
          <Zap className="h-4 w-4 text-[#0a84ff] animate-pulse" />
          <span>FPS:</span>
          <span className="text-white font-bold">{metrics.fps || 60}</span>
        </div>

        <button
          onClick={() => setIsDarkMode(!isDarkMode)}
          title={isDarkMode ? '切换到亮色模式' : '切换到暗色模式'}
          className="flex items-center justify-center p-2 rounded-lg bg-black/40 hover:bg-[#2c2c2e] border border-[#2c2c2e] transition text-[#8e8e93] hover:text-white cursor-pointer"
        >
          {isDarkMode ? (
            <Sun className="h-4 w-4 text-[#ff9f0a]" />
          ) : (
            <Moon className="h-4 w-4 text-[#bf5af2]" />
          )}
        </button>
      </div>
    </header>
  );
};
