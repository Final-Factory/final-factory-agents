---
name: test-an-ffbox-agent-class-from-ff-factory
description: How a test turn reaches each FFBox agent class (ffdev, ffagent, ffdiagnose), and which routes FF Factory's dev hand-over swallows
type: project
---

# Testing an FFBox agent class from FF Factory

w2823 (lothsahn, 2026-11-01) ran one test turn per class on FFBox to measure the headless Unity editor. Three of its
routes failed. These facts come from ffbox master 3cf2986 (`scripts/ffwatch.py` unless named):

- **An operator's ffdev turn is handed to FF Factory while `fff.dev_requests` is "prefer"** (`fff_dev_gate`,
  27640-27735). That includes the ffweb prompt box. The box submits as the Unix account that runs ffweb
  (`ffweb.py:1897`; every unit runs as one `@USER@`, `systemd/ffweb.service:59`), and the gate maps that account
  through the operators' `shell` ids (27631-27637). On FFBox it maps to lothsahn: web conversation 1489 was handed over
  as w2828. A terminal `ffwatch submit` as that same account is handed over too. Only an account the operators block
  doesn't name is skipped as `no_operator` (27693-27698).
- **A reply in a thread FF Factory already took goes to FF Factory as a follow-up.** It counts as a follow-up when the
  same operator writes in a dev-linked conversation (27712-27713), and that test comes before the class check
  (27726-27735).
- **ffagent and ffdiagnose turns are never handed over** (27728-27735, "only ffdev turns are handed over").
- **A Discord message can't pick its class.** The author decides it: operators get `operator_pool` (ffdev), everyone
  else gets `user_pool` (ffagent) (`discord_agent_class`, 2968-2980). ffdiagnose comes only from crash, desync and hang
  intake (1043-1044). Typed turns get theirs from the ffweb agent selector or `ffwatch submit --agent`.
- **A typed turn carries no file.** The web form has only a prompt and an agent picker, and `ffwatch submit` has no
  attachment option. A later turn in the same conversation does see earlier messages' files under `/ffbox/attachments`
  (`history`/`older_attachments`, 14230-14235). For a save, use one every checkout already has
  (`Assets/Tests/Serialization/Fixtures/`).
- **FF Factory can't flip `fff.dev_requests`.** `set_config` changes only `ffbox_settings.LIVE`, which holds the two
  subscription holds (`ffbox_settings.py:42-50`, refused at 76). Editing config.json restarts ffwatch through the
  updater's config hash, after running turns drain (`update_ffbox.sh:366-426`, 1362). Switching hand-over off is
  lothsahn's decision and his step at the box; don't push an ffbox change to get around it (w2823: he asked for
  "no unilateral way into machines").

**How to apply:** for an ffdev test, first ask lothsahn whether hand-over goes off for it, or which unlisted account
types it. Submit the ffagent and ffdiagnose turns from the web page. Pick the save from the fixtures.
