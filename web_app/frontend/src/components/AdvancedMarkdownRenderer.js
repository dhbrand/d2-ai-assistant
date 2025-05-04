import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';
import './markdown.css';

const AdvancedMarkdownRenderer = ({ markdown }) => {
  return (
    <div className="markdown-wrapper">
      <ReactMarkdown
        children={markdown}
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeRaw]}
        components={{
          th: ({ node, ...props }) => <th {...props} style={{ backgroundColor: '#f0f0f0' }} />,
          table: ({ node, ...props }) => (
            <table style={{ borderCollapse: 'collapse', width: '100%' }} {...props} />
          ),
          td: ({ node, ...props }) => <td {...props} style={{ padding: '0.5em', border: '1px solid #ddd' }} />,
        }}
      />
    </div>
  );
};

export default AdvancedMarkdownRenderer; 