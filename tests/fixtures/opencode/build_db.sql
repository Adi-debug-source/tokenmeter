PRAGMA journal_mode = WAL;

CREATE TABLE project (
  id text PRIMARY KEY NOT NULL,
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
  id text PRIMARY KEY NOT NULL,
  project_id text NOT NULL REFERENCES project(id) ON DELETE cascade,
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
  session_id text NOT NULL REFERENCES session(id) ON DELETE cascade,
  time_created integer NOT NULL,
  time_updated integer NOT NULL,
  data text NOT NULL
);

CREATE TABLE part (
  id text PRIMARY KEY NOT NULL,
  message_id text NOT NULL REFERENCES message(id) ON DELETE cascade,
  session_id text NOT NULL,
  time_created integer NOT NULL,
  time_updated integer NOT NULL,
  data text NOT NULL
);

CREATE TABLE session_message (
  id text PRIMARY KEY NOT NULL,
  session_id text NOT NULL REFERENCES session(id) ON DELETE cascade,
  type text NOT NULL,
  seq integer NOT NULL,
  time_created integer NOT NULL,
  time_updated integer NOT NULL,
  data text NOT NULL
);
CREATE UNIQUE INDEX session_message_session_seq_idx ON session_message (session_id, seq);

INSERT INTO project VALUES (
  'prj_9c41a7e2', '/Users/example/code/demo', 'git', 'demo', NULL, NULL, NULL,
  1790000000000, 1790000200000, 1790000000000, '[]', NULL
);

-- v1 session (legacy TUI path). One assistant message, two LLM steps.
INSERT INTO session VALUES (
  'ses_v1demo0001', 'prj_9c41a7e2', NULL, NULL, 'add-verbose-flag',
  '/Users/example/code/demo', NULL, 'Add a --verbose flag', '1.4.2', NULL,
  12, 3, 2, NULL, NULL,
  0.0432, 6390, 742, 480, 21504, 4096, NULL, NULL, 'build',
  '{"id":"claude-sonnet-4-5","providerID":"anthropic"}',
  1790000000000, 1790000200000, NULL, NULL
);

INSERT INTO message VALUES (
  'msg_v1user0001', 'ses_v1demo0001', 1790000010000, 1790000010000,
  json('{"role":"user","time":{"created":1790000010000},"agent":"build","model":{"providerID":"anthropic","modelID":"claude-sonnet-4-5"}}')
);

-- The assistant message holds only the LAST step''s tokens; cost is the SUM of both steps.
INSERT INTO message VALUES (
  'msg_v1asst0001', 'ses_v1demo0001', 1790000012000, 1790000061000,
  json('{"role":"assistant","time":{"created":1790000012000,"completed":1790000061000},"parentID":"msg_v1user0001","modelID":"claude-sonnet-4-5","providerID":"anthropic","mode":"build","agent":"build","path":{"cwd":"/Users/example/code/demo","root":"/Users/example/code/demo"},"cost":0.0432,"tokens":{"total":26980,"input":2170,"output":455,"reasoning":480,"cache":{"read":21504,"write":2371}},"finish":"stop"}')
);

INSERT INTO part VALUES (
  'prt_v1step0001', 'msg_v1asst0001', 'ses_v1demo0001', 1790000030000, 1790000030000,
  json('{"type":"step-finish","reason":"tool-calls","cost":0.0219,"tokens":{"total":6512,"input":4220,"output":287,"reasoning":0,"cache":{"read":0,"write":1725}}}')
);

INSERT INTO part VALUES (
  'prt_v1step0002', 'msg_v1asst0001', 'ses_v1demo0001', 1790000061000, 1790000061000,
  json('{"type":"step-finish","reason":"stop","cost":0.0213,"tokens":{"total":26980,"input":2170,"output":455,"reasoning":480,"cache":{"read":21504,"write":2371}}}')
);

-- v2 session (session_message event-sourced path). One assistant row per LLM step.
INSERT INTO session VALUES (
  'ses_v2demo0002', 'prj_9c41a7e2', NULL, NULL, 'rename-the-cli',
  '/Users/example/code/demo', NULL, 'Rename the CLI', '1.4.2', NULL,
  4, 1, 1, NULL, NULL,
  0, 3960, 512, 900, 18880, 1280, NULL, NULL, 'build',
  '{"id":"gpt-5.2-codex","providerID":"openai"}',
  1790000300000, 1790000420000, NULL, NULL
);

INSERT INTO session_message VALUES (
  'msg_v2user0001', 'ses_v2demo0002', 'user', 1, 1790000305000, 1790000305000,
  json('{"text":"Rename the binary from demo to democtl.","files":[],"agents":[],"time":{"created":1790000305000}}')
);

-- Call A: cached input, no reasoning.
INSERT INTO session_message VALUES (
  'msg_v2asst0001', 'ses_v2demo0002', 'assistant', 2, 1790000310000, 1790000352000,
  json('{"agent":"build","model":{"id":"gpt-5.2-codex","providerID":"openai"},"content":[{"type":"text","id":"txt_01","text":"Patching package.json and the bin shim."}],"finish":"tool-calls","cost":0,"tokens":{"input":1810,"output":233,"reasoning":0,"cache":{"read":18880,"write":1280}},"time":{"created":1790000310000,"completed":1790000352000}}')
);

-- Call B: reasoning tokens, no cache write.
INSERT INTO session_message VALUES (
  'msg_v2asst0002', 'ses_v2demo0002', 'assistant', 3, 1790000360000, 1790000419000,
  json('{"agent":"build","model":{"id":"gpt-5.2-codex","providerID":"openai"},"content":[{"type":"reasoning","id":"rsn_01","text":"Check for other references to the old name."},{"type":"text","id":"txt_02","text":"Renamed. The tests still pass."}],"finish":"stop","cost":0,"tokens":{"input":2150,"output":279,"reasoning":900,"cache":{"read":0,"write":0}},"time":{"created":1790000360000,"completed":1790000419000}}')
);
