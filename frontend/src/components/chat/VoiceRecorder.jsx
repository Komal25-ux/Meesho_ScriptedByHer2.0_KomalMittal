import React, { useState, useRef } from 'react';
import { Mic, Square, Loader } from 'lucide-react';

export default function VoiceRecorder({ onSendAudio, isLoading }) {
  const [isRecording, setIsRecording] = useState(false);
  const [stream, setStream] = useState(null);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);

  const startRecording = async () => {
    try {
      audioChunksRef.current = [];
      const mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      setStream(mediaStream);

      const mediaRecorder = new MediaRecorder(mediaStream);
      mediaRecorderRef.current = mediaRecorder;

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        onSendAudio(audioBlob);
      };

      mediaRecorder.start();
      setIsRecording(true);
    } catch (err) {
      console.error("Error accessing microphone:", err);
      alert("Microphone permission are required to send voice notes.");
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
      
      // Stop all audio tracks to release microphone
      if (stream) {
        stream.getTracks().forEach((track) => track.stop());
        setStream(null);
      }
    }
  };

  return (
    <div className="flex flex-col items-center justify-center p-3 border-t border-meesho-dark bg-meesho-white">
      {isRecording && (
        <div className="flex items-center space-x-2 mb-3">
          <span className="w-2.5 h-2.5 bg-red-500 rounded-full animate-ping"></span>
          <span className="text-xs font-mono text-meesho-dark">Sunita Didi, bolte rahiye...</span>
        </div>
      )}
      
      <div className="flex space-x-4 w-full">
        {isRecording ? (
          <button
            onClick={stopRecording}
            className="flex-1 bg-red-500 text-meesho-white border border-meesho-dark py-3.5 px-6 rounded-lg text-sm flex items-center justify-center space-x-2 transition duration-150 shadow-tactile active:translate-y-[1px]"
          >
            <Square className="w-4 h-4 fill-white" />
            <span className="font-bold">Baat Rokien</span>
          </button>
        ) : (
          <button
            onClick={startRecording}
            disabled={isLoading}
            className={`flex-1 ${
              isLoading ? 'bg-meesho-light text-gray-400 cursor-not-allowed' : 'bg-meesho-aam text-meesho-white'
            } border border-meesho-dark py-3.5 px-6 rounded-lg text-sm flex items-center justify-center space-x-2 transition duration-150 shadow-tactile active:translate-y-[1px]`}
          >
            {isLoading ? (
              <>
                <Loader className="w-4 h-4 animate-spin text-meesho-jamuni" />
                <span>Sakhi soch rahi hai...</span>
              </>
            ) : (
              <>
                <Mic className="w-4 h-4 text-meesho-white" />
                <span className="font-bold">Daba kar bolein (Hindi Voice)</span>
              </>
            )}
          </button>
        )}
      </div>
    </div>
  );
}
