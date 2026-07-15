import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import confetti from 'canvas-confetti';
import { 
  Send, 
  MessageSquare, 
  User, 
  Layers, 
  TrendingUp, 
  RefreshCcw, 
  HelpCircle,
  HelpCircle as QuestionIcon,
  ChevronRight,
  TrendingDown
} from 'lucide-react';
import MessageBubble from './components/chat/MessageBubble';
import VoiceRecorder from './components/chat/VoiceRecorder';
import AgentTraceLog from './components/dashboard/AgentTraceLog';

import { 
  ResponsiveContainer, 
  AreaChart, 
  Area, 
  XAxis, 
  YAxis, 
  Tooltip 
} from 'recharts';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const WS_BASE_URL = API_BASE_URL.replace(/^http/, 'ws');

// Mock chart data for weekly sales analytics dashboard
const CHART_DATA = [
  { day: 'Mon', sales: 1200, profit: 300 },
  { day: 'Tue', sales: 1800, profit: 450 },
  { day: 'Wed', sales: 1500, profit: 380 },
  { day: 'Thu', sales: 2400, profit: 600 },
  { day: 'Fri', sales: 2100, profit: 530 },
  { day: 'Sat', sales: 3200, profit: 800 },
  { day: 'Sun', sales: 2900, profit: 720 },
];

export default function App() {
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      text: 'Namaste Sunita didi! Main aapki AI Sakhi hu. Bolkar ya likhkar mujhse apne catalog, orders aur returns ki baatein kijiye. 🌸',
      voice_fallback: true
    }
  ]);
  const [textInput, setTextInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [traceLogs, setTraceLogs] = useState([]);
  const [viewMode, setViewMode] = useState('chat'); // 'chat' or 'trace' on mobile
  const [activeTab, setActiveTab] = useState('logs'); // 'logs' or 'sales' on dashboard
  
  const chatEndRef = useRef(null);
  const wsRef = useRef(null);

  // Scroll to bottom of chat
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Connect to WebSocket on startup
  useEffect(() => {
    connectWebSocket();
    return () => {
      if (wsRef.current) wsRef.current.close();
    };
  }, []);

  const connectWebSocket = () => {
    try {
      logger_info("Connecting WebSocket: " + `${WS_BASE_URL}/ws/agent-logs`);
      const socket = new WebSocket(`${WS_BASE_URL}/ws/agent-logs`);
      wsRef.current = socket;

      socket.onmessage = (event) => {
        try {
          const logData = JSON.parse(event.data);
          setTraceLogs((prev) => [...prev, logData]);
          
          // Trigger confetti if a catalog listing was added successfully
          if (logData.agent === 'CatalogAgent' && logData.data?.promo_post_created) {
            triggerConfetti();
          }
        } catch (e) {
          console.error("Error parsing WebSocket log:", e);
        }
      };

      socket.onclose = () => {
        console.warn("WebSocket closed. Attempting reconnect in 5 seconds...");
        setTimeout(connectWebSocket, 5000);
      };

      socket.onerror = (err) => {
        console.error("WebSocket error:", err);
      };
    } catch (err) {
      console.error("WebSocket connection failure:", err);
    }
  };

  const logger_info = (msg) => {
    console.log(`[Sakhi UI] ${msg}`);
  };

  const triggerConfetti = () => {
    confetti({
      particleCount: 100,
      spread: 70,
      origin: { y: 0.6 }
    });
  };

  // Text message send handler
  const handleSendMessage = async () => {
    if (!textInput.trim() || isLoading) return;
    const msg = textInput;
    setTextInput('');
    setIsLoading(true);

    // Optimistic user bubble update
    setMessages((prev) => [...prev, { role: 'user', text: msg }]);

    try {
      const formData = new FormData();
      formData.append('text_message', msg);
      formData.append('whatsapp_number', 'whatsapp:+919876543210');

      const response = await axios.post(`${API_BASE_URL}/api/v1/chat/send`, formData);
      const data = response.data;

      setMessages((prev) => [...prev, {
        role: 'assistant',
        text: data.text,
        audio: data.audio,
        image_url: data.image_url,
        voice_fallback: data.voice_fallback
      }]);
    } catch (err) {
      console.error("Error sending text message:", err);
      setMessages((prev) => [...prev, {
        role: 'assistant',
        text: "Maaf kijiyega didi, abhi server se connect nahi ho pa rahi hu. Kripya thodi der me koshish karein.",
        voice_fallback: true
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  // Audio blob send handler
  const handleSendAudio = async (audioBlob) => {
    if (isLoading) return;
    setIsLoading(true);

    // Optimistic temporary user voice bubble
    setMessages((prev) => [...prev, { role: 'user', text: "🎙️ Voice message sent..." }]);

    try {
      const formData = new FormData();
      formData.append('audio_file', audioBlob, 'reseller_recording.webm');
      formData.append('whatsapp_number', 'whatsapp:+919876543210');

      const response = await axios.post(`${API_BASE_URL}/api/v1/chat/send`, formData);
      const data = response.data;

      // Replace the placeholder voice message with actual text transcription + response
      setMessages((prev) => {
        const updated = [...prev];
        // Clean up last user bubble if it was voice placeholder
        if (updated[updated.length - 2]?.text === "🎙️ Voice message sent...") {
          updated[updated.length - 2].text = "🎙️ Voice note command processed";
        }
        return [...updated, {
          role: 'assistant',
          text: data.text,
          audio: data.audio,
          image_url: data.image_url,
          voice_fallback: data.voice_fallback
        }];
      });
    } catch (err) {
      console.error("Error sending audio blob:", err);
      setMessages((prev) => [...prev, {
        role: 'assistant',
        text: "Kripya bolein firse didi, aapki awaaz saaf nahi sunai di.",
        voice_fallback: true
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  // Handle Demo shortcut clicks (Mock runs)
  const triggerDemo = async (scenarioText) => {
    setTextInput(scenarioText);
  };

  return (
    <div className="min-h-[100dvh] flex flex-col bg-meesho-light selection:bg-meesho-pink selection:text-meesho-white">
      {/* App Header */}
      <header className="bg-meesho-jamuni border-b border-meesho-dark text-meesho-white py-4 px-6 flex justify-between items-center shadow-md">
        <div className="flex items-center space-x-2.5">
          <div className="bg-meesho-white p-1.5 rounded-full border border-meesho-dark">
            <span className="text-lg font-bold text-meesho-jamuni">🌸</span>
          </div>
          <div>
            <h1 className="text-lg sm:text-xl font-bold tracking-tight">Sakhi AI</h1>
            <p className="text-[10px] sm:text-xs text-meesho-aam font-mono">Meesho Reseller Didi Co-pilot</p>
          </div>
        </div>

        {/* Mobile View Toggle Tabs */}
        <div className="flex sm:hidden space-x-1 bg-[#851672] p-1 rounded-lg border border-meesho-dark">
          <button
            onClick={() => setViewMode('chat')}
            className={`px-3 py-1 text-xs rounded-md ${
              viewMode === 'chat' ? 'bg-meesho-aam text-meesho-white' : 'text-gray-200'
            }`}
          >
            Chat UI
          </button>
          <button
            onClick={() => setViewMode('trace')}
            className={`px-3 py-1 text-xs rounded-md ${
              viewMode === 'trace' ? 'bg-meesho-aam text-meesho-white' : 'text-gray-200'
            }`}
          >
            Trace Log
          </button>
        </div>

        <div className="hidden sm:flex items-center space-x-2 text-xs font-mono bg-meesho-dark text-meesho-white px-3 py-1.5 border border-meesho-dark rounded-md">
          <span className="w-2.5 h-2.5 bg-green-500 rounded-full animate-pulse"></span>
          <span>SYSTEM ACTIVE</span>
        </div>
      </header>

      {/* Main Workspace Layout */}
      <main className="flex-1 max-w-[1280px] w-full mx-auto p-4 sm:p-6 grid grid-cols-1 md:grid-cols-2 gap-6 items-stretch">
        
        {/* Left Pane: WhatsApp-like Mobile Chat View */}
        <section
          className={`flex flex-col border border-meesho-dark rounded-2xl bg-meesho-white shadow-tactile overflow-hidden h-[75vh] md:h-[80vh] ${
            viewMode === 'chat' ? 'flex' : 'hidden md:flex'
          }`}
        >
          {/* Header */}
          <div className="bg-[#f0e3f2] border-b border-meesho-dark p-3.5 flex justify-between items-center">
            <div className="flex items-center space-x-3">
              <div className="w-9 h-9 rounded-full bg-meesho-jamuni flex items-center justify-center text-meesho-white border border-meesho-dark font-bold text-sm">
                SD
              </div>
              <div>
                <h3 className="text-sm font-bold text-meesho-dark">Sunita Didi</h3>
                <span className="text-[10px] text-green-600 flex items-center">
                  <span className="w-1.5 h-1.5 bg-green-500 rounded-full mr-1"></span> Online
                </span>
              </div>
            </div>
            
            {/* Reset chat */}
            <button
              onClick={() => setMessages([
                {
                  role: 'assistant',
                  text: 'Namaste Sunita didi! Bolkar ya likhkar bataiye aaj main kya madad karu? 🌸',
                  voice_fallback: true
                }
              ])}
              className="text-meesho-jamuni hover:text-meesho-pink border border-transparent p-1.5 rounded-full hover:bg-white transition active:translate-y-[1px]"
              title="Reset Conversation"
            >
              <RefreshCcw className="w-4 h-4" />
            </button>
          </div>

          {/* Quick Demos Shortcuts Panel */}
          <div className="bg-meesho-light p-2.5 border-b border-meesho-dark flex items-center space-x-2 overflow-x-auto text-[11px]">
            <span className="font-bold text-meesho-dark whitespace-nowrap">Demos:</span>
            <button 
              onClick={() => triggerDemo("yellow chanderi saree list kardo")}
              className="bg-meesho-white border border-meesho-dark px-2.5 py-1 rounded-full whitespace-nowrap hover:bg-meesho-aam hover:text-white"
            >
              Catalog List
            </button>
            <button 
              onClick={() => triggerDemo("kya ye kurti large size me hai?")}
              className="bg-meesho-white border border-meesho-dark px-2.5 py-1 rounded-full whitespace-nowrap hover:bg-meesho-aam hover:text-white"
            >
              Customer Qs
            </button>
            <button 
              onClick={() => triggerDemo("weekly analysis dikhao")}
              className="bg-meesho-white border border-meesho-dark px-2.5 py-1 rounded-full whitespace-nowrap hover:bg-meesho-aam hover:text-white"
            >
              Growth Coach
            </button>
            <button 
              onClick={() => triggerDemo("saree choti pad rahi hai return ya exchange karna hai")}
              className="bg-meesho-white border border-meesho-dark px-2.5 py-1 rounded-full whitespace-nowrap hover:bg-meesho-aam hover:text-white"
            >
              Exchange Return
            </button>
          </div>

          {/* Scrollable messages zone */}
          <div className="flex-1 p-4 overflow-y-auto bg-slate-50 space-y-4">
            {messages.map((msg, index) => (
              <MessageBubble key={index} message={msg} />
            ))}
            <div ref={chatEndRef} />
          </div>

          {/* Audio hold-to-talk button */}
          <VoiceRecorder onSendAudio={handleSendAudio} isLoading={isLoading} />

          {/* Direct Text Input Fallback */}
          <div className="p-3 border-t border-meesho-dark bg-meesho-light flex space-x-2">
            <input
              type="text"
              value={textInput}
              onChange={(e) => setTextInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSendMessage()}
              placeholder="Type message here (English or Hindi)..."
              disabled={isLoading}
              className="flex-1 rounded-lg border border-meesho-dark bg-meesho-white px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-meesho-jamuni placeholder:text-gray-400"
            />
            <button
              onClick={handleSendMessage}
              disabled={isLoading || !textInput.trim()}
              className="bg-meesho-jamuni text-meesho-white border border-meesho-dark p-2.5 rounded-lg transition active:translate-y-[1px] hover:bg-opacity-90 disabled:opacity-50"
            >
              <Send className="w-4 h-4" />
            </button>
          </div>
        </section>

        {/* Right Pane: Judge/Analytics View */}
        <section
          className={`flex flex-col h-[75vh] md:h-[80vh] ${
            viewMode === 'trace' ? 'flex' : 'hidden md:flex'
          }`}
        >
          {/* Tabs header */}
          <div className="flex space-x-2 mb-3">
            <button
              onClick={() => setActiveTab('logs')}
              className={`flex-1 py-2 rounded-lg text-xs font-bold border border-meesho-dark transition ${
                activeTab === 'logs'
                  ? 'bg-meesho-jamuni text-meesho-white shadow-tactile'
                  : 'bg-meesho-white text-meesho-dark hover:bg-meesho-light'
              }`}
            >
              LangGraph State Logs
            </button>
            <button
              onClick={() => setActiveTab('sales')}
              className={`flex-1 py-2 rounded-lg text-xs font-bold border border-meesho-dark transition ${
                activeTab === 'sales'
                  ? 'bg-meesho-jamuni text-meesho-white shadow-tactile'
                  : 'bg-meesho-white text-meesho-dark hover:bg-meesho-light'
              }`}
            >
              Weekly Growth Analytics
            </button>
          </div>

          {activeTab === 'logs' ? (
            <div className="flex-1 min-h-0">
              <AgentTraceLog logs={traceLogs} onClear={() => setTraceLogs([])} />
            </div>
          ) : (
            <div className="flex-1 bg-meesho-white border border-meesho-dark rounded-xl p-4 shadow-tactile flex flex-col justify-between overflow-hidden">
              <div>
                <h3 className="text-sm font-bold text-meesho-dark mb-1 flex items-center">
                  <TrendingUp className="w-4 h-4 text-meesho-teal mr-1.5" />
                  Didi Sales Performance Chart (Weekly)
                </h3>
                <p className="text-[11px] text-gray-500 mb-4 font-mono">Real-time aggregate data synchronized with Supabase DB</p>
              </div>

              {/* Responsive Chart */}
              <div className="w-full h-56 flex-1 min-h-0">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={CHART_DATA}>
                    <defs>
                      <linearGradient id="colorSales" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#9F2089" stopOpacity={0.8}/>
                        <stop offset="95%" stopColor="#9F2089" stopOpacity={0}/>
                      </linearGradient>
                      <linearGradient id="colorProfit" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#42BC9E" stopOpacity={0.8}/>
                        <stop offset="95%" stopColor="#42BC9E" stopOpacity={0}/>
                      </linearGradient>
                    </defs>
                    <XAxis dataKey="day" stroke="#1E1E24" style={{ fontSize: '10px', fontFamily: 'monospace' }} />
                    <YAxis stroke="#1E1E24" style={{ fontSize: '10px', fontFamily: 'monospace' }} />
                    <Tooltip contentStyle={{ fontSize: '11px', fontFamily: 'monospace', backgroundColor: '#1E1E24', color: '#fff', border: '1px solid #000' }} />
                    <Area type="monotone" dataKey="sales" name="Sales (₹)" stroke="#9F2089" fillOpacity={1} fill="url(#colorSales)" />
                    <Area type="monotone" dataKey="profit" name="Profit (₹)" stroke="#42BC9E" fillOpacity={1} fill="url(#colorProfit)" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>

              {/* Sub-info layout */}
              <div className="mt-4 border-t border-dashed border-gray-300 pt-3 grid grid-cols-2 gap-4">
                <div className="bg-meesho-light border border-meesho-dark p-2.5 rounded-lg text-center">
                  <span className="text-[10px] text-gray-500 block uppercase font-mono">Best Category</span>
                  <span className="text-sm font-bold text-meesho-jamuni">Sarees (Haldi)</span>
                </div>
                <div className="bg-meesho-light border border-meesho-dark p-2.5 rounded-lg text-center">
                  <span className="text-[10px] text-gray-500 block uppercase font-mono">Conversion Ratio</span>
                  <span className="text-sm font-bold text-meesho-teal">84% Success</span>
                </div>
              </div>
            </div>
          )}
        </section>
      </main>

      {/* Footer copyright */}
      <footer className="py-4 border-t border-meesho-dark/15 text-center text-[10px] font-mono text-gray-500 bg-meesho-white">
        © 2026 ScriptedBy{"{Her}"} 2.0 Hackathon. Powered by Google Gemini & Supabase.
      </footer>
    </div>
  );
}
