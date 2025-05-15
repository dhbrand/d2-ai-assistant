-- Migration: Create api_performance_logs table for backend profiling
CREATE TABLE IF NOT EXISTS api_performance_logs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp timestamptz NOT NULL DEFAULT now(),
    endpoint text NOT NULL,
    operation text NOT NULL,
    duration_ms integer NOT NULL,
    user_id text,
    request_id text,
    extra_data jsonb
);

-- Optional: Indexes for faster querying
CREATE INDEX IF NOT EXISTS idx_api_perf_logs_timestamp ON api_performance_logs (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_api_perf_logs_user_id ON api_performance_logs (user_id);
CREATE INDEX IF NOT EXISTS idx_api_perf_logs_endpoint ON api_performance_logs (endpoint); 