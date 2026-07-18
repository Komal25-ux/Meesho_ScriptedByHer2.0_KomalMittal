import React, { useState } from 'react';
import { Volume2, VolumeX, Sparkles } from 'lucide-react';
import PricePatch from './PricePatch';
import ProductGrid from './ProductGrid';

export default function MessageBubble({ message, onSelectProduct }) {
  const { role, text, audio, image_url, price, product_options, voice_fallback } = message;
  const isUser = role === 'user';
  const [isPlaying, setIsPlaying] = useState(false);
  const [audioObj, setAudioObj] = useState(null);

  const handlePlayVoice = () => {
    if (isPlaying) {
      if (audioObj) {
        audioObj.pause();
        setIsPlaying(false);
      }
      return;
    }

    if (audio) {
      // Play Base64 Audio
      // Sarvam Bulbul returns raw WAV (RIFF/PCM), not mp3 - mislabeling this
      // caused playback artifacts/failures in stricter browsers.
      const snd = new Audio(`data:audio/wav;base64,${audio}`);
      setAudioObj(snd);
      setIsPlaying(true);
      snd.play();
      snd.onended = () => {
        setIsPlaying(false);
      };
    } else if (voice_fallback) {
      // Web Speech synthesis fallback
      setIsPlaying(true);
      const synth = window.speechSynthesis;
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = 'hi-IN';
      utterance.onend = () => {
        setIsPlaying(false);
      };
      utterance.onerror = () => {
        setIsPlaying(false);
      };
      synth.speak(utterance);
    }
  };

  return (
    <div className={`flex w-full ${isUser ? 'justify-end' : 'justify-start'} mb-4`}>
      <div
        className={`max-w-[85%] sm:max-w-[70%] rounded-xl p-4 border border-meesho-dark relative ${
          isUser
            ? 'bg-meesho-aam text-meesho-white shadow-tactile'
            : 'bg-meesho-light text-meesho-dark stitch-border shadow-tactile'
        }`}
      >
        {/* Thread highlight stitching effect */}
        {!isUser && (
          <div className="absolute top-1 right-2 flex space-x-1 items-center">
            <Sparkles className="w-3.5 h-3.5 text-meesho-pink" />
            <span className="text-[9px] font-mono text-meesho-pink">SAKHI</span>
          </div>
        )}

        {/* Message Text */}
        <p className="text-sm whitespace-pre-wrap leading-relaxed select-text pr-4">{text}</p>

        {/* Optional Image from Catalog agent - price is now rendered as a
            separate stitched patch below, instead of being baked into the
            image via AI generation. Capped to 65% of the bubble width (a
            ~35% reduction from the old full-width image) to cut scroll
            fatigue, left-aligned by default since it's a plain block child. */}
        {image_url && (
          <div className="mt-3 max-w-[65%] rounded-[0.5rem] overflow-hidden border border-meesho-dark shadow-tactile bg-meesho-white">
            <img src={image_url} alt="Product Creative" className="w-full h-auto object-cover" />
          </div>
        )}

        {image_url && price !== undefined && price !== null && (
          <div className="mt-2">
            <PricePatch price={price} />
          </div>
        )}

        {/* 2-4 ambiguous SKU matches - tapping one sends its exact name back
            as the next message (see App.jsx / orchestrator.py's
            check_pending_selection). */}
        {product_options && product_options.length > 0 && (
          <ProductGrid products={product_options} onSelect={onSelectProduct} />
        )}

        {/* Audio Player Control */}
        {(audio || voice_fallback) && !isUser && (
          <div className="mt-3 flex items-center border-t border-dashed border-meesho-dark/30 pt-2">
            <button
              onClick={handlePlayVoice}
              className="flex items-center space-x-2 bg-meesho-white text-meesho-jamuni hover:bg-meesho-jamuni hover:text-meesho-white border border-meesho-dark py-1 px-3 rounded-md text-xs transition duration-150 active:translate-y-[1px]"
            >
              {isPlaying ? (
                <>
                  <VolumeX className="w-3.5 h-3.5" />
                  <span>Awaaz Rokein</span>
                </>
              ) : (
                <>
                  <Volume2 className="w-3.5 h-3.5" />
                  <span>Awaaz Sunein</span>
                </>
              )}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
