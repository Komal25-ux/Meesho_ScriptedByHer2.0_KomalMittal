import React, { useEffect, useRef, useState, memo } from 'react';

// Ticking cadence for the typewriter. Kept fast (a real terminal boot log
// feel, not a slow dramatic reveal) since WS trace events can arrive in
// quick bursts during a single LangGraph turn (5-8 events per /chat/send).
const TICK_MS = 16;
const BASE_CHARS_PER_TICK = 2;
// If the queue backs up past this many pending lines, speed-read the rest
// instead of falling further behind - this is what keeps the animation from
// ever visibly lagging the live WebSocket stream.
const CATCH_UP_QUEUE_THRESHOLD = 6;
const CATCH_UP_CHARS_PER_TICK = 14;
// Bound the rendered history so a long demo session doesn't grow the DOM
// unboundedly - this is a terminal scrollback, not a permanent log.
const MAX_COMPLETED_LINES = 300;

/**
 * Translates one raw WebSocket trace_log payload ({agent, action,
 * latency_ms, data, timestamp}) into one or more terminal lines. Grounded in
 * the actual agent/action strings backend/core/orchestrator.py and
 * chat_router.py broadcast - see the exhaustive if/else below - with a
 * generic fallback for anything not explicitly mapped, so an unmapped future
 * event never disappears silently.
 *
 * Two bookend lines (LANGGRAPH_ORCHESTRATOR init, FRONTEND_RENDER dispatch)
 * are synthesized here rather than invented from nothing: Memory Retrieval
 * is always the graph's first node and Assemble Final Response is always
 * its last, so their arrival is a reliable, real signal for "a turn just
 * started" / "a turn just finished" - not a fabricated event.
 */
function mapLogToLines(log) {
  const agent = log.agent || 'SYSTEM';
  const action = log.action || '';
  const data = log.data || {};
  const lines = [];
  const push = (text, category) => lines.push({ text, category });

  if (agent === 'Orchestrator' && action === 'Memory Retrieval') {
    push('> INIT: LANGGRAPH_ORCHESTRATOR', 'system');
    push('> ORCHESTRATOR.THINKING: Loading Memory & Checking Session State...', 'agent');
  } else if (agent === 'Orchestrator' && action === 'Pending Catalog Approval Check') {
    push('> ORCHESTRATOR.THINKING: Checking Pending Catalog Approval...', 'agent');
  } else if (agent === 'Orchestrator' && action === 'Pending Product Selection Check') {
    push('> ORCHESTRATOR.THINKING: Resolving ProductGrid Selection...', 'agent');
  } else if (agent === 'Orchestrator' && action === 'Intent Routing') {
    const intent = String(data.detected_intent || 'GENERAL').toUpperCase();
    push(`> ROUTE: ${intent}_AGENT`, 'system');
  } else if (agent === 'Orchestrator' && action === 'Assemble Final Response') {
    push('> ASSEMBLY: Packaging Final JSON + SARVAM_TTS', 'system');
    push('> DISPATCH: FRONTEND_RENDER', 'system');
  } else if (agent === 'CatalogAgent' && action === 'Draft Ready - Awaiting Approval') {
    push('> AGENT.CATALOG: Drafting WhatsApp Caption via Gemini...', 'agent');
  } else if (agent === 'CatalogAgent' && action === 'Finalize Listing - No Pending Draft') {
    push('> AGENT.CATALOG: Finalize Failed - No Pending Draft', 'agent');
  } else if (agent === 'CatalogAgent' && action === 'Listing Finalized (Post-Approval)') {
    push('> AGENT.CATALOG: Listing Finalized -> Broadcasting to Customer', 'agent');
  } else if (agent === 'CustomerAgent' && action === 'RAG Customer Search') {
    push('> CALL: SUPABASE_DB -> pgvector Similarity Search', 'system');
    push('> AGENT.CUSTOMER: Grounding Response in Retrieved Context...', 'agent');
  } else if (agent === 'CustomerAgent' && action === 'order_placed') {
    push('> AGENT.CUSTOMER: Purchase Confirmed -> Notifying Reseller', 'agent');
  } else if (action === 'Multiple SKU Matches - Awaiting Selection') {
    // Shared by CatalogAgent (reseller listing) and CustomerAgent (buyer
    // browsing) - same underlying event, different wording per side.
    const who = agent === 'CatalogAgent' ? 'CATALOG' : 'CUSTOMER';
    push('> CALL: SUPABASE_DB -> pgvector Similarity Search (Ambiguous)', 'system');
    push(`> AGENT.${who}: Awaiting ProductGrid Selection...`, 'agent');
  } else if (agent === 'ReturnsAgent' && action.startsWith('Returns Retention Funnel')) {
    const stage = action.replace('Returns Retention Funnel - ', '');
    push(`> AGENT.RETURNS: ${stage}`, 'agent');
    if (data.terminal) {
      push('> DISPATCH: HANDOFF -> Reseller', 'system');
    }
  } else if (agent === 'ReturnsAgent' && action === 'Proactive Return Outreach (System Triggered)') {
    push('> RECV: SYSTEM_WEBHOOK -> Return Initiated', 'system');
    push('> DISPATCH: PROACTIVE_OUTREACH -> Customer Segment', 'system');
  } else if (agent === 'GrowthAgent') {
    push('> AGENT.GROWTH: Analyzing Weekly Metrics via Gemini...', 'agent');
  } else if (agent === 'GeneralAgent') {
    push('> AGENT.GENERAL: Generating Greeting Response...', 'agent');
  } else {
    // Generic fallback - keeps any future/unmapped event visible instead of
    // silently dropping it.
    push(`> ${String(agent).toUpperCase()}: ${action}`, 'default');
  }

  push(`> STATUS: ${action || 'event'} completed in ${log.latency_ms ?? 0}ms`, 'system');
  return lines;
}

const CATEGORY_CLASS = {
  system: 'text-white',
  agent: 'text-yellow-400',
  default: 'text-gray-400'
};

const LogLine = memo(function LogLine({ text, category }) {
  return <div className={`whitespace-pre-wrap break-words ${CATEGORY_CLASS[category] || CATEGORY_CLASS.default}`}>{text}</div>;
});

export default function TerminalTraceLog({ logs, onClear }) {
  const [completedLines, setCompletedLines] = useState([]);
  const [typedText, setTypedText] = useState('');
  const [typedCategory, setTypedCategory] = useState('default');

  const containerRef = useRef(null);
  const queueRef = useRef([]); // lines waiting to be typed - a ref, not state, so enqueueing never triggers a render
  const activeLineRef = useRef(null); // { text, category } currently being typed
  const charIndexRef = useRef(0);
  const seenLogCountRef = useRef(0); // how many entries of `logs` have already been enqueued
  const lineIdRef = useRef(0);

  // Ingest new WS events into the queue as they arrive. Reads `logs` (an
  // ever-growing array from App.jsx's WebSocket listener) but only enqueues
  // the slice this component hasn't seen yet, so re-renders never re-type
  // history. If `logs` shrinks (the parent's "Clear Logs" cleared traceLogs
  // upstream), reset the watermark instead of erroring on a negative slice.
  useEffect(() => {
    if (logs.length < seenLogCountRef.current) {
      seenLogCountRef.current = 0;
    }
    const newLogs = logs.slice(seenLogCountRef.current);
    if (newLogs.length > 0) {
      for (const log of newLogs) {
        queueRef.current.push(...mapLogToLines(log));
      }
      seenLogCountRef.current = logs.length;
    }
  }, [logs]);

  // The typewriter loop itself. Runs once; all fast-changing progress state
  // lives in refs so this interval never needs to be torn down/recreated,
  // and only the two small state values that actually affect rendering
  // (typedText, typedCategory) are touched per tick - completedLines only
  // updates once per finished line, not once per character.
  useEffect(() => {
    const interval = setInterval(() => {
      if (!activeLineRef.current) {
        const next = queueRef.current.shift();
        if (!next) return; // idle - nothing queued
        activeLineRef.current = next;
        charIndexRef.current = 0;
        setTypedCategory(next.category);
      }

      const charsPerTick = queueRef.current.length > CATCH_UP_QUEUE_THRESHOLD
        ? CATCH_UP_CHARS_PER_TICK
        : BASE_CHARS_PER_TICK;
      charIndexRef.current = Math.min(
        charIndexRef.current + charsPerTick,
        activeLineRef.current.text.length
      );
      setTypedText(activeLineRef.current.text.slice(0, charIndexRef.current));

      if (charIndexRef.current >= activeLineRef.current.text.length) {
        const finished = activeLineRef.current;
        lineIdRef.current += 1;
        setCompletedLines((prev) => {
          const updated = [...prev, { id: lineIdRef.current, text: finished.text, category: finished.category }];
          return updated.length > MAX_COMPLETED_LINES
            ? updated.slice(updated.length - MAX_COMPLETED_LINES)
            : updated;
        });
        activeLineRef.current = null;
        setTypedText('');
      }
    }, TICK_MS);

    return () => clearInterval(interval);
  }, []);

  // Auto-scroll on every completed line AND every character typed.
  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [completedLines, typedText]);

  const handleClear = () => {
    queueRef.current = [];
    activeLineRef.current = null;
    charIndexRef.current = 0;
    seenLogCountRef.current = 0;
    setCompletedLines([]);
    setTypedText('');
    onClear?.();
  };

  const isIdle = completedLines.length === 0 && !typedText;

  return (
    <div className="h-full flex flex-col border border-meesho-dark rounded-xl bg-black text-gray-400 shadow-tactile overflow-hidden font-['JetBrains_Mono',_monospace]">
      <div className="bg-[#15151a] border-b border-meesho-dark p-3 flex justify-between items-center shrink-0">
        <span className="text-xs font-bold text-white">Orchestrator’s Brain 🧠</span>
        <button
          onClick={handleClear}
          className="text-[10px] bg-meesho-pink text-white hover:bg-meesho-jamuni border border-meesho-dark px-2 py-0.5 rounded transition active:translate-y-[1px]"
        >
          Clear Logs
        </button>
      </div>

      <div ref={containerRef} className="bg-black p-4 h-full overflow-y-auto w-full text-[12px] leading-relaxed">
        {isIdle ? (
          <div className="h-full flex flex-col justify-center items-center text-gray-600 py-10">
            <span>Awaiting LangGraph multi-agent events...</span>
            <span className="text-[10px] mt-1">Speak or type into the chat to trigger agent logs</span>
          </div>
        ) : (
          <>
            {completedLines.map((line) => (
              <LogLine key={line.id} text={line.text} category={line.category} />
            ))}
            {typedText && (
              <div className={CATEGORY_CLASS[typedCategory] || CATEGORY_CLASS.default}>
                {typedText}
                <span className="animate-pulse">_</span>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
