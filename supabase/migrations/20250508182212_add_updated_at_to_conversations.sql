-- Add updated_at column
alter table public.conversations
add column if not exists updated_at timestamp with time zone default timezone('utc'::text, now()) not null;

-- Create a trigger function to update updated_at
create or replace function public.handle_updated_at()
returns trigger as $$
begin
  new.updated_at = timezone('utc'::text, now());
  return new;
end;
$$ language plpgsql;

-- Drop existing trigger if it exists (optional, for idempotency)
drop trigger if exists on_conversation_update on public.conversations;

-- Create the trigger to call the function before any update on the conversations table
create trigger on_conversation_update
before update on public.conversations
for each row
execute function public.handle_updated_at();

comment on column public.conversations.updated_at is 'Timestamp of the last update to the conversation record.';
comment on trigger on_conversation_update on public.conversations is 'Trigger to automatically update updated_at timestamp on row update.';
