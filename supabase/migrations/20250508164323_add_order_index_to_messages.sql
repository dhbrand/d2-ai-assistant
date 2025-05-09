alter table public.messages
add column if not exists order_index integer not null default 0;

comment on column public.messages.order_index is 'Explicit order of the message within a conversation, starts at 0.';
