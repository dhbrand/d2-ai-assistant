import React, { useState, useEffect, useRef } from 'react';
import {
  Box,
  TextField,
  Button,
  Paper,
  List,
  ListItem,
  ListItemText,
  CircularProgress,
} from '@mui/material';
import { useAuth } from '../contexts/AuthContext';
import AdvancedMarkdownRenderer from '../components/AdvancedMarkdownRenderer';
import VoiceInputButton from '../components/VoiceInputButton';

function ChatPage() {
  const { token } = useAuth();
  const [messages, setMessages] = useState([]);
  const [newMessage, setNewMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [showScrollButton, setShowScrollButton] = useState(false);
  const [previousResponseId, setPreviousResponseId] = useState(null);
  const messagesEndRef = useRef(null);
  const messageListRef = useRef(null);

  useEffect(() => {
    if (!showScrollButton) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, showScrollButton]);

  useEffect(() => {
    const el = messageListRef.current;
    if (!el) return;

    const handleScroll = () => {
      const nearBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 50;
      setShowScrollButton(!nearBottom);
    };

    el.addEventListener('scroll', handleScroll);
    return () => el.removeEventListener('scroll', handleScroll);
  }, []);

  const handleScrollToBottom = () => {
    messageListRef.current?.scrollTo({ top: messageListRef.current.scrollHeight, behavior: 'smooth' });
    setShowScrollButton(false);
  };

  const handleSendMessage = async () => {
    if (!newMessage.trim()) return;

    const userMessage = { role: 'user', content: newMessage };
    const currentMessages = [...messages, userMessage];
    setMessages(currentMessages);
    setNewMessage('');
    setIsLoading(true);

    try {
      const response = await fetch('https://localhost:8000/api/assistants/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          messages: currentMessages.map(msg => ({
            role: msg.role,
            content: msg.content,
          })),
          previous_response_id: previousResponseId,
        }),
      });

      const responseText = await response.text();

      if (!response.ok) {
        let errorDetail = responseText;
        try {
          const json = JSON.parse(responseText);
          errorDetail = json.detail || JSON.stringify(json);
        } catch (_) {}
        throw new Error(`HTTP error ${response.status}: ${errorDetail}`);
      }

      const data = JSON.parse(responseText);
      const assistantMessage = { role: 'assistant', content: data.message.content };
      setMessages(prev => [...prev, assistantMessage]);
      setPreviousResponseId(data.response_id);
    } catch (error) {
      console.error(error);
      setMessages(prev => [
        ...prev,
        {
          role: 'assistant',
          content: `Error: ${error.message}`,
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleInputChange = (e) => setNewMessage(e.target.value);

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  return (
    <Box
      sx={{
        height: '100vh',
        width: '100%',
        maxWidth: '100%',
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'column',
        backgroundColor: 'background.default',
      }}
    >
      <Box
        ref={messageListRef}
        sx={{
          flex: 1,
          overflowY: 'auto',
          px: 3,
          py: 2,
          width: '100%',
          maxWidth: '100%',
          boxSizing: 'border-box',
        }}
      >
        <Paper
          elevation={3}
          sx={{
            width: '100%',
            maxWidth: '100%',
            boxSizing: 'border-box',
            p: 2,
            backgroundColor: 'background.paper',
            m: 0,
          }}
        >
          <List sx={{ width: '100%', maxWidth: '100%', pb: 0 }}>
            {messages.map((msg, index) => (
              <ListItem key={index} sx={{ textAlign: msg.role === 'user' ? 'right' : 'left', width: '100%' }}>
                <ListItemText
                  primary={
                    msg.role === 'assistant'
                      ? <AdvancedMarkdownRenderer markdown={msg.content} />
                      : <span className="markdown-body">{msg.content}</span>
                  }
                  sx={{
                    width: '100%',
                    maxWidth: '100%',
                    overflowWrap: 'break-word',
                    bgcolor: msg.role === 'user' ? 'grey.700' : 'transparent',
                    color: 'text.primary',
                    borderRadius: msg.role === 'user' ? '10px' : 0,
                    p: msg.role === 'user' ? 1 : 0,
                    display: 'inline-block',
                  }}
                />
              </ListItem>
            ))}
            {isLoading && (
              <ListItem sx={{ justifyContent: 'center', width: '100%' }}>
                <CircularProgress size={24} />
              </ListItem>
            )}
            <div ref={messagesEndRef} />
          </List>
        </Paper>
      </Box>
      <Box
        sx={{
          position: 'sticky',
          bottom: 0,
          width: '100%',
          maxWidth: '100%',
          px: 3,
          py: 2,
          borderTop: '1px solid #333',
          backgroundColor: 'background.paper',
          zIndex: 1000,
          display: 'flex',
          alignItems: 'center',
          boxSizing: 'border-box',
        }}
      >
        <TextField
          fullWidth
          placeholder="Ask about your gear, quests, or Destiny..."
          variant="outlined"
          value={newMessage}
          onChange={handleInputChange}
          onKeyPress={handleKeyPress}
          multiline
          maxRows={4}
          disabled={isLoading}
        />
        <Button
          variant="contained"
          color="primary"
          onClick={handleSendMessage}
          disabled={isLoading || !newMessage.trim()}
          sx={{ ml: 1 }}
        >
          Send
        </Button>
        <VoiceInputButton onTranscription={setNewMessage} />
      </Box>
    </Box>
  );
}

export default ChatPage; 