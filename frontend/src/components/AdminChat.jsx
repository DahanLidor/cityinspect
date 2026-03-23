import { useState, useRef, useEffect } from 'react';
import { streamAdminChat } from '../api/client';

const SUGGESTED = [
  'כמה טיקטים פתוחים יש כרגע?',
  'מה מצב ה-SLA של הטיקטים הקריטיים?',
  'אילו סוגי תקלות הכי נפוצים?',
  'מה ההמלצה שלך לשיפור זמני תגובה?',
];

function Message({ msg }) {
  const isUser = msg.role === 'user';
  return (
    <div className={`flex gap-2 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
      <div className={`w-7 h-7 rounded-full flex items-center justify-center shrink-0 text-sm ${
        isUser ? 'bg-blue-600' : 'bg-purple-700'
      }`}>
        {isUser ? '👤' : '🤖'}
      </div>
      <div className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap ${
        isUser
          ? 'bg-blue-600 text-white rounded-tr-sm'
          : 'bg-slate-800 border border-slate-700 text-slate-100 rounded-tl-sm'
      }`}>
        {msg.content}
        {msg.streaming && (
          <span className="inline-block w-1.5 h-4 bg-purple-400 animate-pulse ml-1 align-middle" />
        )}
      </div>
    </div>
  );
}

export default function AdminChat({ cityId = 'tel-aviv' }) {
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content: `שלום! אני עוזר ה-AI שלך לניהול CityInspect.\n\nאני יכול לעזור לך לנתח את מצב המערכת, לזהות מגמות, ולהמליץ על שיפורים. שאל אותי כל שאלה על הטיקטים, ה-SLA, הצוותים, או כל נתון אחר.`,
    },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const bottomRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const send = async (text) => {
    const userText = (text || input).trim();
    if (!userText || loading) return;
    setInput('');
    setError('');

    const newMessages = [...messages, { role: 'user', content: userText }];
    setMessages(newMessages);
    setLoading(true);

    // Add streaming placeholder
    setMessages(prev => [...prev, { role: 'assistant', content: '', streaming: true }]);

    try {
      const apiMessages = newMessages.map(m => ({ role: m.role, content: m.content }));

      await streamAdminChat(
        apiMessages,
        cityId,
        (chunk) => {
          setMessages(prev => {
            const updated = [...prev];
            const last = updated[updated.length - 1];
            if (last?.streaming) {
              updated[updated.length - 1] = { ...last, content: last.content + chunk };
            }
            return updated;
          });
        },
        () => {
          setMessages(prev => {
            const updated = [...prev];
            const last = updated[updated.length - 1];
            if (last?.streaming) {
              updated[updated.length - 1] = { ...last, streaming: false };
            }
            return updated;
          });
          setLoading(false);
        },
      );
    } catch (err) {
      setMessages(prev => prev.filter(m => !m.streaming));
      setError(err.message || 'שגיאה בתקשורת עם הסוכן');
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  return (
    <div className="flex flex-col h-full bg-slate-950">
      {/* Header */}
      <div className="px-4 py-3 border-b border-slate-800 bg-slate-900 shrink-0">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-purple-400 animate-pulse" />
          <span className="text-white font-semibold text-sm">CityInspect AI</span>
          <span className="text-slate-500 text-xs">powered by Claude</span>
        </div>
        <div className="text-slate-500 text-xs mt-0.5">נתוני מערכת עדכניים · עיר: {cityId}</div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
        {messages.map((msg, i) => (
          <Message key={i} msg={msg} />
        ))}
        {error && (
          <div className="bg-red-950 border border-red-700 text-red-300 text-xs rounded-xl px-3 py-2">
            ❌ {error}
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Suggestions */}
      {messages.length <= 1 && (
        <div className="px-4 pb-2 flex flex-wrap gap-1.5 shrink-0">
          {SUGGESTED.map(s => (
            <button
              key={s}
              onClick={() => send(s)}
              disabled={loading}
              className="text-xs bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 px-3 py-1.5 rounded-full transition-colors disabled:opacity-50"
            >
              {s}
            </button>
          ))}
        </div>
      )}

      {/* Input */}
      <div className="px-4 py-3 border-t border-slate-800 bg-slate-900 shrink-0">
        <div className="flex gap-2 items-end">
          <textarea
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="שאל שאלה על המערכת..."
            rows={1}
            disabled={loading}
            className="flex-1 bg-slate-800 border border-slate-600 rounded-xl px-4 py-2.5 text-white text-sm placeholder-slate-500 focus:outline-none focus:border-purple-500 transition-colors resize-none disabled:opacity-50"
            style={{ direction: 'rtl', maxHeight: '120px', overflowY: 'auto' }}
          />
          <button
            onClick={() => send()}
            disabled={loading || !input.trim()}
            className="bg-purple-600 hover:bg-purple-500 disabled:opacity-40 text-white w-10 h-10 rounded-xl flex items-center justify-center shrink-0 transition-colors"
          >
            {loading ? (
              <span className="animate-spin text-sm">⚙️</span>
            ) : (
              <span>↑</span>
            )}
          </button>
        </div>
        <div className="text-slate-600 text-xs mt-1">Enter לשליחה · Shift+Enter לשורה חדשה</div>
      </div>
    </div>
  );
}
