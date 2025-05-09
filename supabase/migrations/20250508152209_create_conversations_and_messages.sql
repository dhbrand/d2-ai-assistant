-- conversations table
create table if not exists public.conversations (
  id uuid primary key default gen_random_uuid(),
  user_id text, -- Can be linked to your app's user IDs if you have them
  created_at timestamp with time zone default timezone('utc'::text, now()) not null
);

-- Add comments to the table and columns
comment on table public.conversations is 'Stores a record for each chat conversation session.';
comment on column public.conversations.user_id is 'Identifier for the user who initiated the conversation, if applicable.';

-- messages table
create table if not exists public.messages (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references public.conversations(id) on delete cascade,
  sender text not null, -- e.g., 'user', 'assistant', or a persona name
  content text not null,
  created_at timestamp with time zone default timezone('utc'::text, now()) not null
);

-- Add comments to the table and columns
comment on table public.messages is 'Stores individual messages within a conversation.';
comment on column public.messages.conversation_id is 'Links the message to its parent conversation.';
comment on column public.messages.sender is 'Indicates who sent the message (e.g., ''user'', ''assistant'').';
comment on column public.messages.content is 'The actual text content of the message.';

-- Optional: Add indexes for faster queries if you expect many messages/conversations
create index if not exists idx_messages_conversation_id on public.messages(conversation_id);
create index if not exists idx_conversations_user_id on public.conversations(user_id);
