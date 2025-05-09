alter table public.conversations
add column if not exists title text null;

comment on column public.conversations.title is 'A user-friendly or auto-generated title for the conversation.';
