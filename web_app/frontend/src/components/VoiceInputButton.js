import React, { useRef, useState } from 'react';

const VoiceInputButton = ({ onTranscription }) => {
  const [recording, setRecording] = useState(false);
  const [loading, setLoading] = useState(false);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);

  const handleStartRecording = async () => {
    setRecording(true);
    audioChunksRef.current = [];
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new window.MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          audioChunksRef.current.push(e.data);
        }
      };
      mediaRecorder.onstop = async () => {
        setLoading(true);
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        const formData = new FormData();
        formData.append('file', audioBlob, 'voice.webm');
        try {
          const res = await fetch('/api/voice-to-text', {
            method: 'POST',
            body: formData,
          });
          const data = await res.json();
          if (data.text && onTranscription) {
            onTranscription(data.text);
          }
        } catch (err) {
          alert('Voice transcription failed.');
        } finally {
          setLoading(false);
        }
      };
      mediaRecorder.start();
    } catch (err) {
      alert('Could not access microphone.');
      setRecording(false);
    }
  };

  const handleStopRecording = () => {
    setRecording(false);
    if (mediaRecorderRef.current) {
      mediaRecorderRef.current.stop();
      mediaRecorderRef.current.stream.getTracks().forEach(track => track.stop());
    }
  };

  return (
    <button
      onClick={recording ? handleStopRecording : handleStartRecording}
      disabled={loading}
      style={{
        marginLeft: 8,
        padding: '8px 12px',
        borderRadius: 20,
        border: 'none',
        background: recording ? '#ff5252' : '#222',
        color: '#fff',
        cursor: loading ? 'not-allowed' : 'pointer',
        fontWeight: 600,
        outline: 'none',
        minWidth: 40,
      }}
      title={recording ? 'Stop recording' : 'Start voice input'}
    >
      {loading ? '...' : recording ? '⏹️' : '🎤'}
    </button>
  );
};

export default VoiceInputButton; 