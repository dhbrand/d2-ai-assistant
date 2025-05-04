import React, { useState, useEffect, useContext } from 'react';
import { Box, TextField, Button, Paper, Typography, List, ListItem, ListItemText, CircularProgress } from '@mui/material';
import { AuthContext, useAuth } from '../contexts/AuthContext';
import ReactMarkdown from 'react-markdown';

function ChatPage() {
  const { token } = useAuth();
  const [messages, setMessages] = useState([]); // Stores { sender: 'user'/'assistant', text: 'message' }
  const [newMessage, setNewMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const handleSendMessage = async () => {
    if (!newMessage.trim()) return;

    const userMessage = { role: 'user', content: newMessage }; // Use role/content structure
    const currentMessages = [...messages, userMessage]; // Capture current state before async call
    setMessages(currentMessages);
    setNewMessage('');
    setIsLoading(true);

    try {
        // Prepare request body according to backend model
        const requestBody = { 
            messages: currentMessages.map(msg => ({
                role: msg.role, // Map sender to role
                content: msg.content // Map text to content
            }))
            // No need to send token_data unless backend specifically requires it
            // token_data: token ? JSON.parse(localStorage.getItem('tokenData')) : undefined
        };

        // Log the body being sent for debugging
        console.log("Sending request to /api/assistants/chat with body:", JSON.stringify(requestBody));

      const response = await fetch('https://localhost:8000/api/assistants/chat', { 
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          // Include token if your API needs authentication for chat
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify(requestBody) 
      });

      // Log raw response for debugging
      const responseText = await response.text(); 
      console.log("Raw response text:", responseText);

      if (!response.ok) {
        // Try to parse error details if JSON
        let errorDetail = responseText;
        try {
            const errorJson = JSON.parse(responseText);
            errorDetail = errorJson.detail || JSON.stringify(errorJson);
        } catch (parseError) {
            // Ignore if not JSON
        }
        throw new Error(`HTTP error! status: ${response.status}, details: ${errorDetail}`);
      }

      // Parse the JSON response
      const data = JSON.parse(responseText);
      console.log("Parsed response data:", data);

      // Expecting { message: { role: 'assistant', content: '...' } }
      if (!data.message || !data.message.content) {
          throw new Error("Invalid response structure received from backend.");
      }
      // Store assistant message consistently with role/content
      const assistantMessage = { role: 'assistant', content: data.message.content }; 
      setMessages(prevMessages => [...prevMessages, assistantMessage]);

    } catch (error) {
      console.error('Error sending message:', error);
      // Store error message consistently with role/content
      const errorMessage = { role: 'assistant', content: `Sorry, something went wrong fetching the reply. Details: ${error.message}` }; 
      setMessages(prevMessages => [...prevMessages, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleInputChange = (event) => {
    setNewMessage(event.target.value);
  };

  const handleKeyPress = (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault(); // Prevent newline on Enter
      handleSendMessage();
    }
  };

  useEffect(() => {
    // Optional: Scroll to the bottom of the message list when new messages arrive
    const messageList = document.getElementById('message-list-container');
    if (messageList) {
      messageList.scrollTop = messageList.scrollHeight;
    }
  }, [messages]);

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 64px)', // Adjust height based on your layout/AppBar
              maxWidth: '800px', margin: 'auto', p: 2 }}>
      <Typography variant="h4" gutterBottom>Destiny Chat Assistant</Typography>
      <Paper elevation={3} sx={{ flexGrow: 1, overflowY: 'auto', mb: 2, p: 2 }} id="message-list-container">
        <List>
          {messages.map((msg, index) => (
            <ListItem key={index} sx={{ textAlign: msg.role === 'user' ? 'right' : 'left' }}>
              <ListItemText
                primary={msg.role === 'assistant' ? <ReactMarkdown>{msg.content}</ReactMarkdown> : msg.content}
                sx={{
                  bgcolor: msg.role === 'user' ? 'grey.700' : 'transparent',
                  color: 'text.primary',
                  borderRadius: msg.role === 'user' ? '10px' : 0,
                  p: msg.role === 'user' ? 1 : 0,
                  display: 'inline-block',
                  maxWidth: '75%',
                }}
              />
            </ListItem>
          ))}
          {isLoading && (
            <ListItem sx={{ justifyContent: 'center' }}>
              <CircularProgress size={24} />
            </ListItem>
          )}
        </List>
      </Paper>
      <Box sx={{ display: 'flex', mt: 'auto' }}>
        <TextField
          fullWidth
          variant="outlined"
          placeholder="Ask about your gear, quests, or Destiny..."
          value={newMessage}
          onChange={handleInputChange}
          onKeyPress={handleKeyPress}
          disabled={isLoading}
          multiline
          maxRows={4} // Allow some vertical expansion
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
      </Box>
    </Box>
  );
}

export default ChatPage; 