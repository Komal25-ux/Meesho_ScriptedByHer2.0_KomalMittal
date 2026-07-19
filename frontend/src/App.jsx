import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import confetti from 'canvas-confetti';
import {
  MessageSquare,
  User,
  Layers,
  RefreshCcw,
  HelpCircle,
  HelpCircle as QuestionIcon,
  ChevronRight,
  TrendingDown
} from 'lucide-react';
import MessageBubble from './components/chat/MessageBubble';
import ChatInputBar from './components/chat/ChatInputBar';
import NotificationBell from './components/chat/NotificationBell';
import TerminalTraceLog from './components/dashboard/TerminalTraceLog';
import CatalogDashboard from './components/dashboard/CatalogDashboard';
import GrowthDashboard from './components/dashboard/GrowthDashboard';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const WS_BASE_URL = API_BASE_URL.replace(/^http/, 'ws');

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

  // Reseller-side Notification Bell - bridges the Customer segment's
  // terminal outcomes (order confirmed, return/exchange handed off) into a
  // visible alert on the Reseller segment, since the two are otherwise
  // fully separate chat histories with no shared view.
  const [notifications, setNotifications] = useState([]);
  const [isNotifOpen, setIsNotifOpen] = useState(false);

  const markNotificationRead = (id) => {
    setNotifications((prev) => prev.map((n) => (n.id === id ? { ...n, read: true } : n)));
    setIsNotifOpen(false);
  };
  const [viewMode, setViewMode] = useState('chat'); // 'chat' or 'trace' on mobile
  const [activeTab, setActiveTab] = useState('logs'); // 'logs', 'sales', or 'catalog' on dashboard
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

  // Bridges a terminal Customer-segment outcome (order confirmed, or a
  // return/exchange handed off) into a Reseller-side Notification Bell alert -
  // only called for /chat/send responses received while in Customer mode.
  const notifyFromCustomerResponse = (data) => {
    if (data.purchase_intent_detected) {
      setNotifications((prev) => [
        {
          id: Date.now(),
          type: 'order',
          customer: 'Payal',
          product: data.confirmed_product_name || 'item',
          price: data.confirmed_product_price ?? '',
          read: false
        },
        ...prev
      ]);
    } else if (data.handoff_triggered) {
      setNotifications((prev) => [
        { id: Date.now(), type: 'handoff', customer: 'Payal', read: false },
        ...prev
      ]);
    }
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

  // Text message send handler. Accepts an optional overrideText so a
  // ProductGrid tap (see handleSelectProduct) can send an exact product name
  // as if the user had typed and sent it themselves, without touching the
  // textInput box.
  const handleSendMessage = async (overrideText) => {
    const msg = (overrideText ?? textInput).trim();
    if (!msg || isLoading) return;
    if (overrideText === undefined) setTextInput('');
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
        product_options: data.product_options,
        voice_fallback: data.voice_fallback
      }]);
      broadcastListingToCustomers(data);
      if (activeMode === 'customer') notifyFromCustomerResponse(data);
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
          product_options: data.product_options,
          voice_fallback: data.voice_fallback
        }];
      });
      broadcastListingToCustomers(data);
      if (activeMode === 'customer') notifyFromCustomerResponse(data);
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
            
            <div className="flex items-center space-x-1">
              {/* Reseller-only: alerts for order confirmations / return handoffs
                  arriving from the Customer segment */}
              {activeMode === 'reseller' && (
                <NotificationBell
                  notifications={notifications}
                  isOpen={isNotifOpen}
                  onToggle={() => setIsNotifOpen((prev) => !prev)}
                  onMarkRead={markNotificationRead}
                />
              )}

              {/* Reset chat */}
              <button
                onClick={() => loadGreeting(activeMode)}
                className="text-meesho-jamuni hover:text-meesho-pink border border-transparent p-1.5 rounded-full hover:bg-white transition active:translate-y-[1px]"
                title="Reset Conversation"
              >
                <RefreshCcw className="w-4 h-4" />
              </button>
            </div>
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

          {/* Quick Uses Shortcuts Panel (mode-conditional). Two explicit flex
              groups + justify-between (rather than ml-auto on the nav-button
              group) - space-x-*'s generated `margin-left` selector and a
              plain ml-auto class have colliding specificity in Tailwind, so
              ml-auto wasn't reliably winning and the nav buttons sat short
              of the right edge instead of flush against it. */}
          <div className="bg-meesho-light p-2.5 border-b border-meesho-dark flex items-center justify-between overflow-x-auto text-[11px] gap-2">
            <div className="flex items-center space-x-2 shrink-0">
              <span className="font-bold text-meesho-dark whitespace-nowrap">Uses:</span>
              {activeMode === 'reseller' ? (
                <>
                  <button
                    onClick={() => triggerDemo("saree list krdo")}
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
                <button
                  onClick={() => triggerDemo("laal saree dikha do")}
                  className="bg-meesho-white border border-meesho-dark px-2.5 py-1 rounded-full whitespace-nowrap hover:bg-meesho-aam hover:text-white"
                >
                  Customer Qs
                </button>
              )}
            </div>

            {/* Cross-segment navigation: switches the right dashboard
                panel's active tab without sending a chat message. */}
            {activeMode === 'reseller' && (
              <div className="flex items-center space-x-2 shrink-0">
                <button
                  onClick={() => { setActiveTab('sales'); setViewMode('trace'); }}
                  className="border-[1.5px] border-gray-300 text-[#1E1E24] hover:bg-[#F7F7FA] rounded-[0.5rem] px-3 py-1.5 text-xs font-['Roboto_Slab',_serif] font-medium whitespace-nowrap transition"
                >
                  📊 View Growth
                </button>
                <button
                  onClick={() => { setActiveTab('catalog'); setViewMode('trace'); }}
                  className="border-[1.5px] border-gray-300 text-[#1E1E24] hover:bg-[#F7F7FA] rounded-[0.5rem] px-3 py-1.5 text-xs font-['Roboto_Slab',_serif] font-medium whitespace-nowrap transition"
                >
                  📦 Catalog
                </button>
              </div>
            )}
          </div>

          {/* Scrollable messages zone */}
          <div className="flex-1 p-4 overflow-y-auto bg-slate-50 space-y-4">
            {currentMessages.map((msg, index) => (
              <MessageBubble key={index} message={msg} onSelectProduct={handleSendMessage} />
            ))}
            <div ref={chatEndRef} />
          </div>

          {/* WhatsApp-style unified input: single mic/send action button */}
          <ChatInputBar
            textInput={textInput}
            setTextInput={setTextInput}
            onSendMessage={() => handleSendMessage()}
            onSendAudio={handleSendAudio}
            isLoading={isLoading}
          />
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
          {/* System event trigger - simulates a backend event (e.g. a return
              initiated in the reseller's Meesho seller dashboard) making Sakhi
              proactively message the customer, unprompted. Top-most element
              in this panel, ahead of the tab navigation below it. */}
          <div className="shrink-0 px-4 pt-3 mb-4">
            <button
              onClick={triggerSystemReturnEvent}
              disabled={isTriggeringReturn}
              title="Simulates a backend event (e.g. a return logged in the seller dashboard) - Sakhi to Customer, unprompted"
              className="w-full bg-meesho-jamuni text-meesho-white border border-meesho-dark py-2 rounded-lg text-xs font-bold hover:bg-opacity-90 transition active:translate-y-[1px] disabled:opacity-50"
            >
              {isTriggeringReturn ? 'Triggering...' : '🔔 Sakhi Reaches Out: Return Alert'}
            </button>
          </div>

          {/* Tabs header - edge-to-edge, directly below the return-alert button */}
          <div className="shrink-0 flex border-b border-meesho-dark">
            <button
              onClick={() => setActiveTab('logs')}
              className={`flex-1 py-3 text-xs font-bold transition ${
                activeTab === 'logs'
                  ? 'bg-meesho-jamuni text-meesho-white'
                  : 'bg-meesho-white text-meesho-dark hover:bg-meesho-light'
              }`}
            >
              Orchestrator’s Brain 🧠
            </button>
            <button
              onClick={() => setActiveTab('sales')}
              className={`flex-1 py-3 text-xs font-bold transition border-l border-meesho-dark ${
                activeTab === 'sales'
                  ? 'bg-meesho-jamuni text-meesho-white'
                  : 'bg-meesho-white text-meesho-dark hover:bg-meesho-light'
              }`}
            >
              Growth Analysis
            </button>
            <button
              onClick={() => setActiveTab('catalog')}
              className={`flex-1 py-3 text-xs font-bold transition border-l border-meesho-dark ${
                activeTab === 'catalog'
                  ? 'bg-meesho-jamuni text-meesho-white'
                  : 'bg-meesho-white text-meesho-dark hover:bg-meesho-light'
              }`}
            >
              Catalog
            </button>
          </div>

          {/* Output area - the panel itself is edge-to-edge, but the log/chart
              boxes inside keep their curved, floating card aesthetic via this
              padded wrapper */}
          <div className="flex-1 min-h-0 p-4">
            {activeTab === 'logs' ? (
              <div className="h-full">
                <TerminalTraceLog logs={traceLogs} onClear={() => setTraceLogs([])} />
              </div>
            ) : activeTab === 'catalog' ? (
              <CatalogDashboard />
            ) : (
              <GrowthDashboard />
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
