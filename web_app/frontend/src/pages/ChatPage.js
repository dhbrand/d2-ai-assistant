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
  Alert,
  Chip,
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
import Select from '@mui/material/Select';
import { createParser } from 'eventsource-parser';
import { v4 as uuidv4 } from 'uuid';

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
  const [selectedPersona, setSelectedPersona] = useState('default');
  const [dataRefreshed, setDataRefreshed] = useState(null); // null | true | false
  const [lastUpdated, setLastUpdated] = useState(null); // null | string (ISO)
  const [agentSteps, setAgentSteps] = useState([]); // For agentic step/status
  const [agentState, setAgentState] = useState({}); // For state snapshot/delta
  const [error, setError] = useState(null);

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
    setIsLoading(true);
    setError(null);

    // Generate or reuse threadId and runId
    let threadId = localStorage.getItem('agui_thread_id');
    if (!threadId) {
      threadId = uuidv4();
      localStorage.setItem('agui_thread_id', threadId);
    }
    const runId = uuidv4();

    // Build messages array (align with ag_ui.core.types.BaseMessage: use 'name' for user ID, 'id' for message ID)
    const userId = localStorage.getItem('agui_user_id') || uuidv4();
    localStorage.setItem('agui_user_id', userId);
    const messageId = uuidv4(); // Unique ID for this specific message

    const messages = [
      {
        id: messageId,       // ID for the message itself (BaseMessage.id)
        role: 'user',
        content: newMessage,
        name: userId,         // User identifier goes into the 'name' field (BaseMessage.name)
      },
    ];

    // Add the new user message to the local state immediately
    setMessages(prevMessages => [
      ...prevMessages,
      { role: 'user', content: newMessage },
    ]);
    setNewMessage(''); // Clear input field
    setAgentSteps([]); // Clear previous agent steps
    setAgentState({}); // Clear previous agent state

    console.log("Attempting to connect to agent stream with payload:", {
      thread_id: threadId,
      run_id: runId,
      messages: messages, // These are the AG-UI formatted messages
      context: [], // As per backend expectation
      forwarded_props: { persona: selectedPersona },
    });

    try {
      console.log("Fetch promise created for /agent/stream");
      const responsePromise = fetch('/agent/stream', { // Using relative path for proxy
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`, // Assuming token is needed
        },
        body: JSON.stringify({
          thread_id: threadId,
          run_id: runId,
          messages: messages, // Send the AG-UI formatted messages
          state: null, 
          tools: [], // CHANGED: Was null, now an empty array
          context: [], 
          forwarded_props: { persona: selectedPersona },
        }),
      });

      // Log when the promise resolves, regardless of status
      const response = await responsePromise;
      console.log("Fetch response received for /agent/stream, status:", response.status);

      if (!response.ok) {
        const errorText = await response.text();
        console.error('Failed to connect to agent stream:', response.status, errorText);
        setError(`Error: ${response.status} ${errorText || response.statusText}`);
        setIsLoading(false);
        // Add the error message to the chat
        setMessages(prevMessages => [
          ...prevMessages,
          { role: 'assistant', content: `Error connecting to agent: ${response.status} ${errorText || response.statusText}` },
        ]);
        return;
      }

      // Handle SSE stream
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let incomingText = '';
      let currentAssistantMessageId = null;

      const parser = createParser({
        onEvent: (event) => {
          if (event.type === 'event') {
            try {
              const data = JSON.parse(event.data);
              // console.log('Received SSE event:', data); // Optional: log every event

              if (data.type === 'TEXT_MESSAGE_START') {
                currentAssistantMessageId = data.message_id;
                console.log('[ChatPage] TEXT_MESSAGE_START received, message_id:', currentAssistantMessageId);
                setMessages(prev => {
                  console.log('[ChatPage] Updater for TEXT_MESSAGE_START - prevMessages:', prev);
                  const newAssistantMessage = {
                    id: currentAssistantMessageId, 
                    role: 'assistant', 
                    content: '' 
                  };
                  console.log('[ChatPage] Updater for TEXT_MESSAGE_START - adding new message:', newAssistantMessage);
                  return [...prev, newAssistantMessage];
                });
              } else if (data.type === 'TEXT_MESSAGE_CONTENT') {
                console.log('[ChatPage] TEXT_MESSAGE_CONTENT received, delta:', data.delta, 'for message_id:', data.message_id, 'currentAssistantMessageId:', currentAssistantMessageId);
                if (data.delta) {
                  setMessages(prev => {
                    console.log('[ChatPage] Updater for TEXT_MESSAGE_CONTENT - prevMessages:', prev);
                    console.log('[ChatPage] Updater for TEXT_MESSAGE_CONTENT - targetMessageId:', data.message_id);
                    return prev.map(m => {
                      if (m.id === data.message_id) {
                        console.log('[ChatPage] Updater for TEXT_MESSAGE_CONTENT - message to update:', m, 'appending delta:', data.delta);
                        return { ...m, content: m.content + data.delta }; // Correctly append to existing content
                      } else {
                        return m; // Return other messages unchanged
                      }
                    });
                  });
                }
              } else if (data.type === 'TEXT_MESSAGE_END') {
                // Finalize the message if needed, incomingText should already be complete
                currentAssistantMessageId = null; // Reset for next message
              } else if (data.type === 'STEP_STARTED') {
                setAgentSteps(prev => [...prev, { id: data.step_id, name: data.name, status: 'running' }]);
              } else if (data.type === 'STEP_FINISHED') {
                setAgentSteps(prev => prev.map(s => s.id === data.step_id ? { ...s, status: 'finished' } : s));
              } else if (data.type === 'STATE_SNAPSHOT' || data.type === 'STATE_DELTA') {
                // For simplicity, merging delta into a snapshot view.
                // A more complex UI might differentiate.
                setAgentState(prevState => ({ ...prevState, ...data.state }));
              } else if (data.type === 'RUN_ERROR') {
                  console.error("Agent Run Error:", data.message, data.details);
                  setError(`Agent Error: ${data.message}`);
                  setMessages(prevMessages => [
                      ...prevMessages,
                      { role: 'assistant', content: `Agent Error: ${data.message}` },
                  ]);
              }

            } catch (e) {
              console.error('Error parsing SSE event data inside createParser callback:', e);
              console.error('Offending event.type:', event.type);
              console.error('Offending event.data raw:', event.data);
              setError(`Error processing event: ${e.message}. Check console for details on event data.`);
            }
          } else if (event.type === 'reconnect-interval') {
            console.log('SSE reconnect interval requested:', event.value);
          }
        }
      });
      
      // eslint-disable-next-line no-constant-condition
      while (true) {
        const { done, value } = await reader.read();
        if (done) {
          console.log("SSE stream finished.");
          break;
        }
        const chunk = decoder.decode(value, { stream: true });
        console.log("SSE chunk received:", chunk); // Log each chunk
        parser.feed(chunk);
      }

    } catch (err) {
      console.error('Error sending message or processing stream:', err);
      setError(`Network or processing error: ${err.message}`);
      // Add the error message to the chat
      setMessages(prevMessages => [
        ...prevMessages,
        { role: 'assistant', content: `Error: ${err.message}` },
      ]);
    } finally {
      setIsLoading(false);
      // Ensure scroll to bottom after message processing is done
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
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
        {/* AGENT THOUGHTS/STEP STATUS */}
        {agentSteps.length > 0 && (
          <Paper elevation={2} sx={{ p: 2, mb: 1, background: '#222', color: '#fff' }}>
            <strong>Agent Thoughts:</strong>
            <ul style={{ margin: 0, paddingLeft: 20 }}>
              {agentSteps.map((s, i) => (
                <li key={s.name + i} style={{ color: s.status === 'finished' ? 'lightgreen' : '#fff' }}>
                  {s.name} {s.status === 'finished' ? '✅' : '⏳'}
                </li>
              ))}
            </ul>
          </Paper>
        )}
        {/* AGENT STATE SNAPSHOT */}
        {agentState && Object.keys(agentState).length > 0 && (
          <Paper elevation={1} sx={{ p: 2, mb: 1, background: '#333', color: '#fff', fontSize: 13 }}>
            <strong>Agent State:</strong>
            <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{JSON.stringify(agentState, null, 2)}</pre>
          </Paper>
        )}
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
            flexDirection: 'column', // Stack persona dropdown above input
          }}
        >
          <Box sx={{ width: '100%', mb: 1, display: 'flex', alignItems: 'center', justifyContent: 'flex-end' }}>
            <Select
              value={selectedPersona}
              onChange={e => setSelectedPersona(e.target.value)}
              size="small"
              sx={{ minWidth: 180 }}
            >
              <MenuItem value="default">Default</MenuItem>
              <MenuItem value="Saint-14">Saint-14</MenuItem>
              <MenuItem value="Cayde-6">Cayde-6</MenuItem>
              <MenuItem value="Ikora">Ikora</MenuItem>
              <MenuItem value="Saladin">Saladin</MenuItem>
              <MenuItem value="Zavala">Zavala</MenuItem>
              <MenuItem value="Eris Morn">Eris Morn</MenuItem>
              <MenuItem value="Shaxx">Shaxx</MenuItem>
              <MenuItem value="Drifter">Drifter</MenuItem>
              <MenuItem value="Mara Sov">Mara Sov</MenuItem>
            </Select>
          </Box>
          {/* Data refresh badge/note */}
          {dataRefreshed === true && (
            <Alert severity="success" sx={{ mb: 1, width: '100%' }}>Your Destiny 2 data was just refreshed!</Alert>
          )}
          {dataRefreshed === false && lastUpdated && (
            <Chip
              label={`Data last updated: ${new Date(lastUpdated).toLocaleString()}`}
              color="info"
              variant="outlined"
              sx={{ mb: 1, width: '100%' }}
            />
          )}
          <Box sx={{ width: '100%', display: 'flex', alignItems: 'center' }}>
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