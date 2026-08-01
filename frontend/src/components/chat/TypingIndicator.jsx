import React from 'react';
import { Sparkles } from 'lucide-react';

// Shown in place of Sakhi's reply bubble while a request is in flight. Voice
// turns go through a much longer pipeline (upload -> ffmpeg -> Sarvam ASR ->
// Gemini -> Sarvam TTS) than text turns, so the label is kind-specific rather
// than a single generic "loading" string - a silent multi-second gap reads as
// broken to a user who can't fall back to reading an error message.
export default function TypingIndicator({ kind = 'text' }) {
  const label = kind === 'voice' ? 'Sakhi aapki awaaz samajh rahi hai...' : 'Sakhi soch rahi hai...';

  return (
    <div className="flex w-full justify-start mb-4">
      <div className="max-w-[85%] sm:max-w-[70%] rounded-xl p-4 border border-meesho-dark relative bg-meesho-light text-meesho-dark stitch-border shadow-tactile">
        <div className="absolute top-1 right-2 flex space-x-1 items-center">
          <Sparkles className="w-3.5 h-3.5 text-meesho-pink" />
          <span className="text-[9px] font-mono text-meesho-pink">SAKHI</span>
        </div>

        <div className="flex items-center space-x-2 pr-4">
          <span className="text-sm text-meesho-dark/80">{label}</span>
          <span className="flex items-center space-x-1" aria-hidden="true">
            <span className="w-1.5 h-1.5 bg-meesho-jamuni rounded-full animate-bounce [animation-delay:-0.3s]" />
            <span className="w-1.5 h-1.5 bg-meesho-jamuni rounded-full animate-bounce [animation-delay:-0.15s]" />
            <span className="w-1.5 h-1.5 bg-meesho-jamuni rounded-full animate-bounce" />
          </span>
        </div>
      </div>
    </div>
  );
}
