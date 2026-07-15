import React, { useEffect, useRef } from 'react';
import { Terminal, Activity, Clock, Server } from 'lucide-react';

export default function AgentTraceLog({ logs, onClear }) {
  const scrollRef = useRef(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs]);

  // Calculate stats
  const averageLatency = logs.length > 0 
    ? Math.round(logs.reduce((sum, item) => sum + (item.latency_ms || 0), 0) / logs.length) 
    : 0;

  return (
    <div className="h-full flex flex-col border border-meesho-dark rounded-xl bg-meesho-dark text-meesho-white shadow-tactile overflow-hidden font-mono">
      {/* Panel Header */}
      <div className="bg-[#15151a] border-b border-meesho-dark p-3 flex justify-between items-center">
        <div className="flex items-center space-x-2">
          <Terminal className="w-4 h-4 text-meesho-aam" />
          <span className="text-xs font-bold text-meesho-white">Judge Trace Analytics Dashboard</span>
        </div>
        <button
          onClick={onClear}
          className="text-[10px] bg-meesho-pink text-meesho-white hover:bg-meesho-jamuni border border-meesho-dark px-2 py-0.5 rounded transition active:translate-y-[1px]"
        >
          Clear Logs
        </button>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-3 bg-[#111115] border-b border-meesho-dark p-3 text-center">
        <div className="border-r border-meesho-dark/50 flex flex-col justify-center items-center">
          <Activity className="w-4 h-4 text-meesho-teal mb-1" />
          <span className="text-[9px] uppercase text-gray-400">Total Steps</span>
          <span className="text-sm font-bold text-meesho-teal">{logs.length}</span>
        </div>
        <div className="border-r border-meesho-dark/50 flex flex-col justify-center items-center">
          <Clock className="w-4 h-4 text-meesho-pink mb-1" />
          <span className="text-[9px] uppercase text-gray-400">Avg Latency</span>
          <span className="text-sm font-bold text-meesho-pink">{averageLatency}ms</span>
        </div>
        <div className="flex flex-col justify-center items-center">
          <Server className="w-4 h-4 text-[#ffc658] mb-1" />
          <span className="text-[9px] uppercase text-gray-400">LangGraph Status</span>
          <span className="text-[11px] font-bold text-green-400">RUNNING</span>
        </div>
      </div>

      {/* Scrollable Trace Logging Area */}
      <div ref={scrollRef} className="flex-1 p-3 overflow-y-auto space-y-3 bg-[#0d0d10] text-[11px]">
        {logs.length === 0 ? (
          <div className="h-full flex flex-col justify-center items-center text-gray-500 py-10">
            <Terminal className="w-8 h-8 mb-2 opacity-30 text-meesho-pink animate-pulse" />
            <span>Awaiting LangGraph multi-agent events...</span>
            <span className="text-[9px] text-gray-600 mt-1">Speak into the microphone to trigger agent logs</span>
          </div>
        ) : (
          logs.map((log, index) => {
            const isOrchestrator = log.agent === 'Orchestrator';
            const latencyColor = log.latency_ms > 1000 ? 'text-red-400' : 'text-green-400';
            
            return (
              <div key={index} className="border-b border-meesho-dark/30 pb-2.5 last:border-b-0">
                <div className="flex justify-between items-center text-gray-400 text-[10px] mb-1">
                  <span className="text-meesho-aam font-bold">[{log.agent}]</span>
                  <span>{log.timestamp}</span>
                </div>
                
                <div className="flex justify-between items-center mb-1.5">
                  <span className="text-meesho-white font-bold">{log.action}</span>
                  <span className={`${latencyColor}`}>{log.latency_ms}ms</span>
                </div>

                {log.data && (
                  <pre className="bg-[#171720] border border-meesho-dark/50 p-2 rounded text-gray-300 overflow-x-auto text-[10px] max-h-36">
                    {JSON.stringify(log.data, null, 2)}
                  </pre>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
