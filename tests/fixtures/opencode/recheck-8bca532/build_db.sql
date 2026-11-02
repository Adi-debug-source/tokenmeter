-- OpenCode's database as anomalyco/opencode lays it out at commit 8bca532
-- (1 November 2026), after an upgrade from a release that wrote the v1
-- tables. Table and column names are from packages/core/src/database/
-- schema.gen.ts and v1-migration.bun.ts; the content is invented.
PRAGMA journal_mode = WAL;

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
  time_active integer DEFAULT 0 NOT NULL,
  time_archived integer,
  sandboxes text NOT NULL,
  commands text
);

CREATE TABLE kv (
  key text PRIMARY KEY,
  value text NOT NULL,
  time_created integer NOT NULL,
  time_updated integer NOT NULL
);

-- The v1 tables, left in place by the upgrade and no longer written.
CREATE TABLE session (
  id text PRIMARY KEY NOT NULL,
  project_id text NOT NULL,
  workspace_id text,
  parent_id text,
  slug text NOT NULL,
  directory text NOT NULL,
  path text,
  title text NOT NULL,
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
  time_archived integer
);

CREATE TABLE message (
  id text PRIMARY KEY NOT NULL,
  session_id text NOT NULL,
  time_created integer NOT NULL,
  time_updated integer NOT NULL,
  data text NOT NULL
);

CREATE TABLE part (
  id text PRIMARY KEY NOT NULL,
  message_id text NOT NULL,
  session_id text NOT NULL,
  time_created integer NOT NULL,
  time_updated integer NOT NULL,
  data text NOT NULL
);

-- The v2 tables.
CREATE TABLE session_v2 (
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
  time_busy integer,
  time_idle integer,
  time_viewed integer,
  idle_outcome text,
  time_compacting integer,
  time_archived integer,
  time_suspended integer,
  resume_attempts integer DEFAULT 0 NOT NULL
);

CREATE TABLE session_message (
  id text PRIMARY KEY,
  session_id text NOT NULL REFERENCES session_v2(id) ON DELETE CASCADE,
  type text NOT NULL,
  seq integer NOT NULL,
  time_created integer NOT NULL,
  time_updated integer NOT NULL,
  data text NOT NULL
);
CREATE UNIQUE INDEX session_message_session_seq_idx ON session_message (session_id, seq);

CREATE TABLE session_part (
  message_id text NOT NULL,
  session_id text NOT NULL,
  ordinal integer NOT NULL,
  type text NOT NULL,
  call_id text,
  time_created integer NOT NULL,
  time_updated integer NOT NULL,
  data text NOT NULL,
  CONSTRAINT session_part_pk PRIMARY KEY (message_id, ordinal)
);

INSERT INTO project (id, worktree, vcs, name, time_created, time_updated, time_initialized, time_active, sandboxes)
VALUES ('prj_demo', '/Users/example/code/demo', 'git', 'demo', 1792000000000, 1792000000000, 1792000000000, 1792000000000, '[]'),
       ('prj_widget', '/Users/example/code/widget', 'git', 'widget', 1792000000000, 1792000000000, 1792000000000, 1792000000000, '[]');

INSERT INTO kv VALUES ('migration.v1-v2', json('{"phase":"completed"}'), 1792000500000, 1792000500000);

-- 1. A v1 session, written before the upgrade: one assistant message, two steps.
INSERT INTO session (id, project_id, slug, directory, title, version, cost,
  tokens_input, tokens_output, tokens_reasoning, tokens_cache_read, tokens_cache_write,
  agent, model, time_created, time_updated)
VALUES ('ses_v1keep0001', 'prj_demo', 'tidy-the-readme', '/Users/example/code/demo',
  'Tidy the README', '1.9.0', 0.0371, 4000, 550, 120, 18000, 2100, 'build',
  '{"id":"claude-sonnet-4-5","providerID":"anthropic"}', 1792000010000, 1792000090000);

INSERT INTO message VALUES ('msg_v1user0101', 'ses_v1keep0001', 1792000010000, 1792000010000,
  json('{"role":"user","time":{"created":1792000010000},"agent":"build","model":{"providerID":"anthropic","modelID":"claude-sonnet-4-5"}}'));

INSERT INTO message VALUES ('msg_v1asst0101', 'ses_v1keep0001', 1792000012000, 1792000090000,
  json('{"role":"assistant","time":{"created":1792000012000,"completed":1792000090000},"parentID":"msg_v1user0101","modelID":"claude-sonnet-4-5","providerID":"anthropic","mode":"build","agent":"build","path":{"cwd":"/Users/example/code/demo","root":"/Users/example/code/demo"},"cost":0.0371,"tokens":{"total":19960,"input":900,"output":340,"reasoning":120,"cache":{"read":18000,"write":600}},"finish":"stop"}'));

INSERT INTO part VALUES ('prt_v1step0101', 'msg_v1asst0101', 'ses_v1keep0001', 1792000040000, 1792000040000,
  json('{"type":"step-finish","reason":"tool-calls","cost":0.0172,"tokens":{"total":4810,"input":3100,"output":210,"reasoning":0,"cache":{"read":0,"write":1500}}}'));

INSERT INTO part VALUES ('prt_v1step0102', 'msg_v1asst0101', 'ses_v1keep0001', 1792000090000, 1792000090000,
  json('{"type":"step-finish","reason":"stop","cost":0.0199,"tokens":{"total":19960,"input":900,"output":340,"reasoning":120,"cache":{"read":18000,"write":600}}}'));

-- The same session as the upgrade copied it: the v1 ids kept, and the
-- assistant row holding only the last step's tokens (and the turn's cost).
-- The session's totals are summed from those rows, so they miss step 1 too.
INSERT INTO session_v2 (id, project_id, slug, directory, title, version, cost,
  tokens_input, tokens_output, tokens_reasoning, tokens_cache_read, tokens_cache_write,
  agent, model, time_created, time_updated)
VALUES ('ses_v1keep0001', 'prj_demo', 'tidy-the-readme', '/Users/example/code/demo',
  'Tidy the README', '1.9.0', 0.0371, 900, 340, 120, 18000, 600, 'build',
  '{"id":"claude-sonnet-4-5","providerID":"anthropic"}', 1792000010000, 1792000090000);

INSERT INTO session_message VALUES ('msg_v1user0101', 'ses_v1keep0001', 'user', 0, 1792000010000, 1792000010000,
  json('{"text":"Tidy the README.","time":{"created":1792000010000}}'));

INSERT INTO session_message VALUES ('msg_v1asst0101', 'ses_v1keep0001', 'assistant', 1, 1792000012000, 1792000090000,
  json('{"agent":"build","model":{"providerID":"anthropic","id":"claude-sonnet-4-5","variant":"default"},"content":[{"type":"text","text":"Done."}],"finish":"stop","cost":0.0371,"tokens":{"input":900,"output":340,"reasoning":120,"cache":{"read":18000,"write":600}},"time":{"created":1792000012000,"completed":1792000090000}}'));

-- 2. A v2 session, in session_v2 only. The model changes mid-session; one
-- step is still streaming; a compaction ran.
INSERT INTO session_v2 (id, project_id, slug, directory, title, version, cost,
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

-- Its content lives in session_part, so the row keeps an empty envelope.
INSERT INTO session_message VALUES ('msg_v2nat0002', 'ses_v2native001', 'assistant', 3, 1792001110000, 1792001170000,
  json('{"agent":"build","model":{"id":"gpt-5.2-codex","providerID":"openai","variant":"high"},"content":[],"finish":"stop","cost":0.0094,"tokens":{"input":1200,"output":260,"reasoning":400,"cache":{"read":9600,"write":0}},"time":{"created":1792001110000,"completed":1792001170000}}'));

INSERT INTO session_part VALUES ('msg_v2nat0002', 'ses_v2native001', 0, 'text', NULL, 1792001170000, 1792001170000,
  json('{"type":"text","text":"Turned on the remote cache."}'));

-- Still streaming: no tokens yet.
INSERT INTO session_message VALUES ('msg_v2nat0003', 'ses_v2native001', 'assistant', 4, 1792001200000, 1792001200000,
  json('{"agent":"build","model":{"id":"gpt-5.2-codex","providerID":"openai","variant":"high"},"content":[],"time":{"created":1792001200000}}'));

-- A compaction: its tokens are a total over its calls, so it is not read.
INSERT INTO session_message VALUES ('msg_v2natcomp01', 'ses_v2native001', 'compaction', 5, 1792001250000, 1792001290000,
  json('{"status":"completed","reason":"auto","model":{"id":"gpt-5.2-codex","providerID":"openai"},"summary":"The build is faster.","cost":0.002,"tokens":{"input":8000,"output":300,"reasoning":0,"cache":{"read":0,"write":0}},"time":{"created":1792001250000}}'));

-- 3. A session run through the claude-agent provider: the call went to the
-- user's claude binary, so it is in Claude Code's own log already.
INSERT INTO session_v2 (id, project_id, slug, directory, title, version, cost,
  tokens_input, tokens_output, tokens_reasoning, tokens_cache_read, tokens_cache_write,
  agent, model, time_created, time_updated)
VALUES ('ses_v2claude001', 'prj_widget', 'write-the-changelog', '/Users/example/code/widget',
  'Write the changelog', '2.0.3', 0, 30, 410, 0, 25000, 3000, 'build',
  '{"id":"opus","providerID":"claude-agent"}', 1792002000000, 1792002100000);

INSERT INTO session_message VALUES ('msg_v2clauser01', 'ses_v2claude001', 'user', 0, 1792002010000, 1792002010000,
  json('{"text":"Write the changelog.","time":{"created":1792002010000}}'));

INSERT INTO session_message VALUES ('msg_v2cla0001', 'ses_v2claude001', 'assistant', 1, 1792002020000, 1792002090000,
  json('{"agent":"build","model":{"id":"opus","providerID":"claude-agent"},"content":[{"type":"text","text":"Written."}],"finish":"stop","cost":0,"tokens":{"input":30,"output":410,"reasoning":0,"cache":{"read":25000,"write":3000}},"time":{"created":1792002020000,"completed":1792002090000}}'));

-- 4. A fork of session 2, made after its first call: that call's row is
-- copied under a new id with the parent's time_created; then one new call.
INSERT INTO session_v2 (id, project_id, fork_session_id, fork_boundary, slug, directory, title, version, cost,
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
