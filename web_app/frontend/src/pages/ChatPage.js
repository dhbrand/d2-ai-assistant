import React, { useState, useEffect, useContext } from 'react';
import { Box, TextField, Button, Paper, Typography, List, ListItem, ListItemText, CircularProgress } from '@mui/material';
import { AuthContext, useAuth } from '../contexts/AuthContext';

function ChatPage() {
  const { token } = useAuth();
  const [messages, setMessages] = useState([]); // Stores { sender: 'user'/'assistant', text: 'message' }
  const [newMessage, setNewMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [catalystData, setCatalystData] = useState(null); // State to hold catalyst data
  const [weaponData, setWeaponData] = useState(null); // State to hold weapon data
  const [initialContextSent, setInitialContextSent] = useState(false); // Flag to send context only once

  // Fetch catalyst and weapon data on component mount
  useEffect(() => {
    console.log('ChatPage useEffect triggered. Token:', token ? `${token.substring(0,5)}...` : 'null'); // Log effect start
    
    const fetchAllContextData = async () => {
        console.log('fetchAllContextData called. Token:', token ? `${token.substring(0,5)}...` : 'null'); 
        if (!token) {
            console.log('fetchAllContextData: No token found, exiting.');
            return; 
        }
        setIsLoading(true); 
        try {
            // Fetch catalysts and weapons in parallel
            const [catalystResponse, weaponResponse] = await Promise.all([
                fetch('https://localhost:8000/catalysts/all', {
                    headers: { 'Authorization': `Bearer ${token}` },
                }),
                fetch('https://localhost:8000/weapons/all', {
                    headers: { 'Authorization': `Bearer ${token}` },
                })
            ]);

            // Process catalyst data
            if (!catalystResponse.ok) {
                throw new Error(`HTTP error fetching catalysts! status: ${catalystResponse.status}`);
            }
            const catalystResult = await catalystResponse.json();
            setCatalystData(catalystResult);
            console.log("Catalyst data loaded for chat context:", catalystResult);

            // Process weapon data
            if (!weaponResponse.ok) {
                throw new Error(`HTTP error fetching weapons! status: ${weaponResponse.status}`);
            }
            const weaponResult = await weaponResponse.json();
            setWeaponData(weaponResult);
            console.log("Weapon data loaded for chat context:", weaponResult);

        } catch (error) {
            console.error('Error fetching context data for chat:', error);
            const errorMessage = { sender: 'assistant', text: `Sorry, failed to load context data. Details: ${error.message}` };
            setMessages(prevMessages => [...prevMessages, errorMessage]);
        } finally {
            setIsLoading(false);
        }
    };

    fetchAllContextData();

  }, [token]); // Re-fetch if token changes (e.g., after login)

  const handleSendMessage = async () => {
    if (!newMessage.trim()) return;

    const userMessage = { sender: 'user', text: newMessage };
    setMessages(prevMessages => [...prevMessages, userMessage]);
    setNewMessage('');
    setIsLoading(true);

    try {
        // Prepare request body
        const requestBody = { 
            message: userMessage.text 
        };

        // Add context only if it exists and hasn't been sent yet
        if (!initialContextSent && (catalystData || weaponData)) { // Check if either data exists
            if (catalystData) requestBody.catalyst_context = catalystData;
            if (weaponData) requestBody.weapon_context = weaponData; // Add weapon data
            setInitialContextSent(true); // Mark context as sent
            console.log("Sending initial context (catalysts/weapons) with message.");
        }

      const response = await fetch('https://localhost:8000/api/chat', { // Use absolute path
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestBody) // Send updated body with optional context
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      const assistantMessage = { sender: 'assistant', text: data.reply };
      setMessages(prevMessages => [...prevMessages, assistantMessage]);

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
                  bgcolor: msg.sender === 'user' ? 'grey.700' : 'transparent', 
                  color: 'text.primary',
                  borderRadius: msg.sender === 'user' ? '10px' : 0,
                  p: msg.sender === 'user' ? 1 : 0,
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