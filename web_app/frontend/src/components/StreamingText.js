import React, { useState, useEffect } from 'react';

const StreamingText = ({ initialText = "", isLoading = false, style = {} }) => {
  const [text, setText] = useState(initialText);

  // Update when initialText prop changes
  useEffect(() => {
    setText(initialText);
  }, [initialText]);

  return (
    <span style={{ whiteSpace: 'pre-wrap', ...style }}>
      {text}
      {isLoading && (
        <span style={{ 
          color: '#888', 
          fontSize: '14px', 
          marginLeft: '8px',
          animation: 'pulse 1.5s ease-in-out infinite'
        }}>
          ▋
        </span>
      )}
    </span>
  );
};

export default StreamingText; 