import React, { useState, useRef } from 'react';
import { Mic, Square, Send, Loader2 } from 'lucide-react';

/**
 * WhatsApp-style unified input bar: a single action button that swaps
 * between mic (empty input -> record a voice note) and send (input has
 * text -> submit it), replacing the old full-width standalone "Bolne ke
 * liye dabayein" button and the separate text-input row.
 */
export default function ChatInputBar({ textInput, setTextInput, onSendMessage, onSendAudio, isLoading }) {
  const [isRecording, setIsRecording] = useState(false);
  const streamRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);

  const hasText = textInput.trim().length > 0;

  const startRecording = async () => {
    try {
      audioChunksRef.current = [];
      const mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = mediaStream;

      const mediaRecorder = new MediaRecorder(mediaStream);
      mediaRecorderRef.current = mediaRecorder;

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) audioChunksRef.current.push(event.data);
      };

      mediaRecorder.onstop = () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        onSendAudio(audioBlob);
      };

      mediaRecorder.start();
      setIsRecording(true);
    } catch (err) {
      console.error('Error accessing microphone:', err);
      alert('Microphone permission is required to send voice notes.');
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
      }
    }
  };

  const handleActionClick = () => {
    if (isRecording) {
      stopRecording();
    } else if (hasText) {
      onSendMessage();
    } else {
      startRecording();
    }
  };

  return (
    <div className="border-t border-meesho-dark bg-meesho-light">
      {isRecording && (
        <div className="flex items-center space-x-2 px-3 pt-2 text-xs font-mono text-meesho-dark">
          <span className="w-2.5 h-2.5 bg-red-500 rounded-full animate-ping"></span>
          <span>Sunita Didi, bolte rahiye...</span>
        </div>
      )}
      <div className="p-3 flex items-center space-x-2">
        <div className="relative flex-1">
          <input
            type="text"
            value={textInput}
            onChange={(e) => setTextInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && hasText && !isLoading && onSendMessage()}
            placeholder={isLoading ? 'Sakhi soch rhi hai...' : 'Type message here (English or Hindi)...'}
            disabled={isLoading || isRecording}
            className="w-full rounded-lg border border-meesho-dark bg-meesho-white px-3 py-2 pr-9 text-sm focus:outline-none focus:ring-1 focus:ring-meesho-jamuni placeholder:text-gray-400 disabled:opacity-60"
          />
          {isLoading && (
            <Loader2 className="w-4 h-4 animate-spin text-meesho-jamuni absolute right-3 top-1/2 -translate-y-1/2" />
          )}
        </div>
        <button
          onClick={handleActionClick}
          disabled={isLoading}
          title={isRecording ? 'Baat rokein' : hasText ? 'Send' : 'Record voice note'}
          className={`shrink-0 p-2.5 rounded-lg border border-meesho-dark transition active:translate-y-[1px] disabled:opacity-50 ${
            isRecording ? 'bg-red-500 text-white' : 'bg-meesho-jamuni text-meesho-white hover:bg-opacity-90'
          }`}
        >
          {isRecording ? (
            <Square className="w-4 h-4 fill-white" />
          ) : hasText ? (
            <Send className="w-4 h-4" />
          ) : (
            <Mic className="w-4 h-4" />
          )}
        </button>
      </div>
    </div>
  );
}
