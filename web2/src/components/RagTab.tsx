import React, { useState, useRef, useCallback, useEffect } from 'react';
import { Upload, FileText, Search, Trash2, Loader2, BookOpen, MessageSquare, Sparkles, Settings, Key, Globe, Plus, History, ChevronRight, ChevronLeft } from 'lucide-react';
import {
  RagDocument, RagMessage, LlmApiConfig, RagSource, DEFAULT_LLM_CONFIG,
} from '../types';

function loadLlmConfig(): LlmApiConfig {
  try {
    const saved = localStorage.getItem('pcb_llm_config');
    return saved ? { ...DEFAULT_LLM_CONFIG, ...JSON.parse(saved) } : DEFAULT_LLM_CONFIG;
  } catch { return DEFAULT_LLM_CONFIG; }
}

interface RagConversation {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  messages: RagMessage[];
}

interface RagChatState {
  activeId: string;
  conversations: RagConversation[];
}

function newConversation(): RagConversation {
  const now = new Date().toISOString();
  return {
    id: `rag-chat-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    title: '新对话',
    createdAt: now,
    updatedAt: now,
    messages: [],
  };
}

function loadChatState(): RagChatState {
  try {
    const saved = localStorage.getItem('pcb_rag_conversations');
    const conversations: RagConversation[] = saved ? JSON.parse(saved) : [];
    if (conversations.length > 0) {
      const savedActive = localStorage.getItem('pcb_rag_active_conversation');
      const activeId = conversations.some((item) => item.id === savedActive)
        ? savedActive as string
        : conversations[0].id;
      return { activeId, conversations };
    }
  } catch {}
  const first = newConversation();
  return { activeId: first.id, conversations: [first] };
}

export const RagTab: React.FC<{ pushLog: (msg: string) => void }> = ({ pushLog }) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [documents, setDocuments] = useState<RagDocument[]>([]);
  const [query, setQuery] = useState('');
  const [isQuerying, setIsQuerying] = useState(false);
  const [chatState, setChatState] = useState<RagChatState>(loadChatState);
  const [isUploading, setIsUploading] = useState(false);
  const [showDocumentManager, setShowDocumentManager] = useState(true);
  const [selectedConversationIds, setSelectedConversationIds] = useState<Set<string>>(new Set());

  const activeConversation = chatState.conversations.find(
    (conversation) => conversation.id === chatState.activeId,
  ) || chatState.conversations[0];
  const messages = activeConversation?.messages || [];

  const setMessages = useCallback((updater: React.SetStateAction<RagMessage[]>) => {
    setChatState((previous) => ({
      ...previous,
      conversations: previous.conversations.map((conversation) => {
        if (conversation.id !== previous.activeId) return conversation;
        const nextMessages = typeof updater === 'function'
          ? updater(conversation.messages)
          : updater;
        const firstUserMessage = nextMessages.find((message) => message.role === 'user');
        return {
          ...conversation,
          messages: nextMessages,
          title: firstUserMessage
            ? firstUserMessage.content.slice(0, 24)
            : conversation.title,
          updatedAt: new Date().toISOString(),
        };
      }),
    }));
  }, []);

  useEffect(() => {
    localStorage.setItem('pcb_rag_conversations', JSON.stringify(chatState.conversations));
    localStorage.setItem('pcb_rag_active_conversation', chatState.activeId);
  }, [chatState]);

  const createNewConversation = () => {
    const conversation = newConversation();
    setChatState((previous) => ({
      activeId: conversation.id,
      conversations: [conversation, ...previous.conversations].slice(0, 30),
    }));
    setQuery('');
    setIsQuerying(false);
    pushLog('[RAG] 已新建对话');
  };

  const deleteConversations = (ids: string[]) => {
    if (ids.length === 0) return;
    const deleteSet = new Set(ids);
    setChatState((previous) => {
      const remaining = previous.conversations.filter(
        (conversation) => !deleteSet.has(conversation.id),
      );
      if (remaining.length > 0) {
        const activeId = deleteSet.has(previous.activeId)
          ? remaining[0].id
          : previous.activeId;
        return { activeId, conversations: remaining };
      }
      const replacement = newConversation();
      return { activeId: replacement.id, conversations: [replacement] };
    });
    setSelectedConversationIds(new Set());
    setQuery('');
    pushLog(`[RAG] 已删除 ${ids.length} 个对话`);
  };

  const toggleConversationSelection = (id: string) => {
    setSelectedConversationIds((previous) => {
      const next = new Set(previous);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  // LLM API 配置
  const [llmConfig, setLlmConfig] = useState<LlmApiConfig>(loadLlmConfig);
  const [showLlmConfig, setShowLlmConfig] = useState(false);
  // 编辑草稿（点击保存才生效）
  const [draftConfig, setDraftConfig] = useState<LlmApiConfig>(loadLlmConfig);

  const saveLlmConfig = () => {
    setLlmConfig(draftConfig);
    localStorage.setItem('pcb_llm_config', JSON.stringify(draftConfig));
  };

  // 加载已入库文档
  const loadDocs = useCallback(async () => {
    try {
      const resp = await fetch('/api/rag/documents');
      const data = await resp.json();
      console.log('[RAG] 文档列表:', data.documents?.length || 0, '条');
      setDocuments(data.documents || []);
    } catch (err: any) {
      console.error('[RAG] 加载文档列表失败:', err);
    }
  }, []);

  useEffect(() => { loadDocs(); }, [loadDocs]);

  const handleFileSelect = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    setIsUploading(true);
    for (let fi = 0; fi < files.length; fi++) {
      const file = files.item(fi);
      if (!file) continue;
      pushLog(`[RAG] 上传文档: ${file.name}`);

      try {
        const form = new FormData();
        form.append('file', file);
        const resp = await fetch('/api/rag/upload', { method: 'POST', body: form });
        const result = await resp.json();
        console.log('[RAG] 上传响应:', result);
        if (result.success) {
          pushLog(`[RAG] 索引完成: ${file.name} (${result.chunks} 块)`);
        } else {
          pushLog(`[RAG] 上传失败: ${result.error || '未知错误'}`);
        }
      } catch (err: any) {
        console.error('[RAG] 上传异常:', err);
        pushLog(`[RAG] 上传异常: ${err?.message || String(err)}`);
      }
    }
    setIsUploading(false);
    loadDocs();
    if (fileInputRef.current) fileInputRef.current.value = '';
  }, [pushLog, loadDocs]);

  const removeDoc = async (id: string) => {
    const doc = documents.find((d) => d.id === id);
    try {
      const resp = await fetch(`/api/rag/documents/${encodeURIComponent(id)}`, { method: 'DELETE' });
      const result = await resp.json();
      if (!resp.ok || !result.success) {
        throw new Error(result.error || `HTTP ${resp.status}`);
      }
      if (doc) pushLog(`[RAG] 删除文档: ${doc.name}`);
      await loadDocs();
    } catch (err: any) {
      const message = err?.message || String(err);
      console.error('[RAG] 删除文档失败:', err);
      pushLog(`[RAG] 删除失败: ${message}`);
    }
  };

  const clearAllDocs = async () => {
    for (const doc of documents) {
      await removeDoc(doc.id);
    }
  };

  const handleQuery = useCallback(async () => {
    if (!query.trim()) return;
    const userMsg: RagMessage = { role: 'user', content: query };
    setMessages((prev) => [...prev, userMsg]);
    setQuery('');
    setIsQuerying(true);

    try {
      const resp = await fetch('/api/rag/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: userMsg.content, llm: llmConfig }),
      });
      const result = await resp.json();
      let content = result.answer || '检索无结果。';
      // 如果有来源，追加到回答末尾
      if (result.sources && result.sources.length > 0) {
        content += '\n\n---\n**参考来源：**\n';
        result.sources.forEach((s: any, i: number) => {
          content += `\n${i + 1}. *${s.doc_name}* (相关度 ${(s.score * 100).toFixed(1)}%)`;
        });
      }
      setMessages((prev) => [...prev, { role: 'assistant', content }]);
    } catch (err: any) {
      setMessages((prev) => [...prev, { role: 'assistant', content: `检索失败: ${err?.message || String(err)}` }]);
    }
    setIsQuerying(false);
  }, [query, pushLog]);

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const formatTime = (iso: string) => {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '时间未知';
    return d.toLocaleString(undefined, {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    });
  };

  return (
    <div className="flex-1 min-h-0 p-6 overflow-hidden flex gap-4 select-none items-stretch">
      {/* 左侧：对话管理 */}
      <div className="order-1 w-64 shrink-0 min-h-0 bg-[#1c1c1e] rounded-xl border border-[#2c2c2e] flex flex-col overflow-hidden">
        <div className="p-4 border-b border-[#2c2c2e] space-y-3 shrink-0">
          <div className="flex items-center gap-2">
            <History className="h-4 w-4 text-[#bf5af2]" />
            <span className="text-xs font-semibold text-white">历史对话</span>
            <span className="ml-auto text-[10px] text-[#8e8e93]">{chatState.conversations.length}</span>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <button onClick={createNewConversation}
              className="flex items-center justify-center gap-1.5 px-3 py-2 bg-[#0a84ff] hover:bg-[#0a84ff]/90 text-white rounded-lg text-xs font-semibold transition cursor-pointer">
              <Plus className="h-3.5 w-3.5" />新建对话
            </button>
            <button onClick={() => deleteConversations(Array.from(selectedConversationIds))}
              disabled={isQuerying || selectedConversationIds.size === 0}
              title="批量删除已选对话"
              className="flex items-center justify-center gap-1.5 px-2 py-2 border border-[#ff453a]/30 bg-[#ff453a]/10 hover:bg-[#ff453a]/20 disabled:opacity-40 text-[#ff453a] rounded-lg text-xs transition cursor-pointer">
              <Trash2 className="h-3.5 w-3.5" />批量删除{selectedConversationIds.size > 0 && ` (${selectedConversationIds.size})`}
            </button>
          </div>
        </div>
        <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain p-2 space-y-1">
          {chatState.conversations.map((conversation) => (
            <div key={conversation.id}
              className={`group w-full flex items-center gap-2 px-2 py-2 rounded-lg border transition ${
                conversation.id === chatState.activeId
                  ? 'bg-[#bf5af2]/15 border-[#bf5af2]/30'
                  : 'bg-black/20 border-transparent hover:bg-white/5'
              }`}>
              <input type="checkbox" checked={selectedConversationIds.has(conversation.id)}
                onChange={() => toggleConversationSelection(conversation.id)}
                aria-label={`选择对话 ${conversation.title}`}
                className="h-3.5 w-3.5 accent-[#bf5af2] cursor-pointer shrink-0" />
              <button onClick={() => setChatState((previous) => ({ ...previous, activeId: conversation.id }))}
                className="flex-1 min-w-0 text-left cursor-pointer">
                <p className="text-xs text-white truncate">{conversation.title}</p>
                <p className="text-[9px] text-[#8e8e93] mt-1 truncate">
                  {new Date(conversation.updatedAt).toLocaleString()} · {conversation.messages.length} 条
                </p>
              </button>
              <button onClick={() => deleteConversations([conversation.id])} disabled={isQuerying}
                title="删除此对话"
                className="p-1.5 text-[#8e8e93] hover:text-[#ff453a] hover:bg-[#ff453a]/10 disabled:opacity-40 rounded cursor-pointer shrink-0">
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* 右侧：统一文档管理 */}
      <div className={`order-3 shrink-0 min-h-0 transition-[width] duration-200 ${showDocumentManager ? 'w-80' : 'w-12'}`}>
        {!showDocumentManager ? (
          <button onClick={() => setShowDocumentManager(true)} title="展开知识库文档管理"
            className="w-12 h-full bg-[#1c1c1e] rounded-xl border border-[#2c2c2e] flex flex-col items-center pt-4 gap-3 text-[#0a84ff] hover:bg-white/5 cursor-pointer">
            <BookOpen className="h-5 w-5" /><ChevronLeft className="h-4 w-4" />
            <span className="text-[10px] [writing-mode:vertical-rl] tracking-wider">知识库文档</span>
          </button>
        ) : (
          <div className="h-full min-h-0 bg-[#1c1c1e] rounded-xl border border-[#2c2c2e] flex flex-col overflow-hidden">
            <div className="px-4 py-3 border-b border-[#2c2c2e] flex items-center gap-2 shrink-0">
              <BookOpen className="h-5 w-5 text-[#0a84ff]" />
              <h3 className="text-sm font-semibold text-white">知识库文档</h3>
              <span className="text-[10px] text-[#8e8e93]">{documents.length} 个</span>
              <button onClick={() => setShowDocumentManager(false)} title="向右收起"
                className="ml-auto text-[#8e8e93] hover:text-white cursor-pointer"><ChevronRight className="h-4 w-4" /></button>
            </div>

            <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain">
              <div className="p-4 border-b border-[#2c2c2e]">
                <div onClick={() => fileInputRef.current?.click()}
                  className="border-2 border-dashed border-[#2c2c2e] rounded-xl p-5 text-center cursor-pointer hover:border-[#0a84ff]/50 transition">
                  {isUploading ? <Loader2 className="h-7 w-7 text-[#0a84ff] animate-spin mx-auto mb-2" /> : <Upload className="h-7 w-7 text-[#8e8e93] mx-auto mb-2" />}
                  <p className="text-xs text-[#8e8e93]">{isUploading ? '正在索引文档...' : '点击上传 PDF / TXT / MD'}</p>
                </div>
                <input ref={fileInputRef} type="file" multiple accept=".pdf,.txt,.md,.doc,.docx" className="hidden" onChange={handleFileSelect} />

                <button onClick={() => { setShowLlmConfig(!showLlmConfig); if (!showLlmConfig) setDraftConfig(llmConfig); }}
                  className="mt-3 pt-3 border-t border-[#2c2c2e] flex items-center gap-2 text-xs text-[#8e8e93] hover:text-white transition cursor-pointer w-full">
                  <Settings className="h-3.5 w-3.5" /><span>大模型 API 配置</span>
                  <span className={`text-[10px] ${llmConfig.apiKey ? 'text-[#30d158]' : 'text-[#ff9f0a]'}`}>{llmConfig.apiKey ? '已配置' : '未配置'}</span>
                </button>
                {showLlmConfig && <div className="mt-3 space-y-3 text-xs">
                  <label className="block"><span className="text-[10px] text-[#8e8e93] flex items-center gap-1 mb-1"><Globe className="h-3 w-3" />API 端点</span><input type="text" value={draftConfig.endpoint} onChange={(e) => setDraftConfig({ ...draftConfig, endpoint: e.target.value })} className="w-full bg-black/40 border border-[#2c2c2e] text-white p-2 rounded text-[10px]" /></label>
                  <label className="block"><span className="text-[10px] text-[#8e8e93] flex items-center gap-1 mb-1"><Key className="h-3 w-3" />API Key</span><input type="password" value={draftConfig.apiKey} onChange={(e) => setDraftConfig({ ...draftConfig, apiKey: e.target.value })} className="w-full bg-black/40 border border-[#2c2c2e] text-white p-2 rounded text-[10px]" /></label>
                  <label className="block"><span className="text-[10px] text-[#8e8e93] flex items-center gap-1 mb-1"><Sparkles className="h-3 w-3" />模型名称</span><input type="text" value={draftConfig.model} onChange={(e) => setDraftConfig({ ...draftConfig, model: e.target.value })} className="w-full bg-black/40 border border-[#2c2c2e] text-white p-2 rounded text-[10px]" /></label>
                  <button onClick={() => { saveLlmConfig(); pushLog('[RAG] LLM API 配置已保存'); }} className="w-full py-1.5 bg-[#0a84ff] text-white rounded font-bold text-[11px]">保存配置</button>
                </div>}
              </div>

              <div className="px-4 py-3 flex items-center border-b border-[#2c2c2e]">
                <FileText className="h-4 w-4 text-[#0a84ff] mr-2" /><span className="text-xs font-semibold text-white">文档列表</span>
                {documents.length > 0 && <button onClick={clearAllDocs} className="ml-auto text-[10px] text-[#ff453a] hover:text-white">全部清除</button>}
              </div>
              <div className="divide-y divide-[#2c2c2e]">
                {documents.map((doc) => <div key={doc.id} className="px-4 py-3 flex items-center justify-between hover:bg-white/5">
                  <div className="min-w-0"><p className="text-xs text-white truncate">{doc.name}</p><p className="text-[10px] text-[#8e8e93] mt-0.5">{formatSize(doc.size)} · {formatTime(doc.uploadedAt)}{doc.status === 'ready' && ` · ${doc.chunks} 块`}</p></div>
                  <button onClick={() => removeDoc(doc.id)} className="ml-2 text-[#8e8e93] hover:text-[#ff453a]"><Trash2 className="h-3.5 w-3.5" /></button>
                </div>)}
                {documents.length === 0 && <div className="text-center py-10 text-[#8e8e93] text-xs">暂无文档</div>}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* 中间：RAG 检索对话 */}
      <div className="order-2 flex-1 min-w-0 min-h-0 flex flex-col overflow-hidden">
        <div className="bg-[#1c1c1e] rounded-xl border border-[#2c2c2e] flex-1 min-h-0 flex flex-col overflow-hidden">
          <div className="px-5 py-3 border-b border-[#2c2c2e] flex items-center justify-between gap-3 shrink-0">
            <div className="flex items-center space-x-2 min-w-0">
              <MessageSquare className="h-4 w-4 text-[#bf5af2] shrink-0" />
              <span className="text-xs font-semibold text-[#8e8e93] uppercase tracking-wider">知识库检索</span>
              <span className="text-[10px] text-white truncate">{activeConversation?.title || '新对话'}</span>
            </div>
            <span className="text-[10px] text-[#8e8e93] shrink-0">{messages.length} 条消息</span>
          </div>

          {/* 对话记录 */}
          <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain p-4 space-y-4">
            {messages.length === 0 && (
              <div className="h-full flex flex-col items-center justify-center text-center text-[#8e8e93]">
                <Sparkles className="h-10 w-10 text-[#bf5af2] mb-3" />
                <p className="text-sm font-semibold text-white mb-1">PCB 缺陷检测 RAG 知识库</p>
                <p className="text-xs max-w-md">
                  上传 PCB 缺陷检测文档构建知识库，可通过自然语言检索相关技术文档内容。
                </p>
              </div>
            )}
            {messages.map((msg, i) => (
              <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div className={`max-w-[85%] p-3 rounded-xl text-xs ${
                  msg.role === 'user'
                    ? 'bg-[#0a84ff]/20 border border-[#0a84ff]/30 text-white'
                    : 'bg-black/40 border border-[#2c2c2e] text-[#f5f5f7]'
                }`}>
                  {msg.role === 'assistant' ? (
                    <div className="whitespace-pre-wrap">
                      {msg.content.split('\n').map((line, j) => (
                        <p key={j} className={line.startsWith('**') ? 'font-bold text-[#0a84ff] mt-2' : 'text-[#cccccc]'}>
                          {line.replace(/\*\*/g, '')}
                        </p>
                      ))}
                    </div>
                  ) : (
                    <p>{msg.content}</p>
                  )}
                </div>
              </div>
            ))}
            {isQuerying && (
              <div className="flex justify-start">
                <div className="bg-black/40 border border-[#2c2c2e] p-3 rounded-xl flex items-center space-x-2">
                  <Loader2 className="h-3.5 w-3.5 text-[#0a84ff] animate-spin" />
                  <span className="text-xs text-[#8e8e93]">正在检索知识库...</span>
                </div>
              </div>
            )}
          </div>

          {/* 输入框 */}
          <div className="p-3 border-t border-[#2c2c2e] shrink-0">
            <div className="flex space-x-2">
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleQuery()}
                placeholder="输入问题，检索知识库..."
                className="flex-1 bg-black/40 border border-[#2c2c2e] text-[#f5f5f7] rounded-lg px-3 py-2 text-xs focus:outline-none focus:border-[#0a84ff]"
              />
              <button
                onClick={handleQuery}
                disabled={isQuerying || !query.trim()}
                className="px-3 py-2 bg-gradient-to-r from-[#0a84ff] to-[#bf5af2] hover:opacity-90 disabled:opacity-40 text-white rounded-lg text-xs font-semibold transition cursor-pointer flex items-center space-x-1"
              >
                <Search className="h-3.5 w-3.5" />
                <span>检索</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
