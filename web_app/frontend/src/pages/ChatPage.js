import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Box,
  Drawer,
  List,
  ListItem,
  ListItemButton,
  ListItemText,
  Divider,
  Button,
  TextField,
  CircularProgress,
  Paper,
} from '@mui/material';
import { useAuth } from '../contexts/AuthContext';
import AdvancedMarkdownRenderer from '../components/AdvancedMarkdownRenderer';
import VoiceInputButton from '../components/VoiceInputButton';
import DeleteIcon from '@mui/icons-material/Delete';
import ArchiveIcon from '@mui/icons-material/Archive';
import EditIcon from '@mui/icons-material/Edit';
import CheckIcon from '@mui/icons-material/Check';
import CloseIcon from '@mui/icons-material/Close';
import Switch from '@mui/material/Switch';
import FormControlLabel from '@mui/material/FormControlLabel';
import IconButton from '@mui/material/IconButton';
import Menu from '@mui/material/Menu';
import MenuItem from '@mui/material/MenuItem';
import Tooltip from '@mui/material/Tooltip';

// --- NEW Type Definitions for Chat History (using JSDoc for .js file) ---
/**
 * @typedef {object} Conversation
 * @property {string} id - UUID
 * @property {string} user_bungie_id
 * @property {string | null} title
 * @property {string} created_at - ISO Date string
 * @property {string} updated_at - ISO Date string
 */

/**
 * @typedef {object} ChatApiMessage
 * @property {string} id - UUID
 * @property {string} conversation_id - UUID
 * @property {number} order_index
 * @property {'user' | 'assistant'} role
 * @property {string} content
 * @property {string} timestamp - ISO Date string
 */
// --- End Type Definitions ---

const drawerWidth = 240; // Define sidebar width

function ChatPage() {
  const { token } = useAuth();
  const [messages, setMessages] = useState([]);
  const [newMessage, setNewMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [showScrollButton, setShowScrollButton] = useState(false);
  const [conversations, setConversations] = useState([]);
  const [currentConversationId, setCurrentConversationId] = useState(null);
  const messagesEndRef = useRef(null);
  const messageListRef = useRef(null);
  const [editingTitleId, setEditingTitleId] = useState(null);
  const [editingTitleValue, setEditingTitleValue] = useState('');
  const [showArchived, setShowArchived] = useState(false);
  const [contextMenu, setContextMenu] = useState(null); // { mouseX, mouseY, convId }
  const [contextConvId, setContextConvId] = useState(null);

  // --- NEW Functions for Chat History API Calls ---

  const fetchConversations = useCallback(async () => {
    if (!token) {
      console.log("Fetch conversations: No token found.");
      return [];
    }
    try {
      let url = 'https://localhost:8000/api/conversations';
      if (showArchived) url += '?archived=1';
      const response = await fetch(url, {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Accept': 'application/json',
        },
      });
      if (!response.ok) {
        const errorText = await response.text();
        console.error('Failed to fetch conversations:', response.statusText, errorText);
        return [];
      }
      const data = await response.json();
      return data;
    } catch (error) {
      console.error('Error fetching conversations:', error);
      return [];
    }
  }, [token, showArchived]);

  const fetchMessagesForConversation = useCallback(async (conversationId) => {
     // Check token presence directly
    if (!token || !conversationId) {
        console.log("Fetch messages: No token or conversationId.");
        return [];
    }
    try {
      console.log(`Fetching messages for conversation: ${conversationId}`); // Log start
      const response = await fetch(`https://localhost:8000/api/conversations/${conversationId}/messages`, {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Accept': 'application/json',
        },
      });
      console.log(`Fetch messages response status for ${conversationId}:`, response.status); // Log status
      if (!response.ok) {
         const errorText = await response.text();
        console.error('Failed to fetch messages:', response.statusText, errorText);
        return [];
      }
      /** @type {ChatApiMessage[]} */
      const data = await response.json();
      console.log(`Fetched messages data for ${conversationId}:`, data); // Log data
      // Use 'content' prop directly as assumed by original code's ChatMessage usage
      const formattedMessages = data.map(msg => ({ role: msg.role, content: msg.content })); 
      return formattedMessages;
    } catch (error) {
      console.error('Error fetching messages:', error);
      return [];
    }
  }, [token]); // Dependency on token

  // --- End NEW Functions ---

  // --- NEW useEffect to Fetch Conversations ---
  useEffect(() => {
    if (token) { // Only fetch if token is available
      fetchConversations().then(data => {
        setConversations(data || []); // Set to empty array if fetch fails
        // Optionally, select the first conversation or start new by default
        // if (!currentConversationId && data && data.length > 0) {
        //   setCurrentConversationId(data[0].id);
        // }
      });
    }
  }, [token, fetchConversations]); // Re-fetch if token changes
  // --- End useEffect ---

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

  const handleNewChat = () => {
    setCurrentConversationId(null);
    setMessages([]); // Clear messages for new chat
  };

  const handleSelectConversation = async (id) => {
    if (id !== currentConversationId) {
      setCurrentConversationId(id);
      setMessages([]);
      setNewMessage('');
      setIsLoading(true);
      try {
        const fetchedMessages = await fetchMessagesForConversation(id);
        setMessages(fetchedMessages);
      } catch (error) {
        console.error("Error loading selected conversation:", error);
        setMessages([{role: 'assistant', content: 'Error loading conversation history.'}]);
      } finally {
        setIsLoading(false);
      }
    }
  };

  // --- Polling for Title Update ---
  const pollForTitleUpdate = useCallback((conversationId, maxAttempts = 5, intervalMs = 2000) => {
    let attempts = 0;
    const poll = async () => {
      attempts++;
      const updatedConvs = await fetchConversations();
      setConversations(updatedConvs || []);
      const conv = (updatedConvs || []).find(c => c.id === conversationId);
      if (conv && conv.title && conv.title !== 'New Conversation') {
        // Title updated, stop polling
        return;
      }
      if (attempts < maxAttempts) {
        setTimeout(poll, intervalMs);
      }
    };
    poll();
  }, [fetchConversations]);

  const handleSendMessage = async () => {
    if (!newMessage.trim() || isLoading) return;

    const userMessage = { role: 'user', content: newMessage.trim() };
    setMessages((prev) => [...prev, userMessage]);
    setNewMessage('');
    setIsLoading(true);
    handleScrollToBottom();

    const isNewConversation = !currentConversationId; // Check if it's a new chat BEFORE sending

    try {
      const requestBody = {
        messages: [...messages, userMessage].slice(-20), // Send recent history + new message
        conversation_id: currentConversationId, // Will be null for new chats
      };

      const response = await fetch('https://localhost:8000/api/assistants/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify(requestBody),
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
      
      if (isNewConversation && data.conversation_id) {
        setCurrentConversationId(data.conversation_id);
        fetchConversations();
        // Start polling for title update
        pollForTitleUpdate(data.conversation_id);
      } 

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

  // --- API Calls for Delete, Archive, Rename ---
  const deleteConversation = async (id) => {
    if (!token) return;
    await fetch(`https://localhost:8000/api/conversations/${id}`, {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${token}` },
    });
    const updated = await fetchConversations();
    setConversations(updated || []);
    if (id === currentConversationId) handleNewChat();
  };
  const archiveConversation = async (id) => {
    if (!token) return;
    await fetch(`https://localhost:8000/api/conversations/${id}/archive`, {
      method: 'PATCH',
      headers: { 'Authorization': `Bearer ${token}` },
    });
    const updated = await fetchConversations();
    setConversations(updated || []);
    if (id === currentConversationId) handleNewChat();
  };
  const renameConversation = async (id, newTitle) => {
    if (!token) return;
    await fetch(`https://localhost:8000/api/conversations/${id}/rename`, {
      method: 'PATCH',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ title: newTitle }),
    });
    setEditingTitleId(null);
    setEditingTitleValue('');
    const updated = await fetchConversations();
    setConversations(updated || []);
  };

  // --- Context Menu Handlers ---
  const handleContextMenu = (event, convId) => {
    event.preventDefault();
    setContextMenu(
      contextMenu === null
        ? { mouseX: event.clientX - 2, mouseY: event.clientY - 4 }
        : null,
    );
    setContextConvId(convId);
  };
  const handleCloseContextMenu = (cb) => {
    setContextMenu(null);
    setContextConvId(null);
    if (typeof cb === 'function') {
      setTimeout(cb, 0); // Defer to after menu closes
    } else {
      setEditingTitleId(null);
      setEditingTitleValue('');
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
        backgroundColor: 'background.default',
      }}
    >
      <Drawer
        variant="permanent"
        sx={{
          width: drawerWidth,
          flexShrink: 0,
          [`& .MuiDrawer-paper`]: { width: drawerWidth, boxSizing: 'border-box', position: 'relative' },
        }}
      >
        <Box sx={{ overflow: 'auto', display: 'flex', flexDirection: 'column', height: '100%' }}>
          <List sx={{ flexGrow: 1 }}>
            <ListItem>
              <Button variant="outlined" fullWidth onClick={handleNewChat} sx={{ mt: 1 }}>
                New Chat
              </Button>
            </ListItem>
            <ListItem>
              <FormControlLabel
                control={<Switch checked={showArchived} onChange={e => setShowArchived(e.target.checked)} />}
                label="Show Archived"
              />
            </ListItem>
            <Divider />
            {conversations.length === 0 && (
               <ListItem><ListItemText primary="No conversations yet." /></ListItem>
            )}
            {conversations.map((conv) => (
              <ListItem key={conv.id} disablePadding
                onContextMenu={e => handleContextMenu(e, conv.id)}
                sx={{ alignItems: 'center', minHeight: 56 }}
              >
                <ListItemButton 
                  selected={currentConversationId === conv.id} 
                  onClick={() => handleSelectConversation(conv.id)}
                  sx={{ minHeight: 56 }}
                >
                  <ListItemText 
                    primary={editingTitleId === conv.id ? (
                      <TextField
                        size="small"
                        value={editingTitleValue}
                        onChange={e => setEditingTitleValue(e.target.value)}
                        onKeyDown={e => {
                          if (e.key === 'Enter') renameConversation(conv.id, editingTitleValue);
                          if (e.key === 'Escape') setEditingTitleId(null);
                        }}
                        autoFocus
                        sx={{ width: 200, maxWidth: 250 }}
                        inputProps={{ maxLength: 100 }}
                      />
                    ) : (
                      <Tooltip title={conv.title || 'New Conversation'} placement="right" arrow>
                        <span style={{
                          display: 'inline-block',
                          maxWidth: 200,
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                          verticalAlign: 'middle',
                        }}>{conv.title || 'New Conversation'}</span>
                      </Tooltip>
                    )}
                    secondary={`Updated: ${new Date(conv.updated_at).toLocaleString()}`}
                    primaryTypographyProps={{
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                      maxWidth: 200,
                    }}
                  />
                </ListItemButton>
              </ListItem>
            ))}
          </List>
        </Box>
      </Drawer>

      <Box 
        component="main" 
        sx={{ flexGrow: 1, display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden' }}
      >
        <Box
          ref={messageListRef}
          sx={{
            flex: 1,
            overflowY: 'auto',
            px: 2,
            py: 1,
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
            px: 2,
            py: 1,
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

      {/* Context Menu for Conversation Actions */}
      <Menu
        open={contextMenu !== null}
        onClose={() => handleCloseContextMenu()}
        anchorReference="anchorPosition"
        anchorPosition={
          contextMenu !== null
            ? { top: contextMenu.mouseY, left: contextMenu.mouseX }
            : undefined
        }
      >
        <MenuItem onClick={() => handleCloseContextMenu(() => {
          setEditingTitleId(contextConvId);
          setEditingTitleValue(conversations.find(c => c.id === contextConvId)?.title || '');
        })}>Rename</MenuItem>
        <MenuItem onClick={() => { archiveConversation(contextConvId); handleCloseContextMenu(); }}>Archive</MenuItem>
        <MenuItem onClick={() => { deleteConversation(contextConvId); handleCloseContextMenu(); }} sx={{ color: 'error.main' }}>Delete</MenuItem>
      </Menu>
    </Box>
  );
}

export default ChatPage; 