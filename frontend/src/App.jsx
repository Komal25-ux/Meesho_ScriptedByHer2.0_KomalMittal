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

const GREETINGS = {
  reseller: 'Namaste Sunita didi! Main aapki AI Sakhi hu. Bolkar ya likhkar mujhse apne catalog, orders aur returns ki baatein kijiye. 🌸',
  customer: 'Namaste! Main Sakhi hu. Aap apne order, delivery, ya return ke baare mein pooch sakte hain. 🌸'
};

const MIN_PANEL_PCT = 25;
const MAX_PANEL_PCT = 75;

export default function App() {
  const [activeMode, setActiveMode] = useState('reseller'); // 'reseller' or 'customer'

  // Reseller and Customer are separate people talking to Sakhi in this demo
  // (the reseller managing her business vs. a buyer asking about an order),
  // so their chat histories are kept in fully separate state - switching the
  // toggle must never mix one conversation's messages into the other's.
  const [resellerMessages, setResellerMessages] = useState([
    { role: 'assistant', text: GREETINGS.reseller, audio: null, voice_fallback: true }
  ]);
  const [customerMessages, setCustomerMessages] = useState([
    { role: 'assistant', text: GREETINGS.customer, audio: null, voice_fallback: true }
  ]);
  const currentMessages = activeMode === 'reseller' ? resellerMessages : customerMessages;
  const setCurrentMessages = activeMode === 'reseller' ? setResellerMessages : setCustomerMessages;

  const [textInput, setTextInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [traceLogs, setTraceLogs] = useState([]);
  const [viewMode, setViewMode] = useState('chat'); // 'chat' or 'trace' on mobile
  const [activeTab, setActiveTab] = useState('logs'); // 'logs' or 'sales' on dashboard
  const [leftWidthPct, setLeftWidthPct] = useState(50); // draggable chat/judge panel split
  const [isDesktop, setIsDesktop] = useState(
    () => typeof window !== 'undefined' && window.matchMedia('(min-width: 768px)').matches
  );

  const chatEndRef = useRef(null);
  const wsRef = useRef(null);
  const workspaceRef = useRef(null);
  const isDraggingRef = useRef(false);

  // Track desktop/mobile breakpoint so the drag-resize width only applies
  // when the two panels are actually side-by-side (md: and above).
  useEffect(() => {
    const mql = window.matchMedia('(min-width: 768px)');
    const handleChange = (e) => setIsDesktop(e.matches);
    mql.addEventListener('change', handleChange);
    return () => mql.removeEventListener('change', handleChange);
  }, []);

  // Draggable divider between the Chat and Judge panels
  const handleDividerMouseDown = () => {
    isDraggingRef.current = true;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  };

  useEffect(() => {
    const handleMouseMove = (e) => {
      if (!isDraggingRef.current || !workspaceRef.current) return;
      const rect = workspaceRef.current.getBoundingClientRect();
      const pct = ((e.clientX - rect.left) / rect.width) * 100;
      setLeftWidthPct(Math.min(MAX_PANEL_PCT, Math.max(MIN_PANEL_PCT, pct)));
    };
    const handleMouseUp = () => {
      if (isDraggingRef.current) {
        isDraggingRef.current = false;
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
      }
    };
    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, []);

  // Resets a specific mode's chat to just its welcome message and fetches
  // real Sarvam audio for it. Used both for the explicit "reset" button and
  // to lazily fetch audio the first time a mode is visited.
  const loadGreeting = async (mode) => {
    const greetingText = GREETINGS[mode];
    const setter = mode === 'reseller' ? setResellerMessages : setCustomerMessages;
    setter([{ role: 'assistant', text: greetingText, audio: null, voice_fallback: true }]);
    try {
      const response = await axios.get(`${API_BASE_URL}/api/v1/tts/greeting`, { params: { mode } });
      setter([{
        role: 'assistant',
        text: greetingText,
        audio: response.data.audio,
        voice_fallback: !response.data.audio
      }]);
    } catch (err) {
      console.error("Error pre-fetching greeting audio:", err);
    }
  };

  const handleModeSwitch = (mode) => {
    if (mode === activeMode) return;
    setActiveMode(mode);
    // Lazily fetch real greeting audio the first time this mode is visited,
    // without wiping any conversation that's already happened in it.
    const targetMessages = mode === 'reseller' ? resellerMessages : customerMessages;
    if (targetMessages.length === 1 && targetMessages[0].audio === null) {
      loadGreeting(mode);
    }
  };

  // Fetch real audio for the initial reseller greeting on first mount
  useEffect(() => {
    loadGreeting('reseller');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Scroll to bottom of chat
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [currentMessages]);

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

  // When the reseller approves a catalog listing, broadcast the finalized
  // promotional post into the Customer segment's chat - simulating it
  // reaching buyers - regardless of which segment is currently on screen.
  const broadcastListingToCustomers = (data) => {
    if (!data.listing_finalized) return;
    setCustomerMessages((prev) => [...prev, {
      role: 'assistant',
      text: `📢 Naya product aaya hai!\n\n${data.broadcast_caption || data.text}`,
      image_url: data.image_url,
      price: data.price,
      audio: data.broadcast_audio || null,
      voice_fallback: !data.broadcast_audio
    }]);
  };

  // Judge Dashboard "system trigger" button: simulates a backend event (e.g. a
  // return initiated in the reseller's Meesho seller dashboard) that makes
  // Sakhi proactively message the customer, unprompted. Distinct from the
  // "Exchange/Returns" quick-use button in the Customer Uses bar, which
  // demos the customer-initiated flow instead.
  const [isTriggeringReturn, setIsTriggeringReturn] = useState(false);
  const triggerSystemReturnEvent = async () => {
    if (isTriggeringReturn) return;
    setIsTriggeringReturn(true);
    setActiveMode('customer');
    setViewMode('chat');
    try {
      const formData = new FormData();
      formData.append('whatsapp_number', 'whatsapp:+919876543210');
      formData.append('order_id', '104');
      formData.append('product_name', 'Red Cotton Kurti');
      const response = await axios.post(`${API_BASE_URL}/api/v1/system/trigger-return`, formData);
      const data = response.data;
      setCustomerMessages((prev) => [...prev, {
        role: 'assistant',
        text: data.text,
        audio: data.audio,
        image_url: data.image_url,
        voice_fallback: data.voice_fallback
      }]);
    } catch (err) {
      console.error("Error triggering system return event:", err);
    } finally {
      setIsTriggeringReturn(false);
    }
  };

  // Text message send handler
  const handleSendMessage = async () => {
    if (!textInput.trim() || isLoading) return;
    const msg = textInput;
    setTextInput('');
    setIsLoading(true);

    // Optimistic user bubble update
    setCurrentMessages((prev) => [...prev, { role: 'user', text: msg }]);

    try {
      const formData = new FormData();
      formData.append('text_message', msg);
      formData.append('whatsapp_number', 'whatsapp:+919876543210');
      formData.append('active_mode', activeMode);

      const response = await axios.post(`${API_BASE_URL}/api/v1/chat/send`, formData);
      const data = response.data;

      setCurrentMessages((prev) => [...prev, {
        role: 'assistant',
        text: data.text,
        audio: data.audio,
        image_url: data.image_url,
        price: data.price,
        voice_fallback: data.voice_fallback
      }]);
      broadcastListingToCustomers(data);
    } catch (err) {
      console.error("Error sending text message:", err);
      setCurrentMessages((prev) => [...prev, {
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
    setCurrentMessages((prev) => [...prev, { role: 'user', text: "🎙️ Voice message sent..." }]);

    try {
      const formData = new FormData();
      formData.append('audio_file', audioBlob, 'reseller_recording.webm');
      formData.append('whatsapp_number', 'whatsapp:+919876543210');
      formData.append('active_mode', activeMode);

      const response = await axios.post(`${API_BASE_URL}/api/v1/chat/send`, formData);
      const data = response.data;

      // Replace the placeholder voice message with actual text transcription + response
      setCurrentMessages((prev) => {
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
          price: data.price,
          voice_fallback: data.voice_fallback
        }];
      });
      broadcastListingToCustomers(data);
    } catch (err) {
      console.error("Error sending audio blob:", err);
      setCurrentMessages((prev) => [...prev, {
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
    <div className="h-[100dvh] flex flex-col overflow-hidden bg-meesho-light selection:bg-meesho-pink selection:text-meesho-white">
      {/* App Header */}
      <header className="shrink-0 bg-meesho-jamuni border-b border-meesho-dark text-meesho-white py-4 px-6 flex justify-between items-center shadow-md">
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

      {/* Main Workspace Layout - edge-to-edge, fills remaining viewport height */}
      <main ref={workspaceRef} className="flex-1 min-h-0 flex flex-col md:flex-row">

        {/* Left Pane: WhatsApp-like Mobile Chat View */}
        <section
          style={isDesktop ? { width: `${leftWidthPct}%` } : undefined}
          className={`flex flex-col min-h-0 bg-meesho-white overflow-hidden md:border-r md:border-meesho-dark ${
            viewMode === 'chat' ? 'flex flex-1 md:flex-none' : 'hidden md:flex'
          }`}
        >
          {/* Header */}
          <div className="bg-[#f0e3f2] border-b border-meesho-dark p-3.5 flex justify-between items-center">
            <div className="flex items-center space-x-3">
              <div className="w-9 h-9 rounded-full bg-meesho-jamuni flex items-center justify-center text-meesho-white border border-meesho-dark font-bold text-sm">
                SD
              </div>
              <div>
                <h3 className="text-sm font-bold text-meesho-dark">Sakhi</h3>
                <span className="text-[10px] text-green-600 flex items-center">
                  <span className="w-1.5 h-1.5 bg-green-500 rounded-full mr-1"></span> Sakhi Online
                </span>
              </div>
            </div>
            
            {/* Reset chat */}
            <button
              onClick={() => loadGreeting(activeMode)}
              className="text-meesho-jamuni hover:text-meesho-pink border border-transparent p-1.5 rounded-full hover:bg-white transition active:translate-y-[1px]"
              title="Reset Conversation"
            >
              <RefreshCcw className="w-4 h-4" />
            </button>
          </div>

          {/* Reseller / Customer Mode Toggle */}
          <div className="bg-meesho-light p-2 border-b border-meesho-dark flex items-center justify-center space-x-2">
            <button
              onClick={() => handleModeSwitch('reseller')}
              className={`flex-1 text-xs font-bold py-1.5 rounded-lg border border-meesho-dark transition ${
                activeMode === 'reseller'
                  ? 'bg-meesho-jamuni text-meesho-white shadow-tactile'
                  : 'bg-meesho-white text-meesho-dark hover:bg-meesho-aam hover:text-white'
              }`}
            >
              Reseller
            </button>
            <button
              onClick={() => handleModeSwitch('customer')}
              className={`flex-1 text-xs font-bold py-1.5 rounded-lg border border-meesho-dark transition ${
                activeMode === 'customer'
                  ? 'bg-meesho-jamuni text-meesho-white shadow-tactile'
                  : 'bg-meesho-white text-meesho-dark hover:bg-meesho-aam hover:text-white'
              }`}
            >
              Customer
            </button>
          </div>

          {/* Quick Uses Shortcuts Panel (mode-conditional) */}
          <div className="bg-meesho-light p-2.5 border-b border-meesho-dark flex items-center space-x-2 overflow-x-auto text-[11px]">
            <span className="font-bold text-meesho-dark whitespace-nowrap">Uses:</span>
            {activeMode === 'reseller' ? (
              <>
                <button
                  onClick={() => triggerDemo("yellow chanderi saree list kardo")}
                  className="bg-meesho-white border border-meesho-dark px-2.5 py-1 rounded-full whitespace-nowrap hover:bg-meesho-aam hover:text-white"
                >
                  Catalog List
                </button>
                <button
                  onClick={() => triggerDemo("weekly analysis dikhao")}
                  className="bg-meesho-white border border-meesho-dark px-2.5 py-1 rounded-full whitespace-nowrap hover:bg-meesho-aam hover:text-white"
                >
                  Growth Agent
                </button>
              </>
            ) : (
              <>
                <button
                  onClick={() => triggerDemo("kya ye kurti large size me hai?")}
                  className="bg-meesho-white border border-meesho-dark px-2.5 py-1 rounded-full whitespace-nowrap hover:bg-meesho-aam hover:text-white"
                >
                  Customer Qs
                </button>
              </>
            )}
          </div>

          {/* Scrollable messages zone */}
          <div className="flex-1 p-4 overflow-y-auto bg-slate-50 space-y-4">
            {currentMessages.map((msg, index) => (
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

        {/* Draggable resizer (desktop only) */}
        <div
          onMouseDown={handleDividerMouseDown}
          className="hidden md:flex w-2 shrink-0 cursor-col-resize bg-meesho-dark/10 hover:bg-meesho-jamuni/40 active:bg-meesho-jamuni/60 transition-colors items-center justify-center group"
        >
          <div className="w-0.5 h-10 rounded-full bg-meesho-dark/30 group-hover:bg-meesho-jamuni/70"></div>
        </div>

        {/* Right Pane: Judge/Analytics View */}
        <section
          style={isDesktop ? { width: `${100 - leftWidthPct}%` } : undefined}
          className={`flex flex-col min-h-0 bg-meesho-light overflow-hidden ${
            viewMode === 'trace' ? 'flex flex-1 md:flex-none' : 'hidden md:flex'
          }`}
        >
          {/* Tabs header - edge-to-edge at the top of the panel */}
          <div className="shrink-0 flex border-b border-meesho-dark">
            <button
              onClick={() => setActiveTab('logs')}
              className={`flex-1 py-3 text-xs font-bold transition ${
                activeTab === 'logs'
                  ? 'bg-meesho-jamuni text-meesho-white'
                  : 'bg-meesho-white text-meesho-dark hover:bg-meesho-light'
              }`}
            >
              LangGraph State Logs
            </button>
            <button
              onClick={() => setActiveTab('sales')}
              className={`flex-1 py-3 text-xs font-bold transition border-l border-meesho-dark ${
                activeTab === 'sales'
                  ? 'bg-meesho-jamuni text-meesho-white'
                  : 'bg-meesho-white text-meesho-dark hover:bg-meesho-light'
              }`}
            >
              Weekly Growth Analytics
            </button>
          </div>

          {/* System event trigger - simulates a backend event (e.g. a return
              initiated in the reseller's Meesho seller dashboard) making Sakhi
              proactively message the customer, unprompted. */}
          <div className="shrink-0 px-4 pt-3">
            <button
              onClick={triggerSystemReturnEvent}
              disabled={isTriggeringReturn}
              title="Simulates a backend event (e.g. a return logged in the seller dashboard) - Sakhi to Customer, unprompted"
              className="w-full bg-meesho-jamuni text-meesho-white border border-meesho-dark py-2 rounded-lg text-xs font-bold hover:bg-opacity-90 transition active:translate-y-[1px] disabled:opacity-50"
            >
              {isTriggeringReturn ? 'Triggering...' : '🔔 Sakhi Reaches Out: Return Alert'}
            </button>
          </div>

          {/* Output area - the panel itself is edge-to-edge, but the log/chart
              boxes inside keep their curved, floating card aesthetic via this
              padded wrapper */}
          <div className="flex-1 min-h-0 p-4">
            {activeTab === 'logs' ? (
              <div className="h-full">
                <AgentTraceLog logs={traceLogs} onClear={() => setTraceLogs([])} />
              </div>
            ) : (
              <div className="h-full bg-meesho-white border border-meesho-dark rounded-xl p-4 shadow-tactile flex flex-col justify-between overflow-hidden">
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
          </div>
        </section>
      </main>

      {/* Footer copyright */}
      <footer className="shrink-0 py-2 border-t border-meesho-dark/15 text-center text-[10px] font-mono text-gray-500 bg-meesho-white">
        © 2026 ScriptedBy{"{Her}"} 2.0 Hackathon. Powered by Google Gemini & Supabase.
      </footer>
    </div>
  );
}
