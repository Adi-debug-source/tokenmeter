-- A Kilo Code 7 database (kilo.db) as the source at e4833e5 (version 7.8.25)
-- writes it: table and column names from packages/core/src/session/sql.ts,
-- step-finish fields from packages/schema/src/v1/session.ts 241 to 286 and
-- session/processor.ts 612 to 721. Content invented. Expected figures in
-- expected.json beside this file.
PRAGMA journal_mode = WAL;

CREATE TABLE project (
  id text PRIMARY KEY NOT NULL,
  worktree text NOT NULL,
  vcs text,
  name text,
  time_created integer NOT NULL,
  time_updated integer NOT NULL,
  sandboxes text NOT NULL
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

-- seq is nullable in Kilo Code (a kilocode_change in sql.ts).
CREATE TABLE session_message (
  id text PRIMARY KEY NOT NULL,
  session_id text NOT NULL REFERENCES session(id) ON DELETE cascade,
  type text NOT NULL,
  seq integer,
  time_created integer NOT NULL,
  time_updated integer NOT NULL,
  data text NOT NULL
);

INSERT INTO project VALUES ('prj_shop01', '/home/dev/projects/shop', 'git', 'shop',
  1790000000000, 1790000000000, '[]');

-- Session 1, written by 7.8.25: steps carry time, so output excludes reasoning.
INSERT INTO session (id, project_id, parent_id, slug, directory, title, version, agent, model,
  time_created, time_updated) VALUES ('ses_kilomain0001', 'prj_shop01', NULL, 'tidy-cart',
  '/home/dev/projects/shop', 'Tidy the cart module', '7.8.25', 'code',
  '{"id":"claude-sonnet-4-5","providerID":"anthropic"}', 1790000000000, 1790000160000);
INSERT INTO message VALUES ('msg_k_user01', 'ses_kilomain0001', 1790000005000, 1790000005000,
  json('{"role":"user","time":{"created":1790000005000},"agent":"code","model":{"providerID":"anthropic","modelID":"claude-sonnet-4-5"}}'));
-- One assistant message, two steps (older loops ran several steps per message).
INSERT INTO message VALUES ('msg_k_asst01', 'ses_kilomain0001', 1790000006000, 1790000060000,
  json('{"role":"assistant","time":{"created":1790000006000,"completed":1790000060000},"parentID":"msg_k_user01","modelID":"claude-sonnet-4-5","providerID":"anthropic","mode":"code","agent":"code","path":{"cwd":"/home/dev/projects/shop","root":"/home/dev/projects/shop"},"cost":0.04,"tokens":{"total":26980,"input":2170,"output":455,"reasoning":480,"cache":{"read":21504,"write":2371}},"finish":"stop"}'));
INSERT INTO part VALUES ('prt_k_start01', 'msg_k_asst01', 'ses_kilomain0001', 1790000006100, 1790000006100,
  json('{"type":"step-start","snapshot":"a1b2c3","time":{"start":1790000006100}}'));
INSERT INTO part VALUES ('prt_k_step01', 'msg_k_asst01', 'ses_kilomain0001', 1790000030000, 1790000030000,
  json('{"type":"step-finish","reason":"tool-calls","snapshot":"d4e5f6","time":{"start":1790000006100,"end":1790000030000,"elapsed":23900},"cost":0.02,"tokens":{"total":6232,"input":4220,"output":287,"reasoning":0,"cache":{"read":0,"write":1725}}}'));
INSERT INTO part VALUES ('prt_k_text01', 'msg_k_asst01', 'ses_kilomain0001', 1790000031000, 1790000031000,
  json('{"type":"text","text":"Moved the totals into one helper.","time":{"start":1790000030500,"end":1790000031000}}'));
INSERT INTO part VALUES ('prt_k_step02', 'msg_k_asst01', 'ses_kilomain0001', 1790000060000, 1790000060000,
  json('{"type":"step-finish","reason":"stop","time":{"start":1790000030500,"end":1790000060000,"elapsed":29500},"cost":0.02,"tokens":{"total":26980,"input":2170,"output":455,"reasoning":480,"cache":{"read":21504,"write":2371}}}'));
-- A custom auto router sent this call to the user's own OpenAI provider; the row names it.
INSERT INTO message VALUES ('msg_k_asst02', 'ses_kilomain0001', 1790000070000, 1790000090000,
  json('{"role":"assistant","time":{"created":1790000070000,"completed":1790000090000},"parentID":"msg_k_user01","modelID":"kilo-auto/custom/fast-lane","providerID":"kilo","mode":"code","agent":"code","path":{"cwd":"/home/dev/projects/shop","root":"/home/dev/projects/shop"},"cost":0,"tokens":{"total":13550,"input":3100,"output":210,"reasoning":640,"cache":{"read":9600,"write":0}},"finish":"stop"}'));
INSERT INTO part VALUES ('prt_k_step03', 'msg_k_asst02', 'ses_kilomain0001', 1790000090000, 1790000090000,
  json('{"type":"step-finish","reason":"stop","time":{"start":1790000070100,"end":1790000090000,"elapsed":19900},"model":{"providerID":"openai","modelID":"gpt-5.2-codex"},"cost":0,"tokens":{"total":13550,"input":3100,"output":210,"reasoning":640,"cache":{"read":9600,"write":0}}}'));
-- Through Kilo's own gateway, which serves several makers: no table.
INSERT INTO message VALUES ('msg_k_asst03', 'ses_kilomain0001', 1790000100000, 1790000120000,
  json('{"role":"assistant","time":{"created":1790000100000,"completed":1790000120000},"parentID":"msg_k_user01","modelID":"anthropic/claude-sonnet-4.5","providerID":"kilo","mode":"code","agent":"code","path":{"cwd":"/home/dev/projects/shop","root":"/home/dev/projects/shop"},"cost":0.01,"tokens":{"total":13620,"input":1500,"output":120,"reasoning":0,"cache":{"read":12000,"write":0}},"finish":"stop"}'));
INSERT INTO part VALUES ('prt_k_step04', 'msg_k_asst03', 'ses_kilomain0001', 1790000120000, 1790000120000,
  json('{"type":"step-finish","reason":"stop","time":{"start":1790000100100,"end":1790000120000,"elapsed":19900},"generationID":"gen_01kexample","cost":0.01,"tokens":{"total":13620,"input":1500,"output":120,"reasoning":0,"cache":{"read":12000,"write":0}}}'));
-- The model changes mid-session, to a plan route that serves one maker.
INSERT INTO message VALUES ('msg_k_asst04', 'ses_kilomain0001', 1790000130000, 1790000150000,
  json('{"role":"assistant","time":{"created":1790000130000,"completed":1790000150000},"parentID":"msg_k_user01","modelID":"glm-5.1","providerID":"zai-coding-plan","mode":"code","agent":"code","path":{"cwd":"/home/dev/projects/shop","root":"/home/dev/projects/shop"},"cost":0,"tokens":{"total":0,"input":0,"output":0,"reasoning":0,"cache":{"read":0,"write":0}},"finish":"error"}'));
INSERT INTO part VALUES ('prt_k_step05', 'msg_k_asst04', 'ses_kilomain0001', 1790000140000, 1790000140000,
  json('{"type":"step-finish","reason":"tool-calls","time":{"start":1790000130100,"end":1790000140000,"elapsed":9900},"cost":0,"tokens":{"total":7700,"input":5000,"output":400,"reasoning":300,"cache":{"read":2000,"write":0}}}'));
-- A step with no usage.
INSERT INTO part VALUES ('prt_k_step06', 'msg_k_asst04', 'ses_kilomain0001', 1790000150000, 1790000150000,
  json('{"type":"step-finish","reason":"error","time":{"start":1790000140100,"end":1790000150000,"elapsed":9900},"cost":0,"tokens":{"input":0,"output":0,"reasoning":0,"cache":{"read":0,"write":0}}}'));
-- Partial records: a step-finish with no tokens, and one that is not JSON.
INSERT INTO message VALUES ('msg_k_asst05', 'ses_kilomain0001', 1790000160000, 1790000160000,
  json('{"role":"assistant","time":{"created":1790000160000},"parentID":"msg_k_user01","modelID":"claude-sonnet-4-5","providerID":"anthropic","mode":"code","agent":"code","path":{"cwd":"/home/dev/projects/shop","root":"/home/dev/projects/shop"},"cost":0,"tokens":{"input":0,"output":0,"reasoning":0,"cache":{"read":0,"write":0}}}'));
INSERT INTO part VALUES ('prt_k_step07', 'msg_k_asst05', 'ses_kilomain0001', 1790000160500, 1790000160500,
  json('{"type":"step-finish","reason":"stop","cost":0}'));
INSERT INTO part VALUES ('prt_k_step08', 'msg_k_asst05', 'ses_kilomain0001', 1790000160600, 1790000160600,
  '{"type":"step-finish","reason":"stop","tokens":{"input":12');

-- Session 2, a fork of session 1 made later: the first message and its steps
-- copied under new ids, cost set to 0, every other field kept; then one new call.
INSERT INTO session (id, project_id, parent_id, slug, directory, title, version, agent, model,
  time_created, time_updated) VALUES ('ses_kilofork0001', 'prj_shop01', NULL, 'tidy-cart-fork',
  '/home/dev/projects/shop', 'Tidy the cart module (fork #1)', '7.8.25', 'code',
  '{"id":"claude-sonnet-4-5","providerID":"anthropic"}', 1790000200000, 1790000230000);
INSERT INTO message VALUES ('msg_k_fork_u01', 'ses_kilofork0001', 1790000005000, 1790000200001,
  json('{"role":"user","time":{"created":1790000005000},"agent":"code","model":{"providerID":"anthropic","modelID":"claude-sonnet-4-5"}}'));
INSERT INTO message VALUES ('msg_k_fork_a01', 'ses_kilofork0001', 1790000006000, 1790000200002,
  json('{"role":"assistant","time":{"created":1790000006000,"completed":1790000060000},"parentID":"msg_k_fork_u01","modelID":"claude-sonnet-4-5","providerID":"anthropic","mode":"code","agent":"code","path":{"cwd":"/home/dev/projects/shop","root":"/home/dev/projects/shop"},"cost":0,"tokens":{"total":26980,"input":2170,"output":455,"reasoning":480,"cache":{"read":21504,"write":2371}},"finish":"stop"}'));
INSERT INTO part VALUES ('prt_k_fork01', 'msg_k_fork_a01', 'ses_kilofork0001', 1790000200003, 1790000200003,
  json('{"type":"step-start","snapshot":"a1b2c3","time":{"start":1790000006100}}'));
INSERT INTO part VALUES ('prt_k_fork02', 'msg_k_fork_a01', 'ses_kilofork0001', 1790000200004, 1790000200004,
  json('{"type":"step-finish","reason":"tool-calls","snapshot":"d4e5f6","time":{"start":1790000006100,"end":1790000030000,"elapsed":23900},"cost":0,"tokens":{"total":6232,"input":4220,"output":287,"reasoning":0,"cache":{"read":0,"write":1725}}}'));
INSERT INTO part VALUES ('prt_k_fork03', 'msg_k_fork_a01', 'ses_kilofork0001', 1790000200005, 1790000200005,
  json('{"type":"text","text":"Moved the totals into one helper.","time":{"start":1790000030500,"end":1790000031000}}'));
INSERT INTO part VALUES ('prt_k_fork04', 'msg_k_fork_a01', 'ses_kilofork0001', 1790000200006, 1790000200006,
  json('{"type":"step-finish","reason":"stop","time":{"start":1790000030500,"end":1790000060000,"elapsed":29500},"cost":0,"tokens":{"total":26980,"input":2170,"output":455,"reasoning":480,"cache":{"read":21504,"write":2371}}}'));
INSERT INTO message VALUES ('msg_k_fork_u02', 'ses_kilofork0001', 1790000209000, 1790000209000,
  json('{"role":"user","time":{"created":1790000209000},"agent":"code","model":{"providerID":"anthropic","modelID":"claude-sonnet-4-5"}}'));
INSERT INTO message VALUES ('msg_k_fork_a02', 'ses_kilofork0001', 1790000210000, 1790000230000,
  json('{"role":"assistant","time":{"created":1790000210000,"completed":1790000230000},"parentID":"msg_k_fork_u02","modelID":"claude-sonnet-4-5","providerID":"anthropic","mode":"code","agent":"code","path":{"cwd":"/home/dev/projects/shop","root":"/home/dev/projects/shop"},"cost":0.01,"tokens":{"total":27190,"input":800,"output":90,"reasoning":0,"cache":{"read":26000,"write":300}},"finish":"stop"}'));
INSERT INTO part VALUES ('prt_k_fork05', 'msg_k_fork_a02', 'ses_kilofork0001', 1790000230000, 1790000230000,
  json('{"type":"step-finish","reason":"stop","time":{"start":1790000210100,"end":1790000230000,"elapsed":19900},"cost":0.01,"tokens":{"total":27190,"input":800,"output":90,"reasoning":0,"cache":{"read":26000,"write":300}}}'));

-- Session 3, a subagent's session (parent_id set by the task tool).
INSERT INTO session (id, project_id, parent_id, slug, directory, title, version, agent, model,
  time_created, time_updated) VALUES ('ses_kilochild001', 'prj_shop01', 'ses_kilomain0001', 'find-callers',
  '/home/dev/projects/shop', 'Find the callers (@explore subagent)', '7.8.25', 'explore',
  '{"id":"deepseek-v4-flash","providerID":"deepseek"}', 1790000080000, 1790000095000);
INSERT INTO message VALUES ('msg_k_child_a01', 'ses_kilochild001', 1790000081000, 1790000095000,
  json('{"role":"assistant","time":{"created":1790000081000,"completed":1790000095000},"parentID":"msg_k_child_u01","modelID":"deepseek-v4-flash","providerID":"deepseek","mode":"explore","agent":"explore","path":{"cwd":"/home/dev/projects/shop","root":"/home/dev/projects/shop"},"cost":0,"tokens":{"total":36500,"input":6000,"output":300,"reasoning":200,"cache":{"read":30000,"write":0}},"finish":"stop"}'));
INSERT INTO part VALUES ('prt_k_child01', 'msg_k_child_a01', 'ses_kilochild001', 1790000095000, 1790000095000,
  json('{"type":"step-finish","reason":"stop","time":{"start":1790000081100,"end":1790000095000,"elapsed":13900},"cost":0,"tokens":{"total":36500,"input":6000,"output":300,"reasoning":200,"cache":{"read":30000,"write":0}}}'));

-- Session 4, written by 7.2.3 (April 2026): steps carry no time, and AI SDK 5
-- put reasoning inside output for OpenAI and outside it for Google.
INSERT INTO session (id, project_id, parent_id, slug, directory, title, version, agent, model,
  time_created, time_updated) VALUES ('ses_kiloold00001', 'prj_shop01', NULL, 'add-coupons',
  '/home/dev/projects/shop', 'Add coupon codes', '7.2.3', 'code',
  '{"id":"gpt-5.1","providerID":"openai"}', 1776000000000, 1776000100000);
INSERT INTO message VALUES ('msg_k_old_a01', 'ses_kiloold00001', 1776000010000, 1776000050000,
  json('{"role":"assistant","time":{"created":1776000010000,"completed":1776000050000},"parentID":"msg_k_old_u01","modelID":"gpt-5.1","providerID":"openai","mode":"code","agent":"code","path":{"cwd":"/home/dev/projects/shop","root":"/home/dev/projects/shop"},"cost":0.01,"tokens":{"total":4900,"input":3000,"output":900,"reasoning":600,"cache":{"read":1000,"write":0}},"finish":"stop"}'));
-- total = input + cache + output: reasoning is inside output.
INSERT INTO part VALUES ('prt_k_old01', 'msg_k_old_a01', 'ses_kiloold00001', 1776000030000, 1776000030000,
  json('{"type":"step-finish","reason":"stop","cost":0.01,"tokens":{"total":4900,"input":3000,"output":900,"reasoning":600,"cache":{"read":1000,"write":0}}}'));
INSERT INTO message VALUES ('msg_k_old_a02', 'ses_kiloold00001', 1776000060000, 1776000080000,
  json('{"role":"assistant","time":{"created":1776000060000,"completed":1776000080000},"parentID":"msg_k_old_u01","modelID":"gemini-3.1-pro-preview","providerID":"google","mode":"code","agent":"code","path":{"cwd":"/home/dev/projects/shop","root":"/home/dev/projects/shop"},"cost":0.01,"tokens":{"total":2756,"input":2000,"output":500,"reasoning":256,"cache":{"read":0,"write":0}},"finish":"stop"}'));
-- total = input + cache + output + reasoning: reasoning is outside output.
INSERT INTO part VALUES ('prt_k_old02', 'msg_k_old_a02', 'ses_kiloold00001', 1776000070000, 1776000070000,
  json('{"type":"step-finish","reason":"stop","cost":0.01,"tokens":{"total":2756,"input":2000,"output":500,"reasoning":256,"cache":{"read":0,"write":0}}}'));
INSERT INTO message VALUES ('msg_k_old_a03', 'ses_kiloold00001', 1776000085000, 1776000099000,
  json('{"role":"assistant","time":{"created":1776000085000,"completed":1776000099000},"parentID":"msg_k_old_u01","modelID":"gpt-5.1","providerID":"openai","mode":"code","agent":"code","path":{"cwd":"/home/dev/projects/shop","root":"/home/dev/projects/shop"},"cost":0.01,"tokens":{"input":700,"output":50,"reasoning":0,"cache":{"read":0,"write":0}},"finish":"stop"}'));
-- No total and reasoning present: cannot be settled, so not counted.
INSERT INTO part VALUES ('prt_k_old03', 'msg_k_old_a03', 'ses_kiloold00001', 1776000090000, 1776000090000,
  json('{"type":"step-finish","reason":"tool-calls","cost":0.01,"tokens":{"input":1200,"output":300,"reasoning":100,"cache":{"read":0,"write":0}}}'));
-- No total but no reasoning either: nothing to settle.
INSERT INTO part VALUES ('prt_k_old04', 'msg_k_old_a03', 'ses_kiloold00001', 1776000099000, 1776000099000,
  json('{"type":"step-finish","reason":"stop","cost":0.01,"tokens":{"input":700,"output":50,"reasoning":0,"cache":{"read":0,"write":0}}}'));

-- Session 5, session 4 forked by 7.8.25 in September: its rows are dated when copied.
INSERT INTO session (id, project_id, parent_id, slug, directory, title, version, agent, model,
  time_created, time_updated) VALUES ('ses_kilooldfork1', 'prj_shop01', NULL, 'add-coupons-fork',
  '/home/dev/projects/shop', 'Add coupon codes (fork #1)', '7.8.25', 'code',
  '{"id":"gpt-5.1","providerID":"openai"}', 1790000300000, 1790000300010);
INSERT INTO message VALUES ('msg_k_oldfork_a01', 'ses_kilooldfork1', 1776000010000, 1790000300001,
  json('{"role":"assistant","time":{"created":1776000010000,"completed":1776000050000},"parentID":"msg_k_oldfork_u01","modelID":"gpt-5.1","providerID":"openai","mode":"code","agent":"code","path":{"cwd":"/home/dev/projects/shop","root":"/home/dev/projects/shop"},"cost":0,"tokens":{"total":4900,"input":3000,"output":900,"reasoning":600,"cache":{"read":1000,"write":0}},"finish":"stop"}'));
INSERT INTO part VALUES ('prt_k_oldfork01', 'msg_k_oldfork_a01', 'ses_kilooldfork1', 1790000300002, 1790000300002,
  json('{"type":"step-finish","reason":"stop","cost":0,"tokens":{"total":4900,"input":3000,"output":900,"reasoning":600,"cache":{"read":1000,"write":0}}}'));
INSERT INTO message VALUES ('msg_k_oldfork_a03', 'ses_kilooldfork1', 1776000085000, 1790000300003,
  json('{"role":"assistant","time":{"created":1776000085000,"completed":1776000099000},"parentID":"msg_k_oldfork_u01","modelID":"gpt-5.1","providerID":"openai","mode":"code","agent":"code","path":{"cwd":"/home/dev/projects/shop","root":"/home/dev/projects/shop"},"cost":0,"tokens":{"input":700,"output":50,"reasoning":0,"cache":{"read":0,"write":0}},"finish":"stop"}'));
INSERT INTO part VALUES ('prt_k_oldfork03', 'msg_k_oldfork_a03', 'ses_kilooldfork1', 1790000300004, 1790000300004,
  json('{"type":"step-finish","reason":"tool-calls","cost":0,"tokens":{"input":1200,"output":300,"reasoning":100,"cache":{"read":0,"write":0}}}'));
INSERT INTO part VALUES ('prt_k_oldfork04', 'msg_k_oldfork_a03', 'ses_kilooldfork1', 1790000300005, 1790000300005,
  json('{"type":"step-finish","reason":"stop","cost":0,"tokens":{"input":700,"output":50,"reasoning":0,"cache":{"read":0,"write":0}}}'));

-- Session 6, through the event-sourced /api/session routes (session_message).
INSERT INTO session (id, project_id, parent_id, slug, directory, title, version, agent, model,
  time_created, time_updated) VALUES ('ses_kilov2000001', 'prj_shop01', NULL, 'readme-typo',
  '/home/dev/projects/shop', 'Fix a README typo', '7.8.25', 'code',
  '{"id":"claude-haiku-4-5","providerID":"anthropic"}', 1790000400000, 1790000420000);
INSERT INTO session_message VALUES ('msg_k_v2user01', 'ses_kilov2000001', 'user', 1, 1790000405000, 1790000405000,
  json('{"text":"Fix the typo in the README.","files":[],"agents":[],"time":{"created":1790000405000}}'));
INSERT INTO session_message VALUES ('msg_k_v2asst01', 'ses_kilov2000001', 'assistant', 2, 1790000410000, 1790000420000,
  json('{"agent":"code","model":{"id":"claude-haiku-4-5","providerID":"anthropic"},"content":[],"finish":"stop","cost":0,"tokens":{"input":900,"output":60,"reasoning":0,"cache":{"read":0,"write":0}},"time":{"created":1790000410000,"completed":1790000420000}}'));
