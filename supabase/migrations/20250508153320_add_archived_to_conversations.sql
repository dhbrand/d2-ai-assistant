alter table public.conversations
add column if not exists archived boolean default false not null;

comment on column public.conversations.archived is 'Indicates if the conversation is archived and hidden by default.';
