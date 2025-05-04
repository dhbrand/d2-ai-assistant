import React, { useState, useEffect } from 'react';
import { Box, TextField, Button, Paper, Typography, List, ListItem, ListItemText, CircularProgress } from '@mui/material';

function ChatPage() {
  const [messages, setMessages] = useState([]); // Stores { sender: 'user'/'assistant', text: 'message' }
  const [newMessage, setNewMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const handleSendMessage = async () => {
    if (!newMessage.trim()) return;

    const userMessage = { sender: 'user', text: newMessage };
    setMessages(prevMessages => [...prevMessages, userMessage]);
    setNewMessage('');
    setIsLoading(true);

    try {
      const response = await fetch('https://localhost:8000/api/chat', { // Use absolute path
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          // Add authentication headers if needed by your backend
        },
        body: JSON.stringify({ message: userMessage.text }) // Send message in correct format
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      const assistantMessage = { sender: 'assistant', text: data.reply };
      setMessages(prevMessages => [...prevMessages, assistantMessage]);

      // --- Placeholder Reply (Remove when API call is implemented) --- REMOVED
      // await new Promise(resolve => setTimeout(resolve, 1000)); // Simulate network delay
      // const placeholderReply = { sender: 'assistant', text: `Echo: ${userMessage.text}` };
      // setMessages(prevMessages => [...prevMessages, placeholderReply]);
      // --- End Placeholder ---

    } catch (error) {
      console.error('Error sending message:', error);
      const errorMessage = { sender: 'assistant', text: `Sorry, something went wrong fetching the reply. Details: ${error.message}` };
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
            <ListItem key={index} sx={{ textAlign: msg.sender === 'user' ? 'right' : 'left' }}>
              <ListItemText
                primary={msg.text}
                sx={{
                  bgcolor: msg.sender === 'user' ? 'primary.light' : 'grey.200',
                  color: msg.sender === 'user' ? 'primary.contrastText' : 'text.primary',
                  borderRadius: '10px',
                  p: 1,
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