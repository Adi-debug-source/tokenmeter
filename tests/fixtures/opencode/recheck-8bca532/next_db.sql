-- An opencode-next.db left by an older "next" build of OpenCode, as
-- anomalyco/opencode lays one out at commit eb95bd2 (30 July 2026): its v2
-- sessions are in a table named session, with fork_session_id, and there are
-- no v1 tables. At 8bca532 (1 November 2026) the upgrade copies its sessions
-- and rows into opencode.db under the same ids and leaves this file in place
-- (packages/core/src/database/v1-migration.bun.ts, importNextDatabase). It
-- holds sessions 2 and 4 of build_db.sql; the content is invented.

CREATE TABLE project (
  id text PRIMARY KEY,
  worktree text NOT NULL,
  vcs text,
  name text,
  icon_url text,
  icon_url_override text,
  icon_color text,
  time_created integer NOT NULL,
  time_updated integer NOT NULL,
  time_initialized integer,
  sandboxes text NOT NULL,
  commands text
);

CREATE TABLE session (
  id text PRIMARY KEY,
  project_id text NOT NULL,
  workspace_id text,
  parent_id text,
  fork_session_id text,
  fork_boundary text,
  slug text NOT NULL,
  directory text NOT NULL,
  path text,
  title text,
  version text NOT NULL,
  share_url text,
  summary_additions integer,
  summary_deletions integer,
  summary_files integer,
  summary_diffs text,
  metadata text,
  cost real DEFAULT 0 NOT NULL,
  tokens_input integer DEFAULT 0 NOT NULL,
  tokens_output integer DEFAULT 0 NOT NULL,
  tokens_reasoning integer DEFAULT 0 NOT NULL,
  tokens_cache_read integer DEFAULT 0 NOT NULL,
  tokens_cache_write integer DEFAULT 0 NOT NULL,
  revert text,
  permission text,
  agent text,
  model text,
  time_created integer NOT NULL,
  time_updated integer NOT NULL,
  time_compacting integer,
  time_archived integer,
  time_suspended integer
);

CREATE TABLE session_message (
  id text PRIMARY KEY,
  session_id text NOT NULL REFERENCES session(id) ON DELETE CASCADE,
  type text NOT NULL,
  seq integer NOT NULL,
  time_created integer NOT NULL,
  time_updated integer NOT NULL,
  data text NOT NULL
);
CREATE UNIQUE INDEX session_message_session_seq_idx ON session_message (session_id, seq);

INSERT INTO project (id, worktree, vcs, name, time_created, time_updated, time_initialized, sandboxes)
VALUES ('prj_widget', '/Users/example/code/widget', 'git', 'widget', 1792000000000, 1792000000000, 1792000000000, '[]');

INSERT INTO session (id, project_id, slug, directory, title, version, cost,
  tokens_input, tokens_output, tokens_reasoning, tokens_cache_read, tokens_cache_write,
  agent, model, time_created, time_updated)
VALUES ('ses_v2native001', 'prj_widget', 'speed-up-the-build', '/Users/example/code/widget',
  'Speed up the build', '2.0.3', 0, 3600, 440, 400, 9600, 5200, 'build',
  '{"id":"gpt-5.2-codex","providerID":"openai"}', 1792001000000, 1792001300000);

INSERT INTO session_message VALUES ('msg_v2natuser01', 'ses_v2native001', 'user', 0, 1792001010000, 1792001010000,
  json('{"text":"Why is the build slow?","time":{"created":1792001010000}}'));

INSERT INTO session_message VALUES ('msg_v2nat0001', 'ses_v2native001', 'assistant', 1, 1792001020000, 1792001060000,
  json('{"agent":"build","model":{"id":"claude-sonnet-4-5","providerID":"anthropic"},"content":[{"type":"text","text":"The cache is cold."}],"finish":"stop","cost":0.0273,"tokens":{"input":2400,"output":180,"reasoning":0,"cache":{"read":0,"write":5200}},"time":{"created":1792001020000,"streamed":1792001058000,"completed":1792001060000}}'));

INSERT INTO session_message VALUES ('msg_v2natswitch', 'ses_v2native001', 'model-switched', 2, 1792001100000, 1792001100000,
  json('{"model":{"id":"gpt-5.2-codex","providerID":"openai","variant":"high"},"previous":{"id":"claude-sonnet-4-5","providerID":"anthropic"},"time":{"created":1792001100000}}'));

INSERT INTO session_message VALUES ('msg_v2nat0002', 'ses_v2native001', 'assistant', 3, 1792001110000, 1792001170000,
  json('{"agent":"build","model":{"id":"gpt-5.2-codex","providerID":"openai","variant":"high"},"content":[{"type":"text","text":"Turned on the remote cache."}],"finish":"stop","cost":0.0094,"tokens":{"input":1200,"output":260,"reasoning":400,"cache":{"read":9600,"write":0}},"time":{"created":1792001110000,"completed":1792001170000}}'));

-- The fork, with its copy of the parent's call and one call of its own.
INSERT INTO session (id, project_id, fork_session_id, fork_boundary, slug, directory, title, version, cost,
  tokens_input, tokens_output, tokens_reasoning, tokens_cache_read, tokens_cache_write,
  agent, model, time_created, time_updated)
VALUES ('ses_v2fork0001', 'prj_widget', 'ses_v2native001',
  '{"type":"through","messageID":"msg_v2nat0001"}', 'try-another-way', '/Users/example/code/widget',
  'Speed up the build (fork #1)', '2.0.3', 0, 700, 90, 0, 4000, 0, 'build',
  '{"id":"claude-sonnet-4-5","providerID":"anthropic"}', 1792003000000, 1792003080000);

INSERT INTO session_message VALUES ('msg_forkevt01_0', 'ses_v2fork0001', 'user', 0, 1792001010000, 1792001010000,
  json('{"text":"Why is the build slow?","time":{"created":1792001010000}}'));

INSERT INTO session_message VALUES ('msg_forkevt01_1', 'ses_v2fork0001', 'assistant', 1, 1792001020000, 1792001060000,
  json('{"agent":"build","model":{"id":"claude-sonnet-4-5","providerID":"anthropic"},"content":[{"type":"text","text":"The cache is cold."}],"finish":"stop","cost":0.0273,"tokens":{"input":2400,"output":180,"reasoning":0,"cache":{"read":0,"write":5200}},"time":{"created":1792001020000,"streamed":1792001058000,"completed":1792001060000}}'));

INSERT INTO session_message VALUES ('msg_v2fork0001', 'ses_v2fork0001', 'assistant', 2, 1792003020000, 1792003080000,
  json('{"agent":"build","model":{"id":"claude-sonnet-4-5","providerID":"anthropic"},"content":[{"type":"text","text":"Try a smaller image."}],"finish":"stop","cost":0.0047,"tokens":{"input":700,"output":90,"reasoning":0,"cache":{"read":4000,"write":0}},"time":{"created":1792003020000,"completed":1792003080000}}'));
