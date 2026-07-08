# Skill loading — local vs cloud agents (future-facing)

> Status: **prepared, not deployed.** The skill content is complete and
> usable locally today. This note records how it will reach *cloud*
> agents later, so the structure is ready. Nothing here is wired up yet.

The same `dcc-control` skill must reach two kinds of agent, which load
skills differently:

## 1. Local agents (works today)

A local agent (e.g. Claude Code running on the same machine as the
daemon) reads the skill straight from the repo / a skills directory on
disk. No packaging, no upload. Point the agent at `skills/dcc-control/`
(or symlink/copy it into the agent's skills path). `SKILL.md` is the
entry; `references/` load on demand.

## 2. Cloud / internal agents (future)

An internal cloud agent cannot see this repo. The plan:

1. **Package** `skills/dcc-control/` into a versioned zip
   (`dcc-control-<version>.zip`) containing `SKILL.md` + `references/`.
2. **Upload** it to an internal object store (COS bucket).
3. The agent runtime, given the **manifest** (`packaging/manifest.json`)
   pointing at `bucket` + `object_key`, **downloads and unpacks** the zip
   at load time.

Two things vary per cloud runtime and must be filled in at deploy time
(placeholders in `manifest.json`):

- **`bucket` / `object_key`** — where the zip lives.
- **`agent_name`** — the skill's registered name differs between agent
  runtimes; map it in the manifest's `targets.cloud.agent_name`.

## What is intentionally deferred

- The actual zip build + upload tooling.
- COS credentials / bucket provisioning.
- Wiring the manifest into whatever loader each cloud runtime uses.

When we do deploy, the skill content should not need to change — only
the `targets` block in `manifest.json` and a small build/upload step.
Keep the skill self-contained (relative `references/` links only, no
absolute repo paths) so zipping it stays trivial.
