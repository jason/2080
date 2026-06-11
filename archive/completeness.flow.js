// 2080 completeness engine as a rally-flow consumer.
// It does not try to guess future bugs. It derives missing dimensions from
// intent, runs checks against the day-1 artifact, asks what dimension is still
// unexamined, and refuses completion while coverage is open.
export const meta = {
  name: "completeness-2080",
  description: "Derive intent-implied completeness dimensions, search for gaps, loop until dry, then gate completion.",
  whenToUse:
    "Use on a day-1 implementation or plan when you need the second-85% surface made explicit before calling it done.",
  phases: [
    { title: "Orient" },
    { title: "Derive" },
    { title: "Search" },
    { title: "Refute" },
    { title: "Score" },
    { title: "Gate" },
  ],
};

const DEFAULT_INPUT = {
  app_type: "web application",
  project: "unknown",
  intent: "Add a user logout button.",
  day1_artifact:
    "A user-visible logout button exists and clears browser-local auth state on the happy path.",
  corpus_priors: [
    "failure modes",
    "edge cases",
    "integration contracts",
    "non-functional requirements",
    "server-side authority",
    "operability",
  ],
  max_loops: 2,
  primary_harness: null,
  secondary_harness: null,
  answer_key: null,
  min_answer_key_recall: 0.6,
};

const input = Object.assign({}, DEFAULT_INPUT, args || {});
const maxLoops = Math.max(1, Math.min(Number(input.max_loops || 2), 5));
const primaryHarness = input.primary_harness || null;
const secondaryHarness = input.secondary_harness || primaryHarness;
const answerKey = input.answer_key || input.harvest_answer_key || null;
const minAnswerKeyRecall = Number(input.min_answer_key_recall || 0.6);

function agentOptions(label, schema, harness) {
  const opts = { label, schema };
  if (harness) opts.harness = harness;
  return opts;
}

const ORIENTATION = {
  type: "object",
  properties: {
    summary: { type: "string" },
    core_job: { type: "string" },
    primary_subjects: { type: "array", items: { type: "string" } },
    boundaries: { type: "array", items: { type: "string" } },
    dangerous_assumptions: { type: "array", items: { type: "string" } },
  },
  required: ["summary", "core_job", "primary_subjects", "boundaries", "dangerous_assumptions"],
};

const DIMENSIONS = {
  type: "object",
  properties: {
    dimensions: {
      type: "array",
      items: {
        type: "object",
        properties: {
          id: { type: "string" },
          title: { type: "string" },
          source: { type: "string" },
          severity: { type: "string" },
          question: { type: "string" },
          day1_check: { type: "string" },
          evidence_needed: { type: "string" },
          rationale: { type: "string" },
        },
        required: [
          "id",
          "title",
          "source",
          "severity",
          "question",
          "day1_check",
          "evidence_needed",
          "rationale",
        ],
      },
    },
  },
  required: ["dimensions"],
};

const FINDINGS = {
  type: "object",
  properties: {
    findings: {
      type: "array",
      items: {
        type: "object",
        properties: {
          dimension_id: { type: "string" },
          status: { type: "string" },
          gap: { type: "string" },
          evidence: { type: "string" },
          next_check: { type: "string" },
        },
        required: ["dimension_id", "status", "gap", "evidence", "next_check"],
      },
    },
  },
  required: ["findings"],
};

const REFUTATION = {
  type: "object",
  properties: {
    missing_dimensions: DIMENSIONS.properties.dimensions,
    dry: { type: "boolean" },
    reason: { type: "string" },
  },
  required: ["missing_dimensions", "dry", "reason"],
};

const COVERAGE = {
  type: "object",
  properties: {
    ok: { type: "boolean" },
    cells: {
      type: "array",
      items: {
        type: "object",
        properties: {
          dimension_id: { type: "string" },
          title: { type: "string" },
          status: { type: "string" },
          blocking: { type: "boolean" },
          evidence: { type: "string" },
          required_next_step: { type: "string" },
        },
        required: ["dimension_id", "title", "status", "blocking", "evidence", "required_next_step"],
      },
    },
    verdict: { type: "string" },
  },
  required: ["ok", "cells", "verdict"],
};

const SCORE = {
  type: "object",
  properties: {
    evaluated: { type: "boolean" },
    recall_estimate: { type: "number" },
    matched_answer_key_items: {
      type: "array",
      items: {
        type: "object",
        properties: {
          answer_key_item: { type: "string" },
          matched_dimension_id: { type: "string" },
          match_strength: { type: "string" },
          rationale: { type: "string" },
        },
        required: ["answer_key_item", "matched_dimension_id", "match_strength", "rationale"],
      },
    },
    missed_answer_key_items: {
      type: "array",
      items: {
        type: "object",
        properties: {
          answer_key_item: { type: "string" },
          miss_reason: { type: "string" },
          falsifies_claim: { type: "boolean" },
        },
        required: ["answer_key_item", "miss_reason", "falsifies_claim"],
      },
    },
    verdict: { type: "string" },
  },
  required: ["evaluated", "recall_estimate", "matched_answer_key_items", "missed_answer_key_items", "verdict"],
};

function normalizeId(text) {
  return String(text || "dimension")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 64);
}

function mergeDimensions(groups) {
  const byId = new Map();
  for (const item of groups.flat()) {
    if (!item || !item.title) continue;
    const id = normalizeId(item.id || item.title);
    if (!byId.has(id)) byId.set(id, Object.assign({}, item, { id }));
  }
  return Array.from(byId.values());
}

phase("Orient");
const orientation = await agent(
  `Project: ${input.project}
App type: ${input.app_type}
Intent:
${input.intent}

Day-1 artifact or implementation claim:
${input.day1_artifact}

Summarize what the thing is for. Identify the product boundaries and assumptions
that would cause false completeness if left implicit.

Blind-test rule: use only the intent and day-1 artifact. Do not infer from any
later answer key or later work.`,
  agentOptions("orient-intent", ORIENTATION, primaryHarness),
);

phase("Derive");
const derivations = await parallel([
  () =>
    agent(
      `Use these corpus priors as seed categories, not as a fixed checklist:
${JSON.stringify(input.corpus_priors)}

Intent summary:
${JSON.stringify(orientation)}

Derive reusable completeness dimensions that this intent implies. Focus on
dimensions/checks, not specific predicted bugs. Emit dimensions that could be
verified on day 1.`,
      agentOptions("derive-from-corpus-priors", DIMENSIONS, primaryHarness),
    ),
  () =>
    agent(
      `Intent:
${input.intent}

Day-1 artifact:
${input.day1_artifact}

Derive project-specific dimensions implied by what this thing is for. Include
authority boundaries, teardown semantics, lifecycle/concurrency, hostile states,
and user-visible correctness. Do not rely on historical corpus transfer.`,
      agentOptions("derive-from-intent", DIMENSIONS, secondaryHarness),
    ),
  () =>
    agent(
      `App type: ${input.app_type}
Intent:
${input.intent}

Derive integration and operability dimensions: external systems, data stores,
identity/session authority, observability, rollback/recovery, deployment and
support surfaces. These are the things demos usually hide.`,
      agentOptions("derive-integration-ops", DIMENSIONS, primaryHarness),
    ),
]);

let dimensions = mergeDimensions(derivations.filter(Boolean).flatMap((d) => d.dimensions || []));
log(`derived ${dimensions.length} initial dimension(s)`);

phase("Search");
let findings = [];
let dryReason = "";
for (let loop = 1; loop <= maxLoops; loop++) {
  const activeDimensions = dimensions.slice(0, 24);
  const batches = [];
  for (let i = 0; i < activeDimensions.length; i += 6) {
    batches.push(activeDimensions.slice(i, i + 6));
  }

  const searchResults = await parallel(
    batches.map((batch, index) => () =>
      agent(
        `Loop ${loop}. Evaluate these completeness dimensions against the day-1 artifact.

Dimensions:
${JSON.stringify(batch, null, 2)}

Intent:
${input.intent}

Day-1 artifact:
${input.day1_artifact}

For each dimension, decide whether it is covered, open, unknown, or needs an
empirical check. Ground the answer in available evidence. Do not mark covered
unless the evidence would convince a skeptical reviewer.

Blind-test rule: evaluate only the day-1 artifact. If an answer key exists in
the workflow args, do not use it in this phase.`,
        agentOptions(`find-gaps-${loop}-${index}`, FINDINGS, index % 2 === 0 ? primaryHarness : secondaryHarness),
      ),
    ),
  );

  findings = findings.concat(searchResults.filter(Boolean).flatMap((r) => r.findings || []));

  phase("Refute");
  const refutation = await agent(
    `We are building a completeness engine, not a bug oracle.

Question: what DIMENSION has not yet been examined?

Intent:
${input.intent}

Orientation:
${JSON.stringify(orientation)}

Current dimensions:
${JSON.stringify(dimensions, null, 2)}

Current findings:
${JSON.stringify(findings, null, 2)}

Return only genuinely new missing dimensions. If every important dimension
implied by the intent has already been examined, set dry=true. Unknown-unknowns
that are not derivable from intent should be named only as empirical checks, not
fabricated as specific bugs.`,
    agentOptions(`refute-dimensions-${loop}`, REFUTATION, primaryHarness),
  );

  const additions = mergeDimensions([refutation?.missing_dimensions || []]).filter(
    (candidate) => !dimensions.some((existing) => existing.id === candidate.id),
  );
  if (additions.length === 0 || refutation?.dry === true) {
    dryReason = refutation?.reason || "no new intent-derived dimensions";
    log(`loop ${loop} dry: ${dryReason}`);
    break;
  }

  dimensions = mergeDimensions([dimensions, additions]);
  log(`loop ${loop} added ${additions.length} missing dimension(s)`);
  phase("Search");
}

phase("Score");
let score = {
  evaluated: false,
  recall_estimate: 0,
  matched_answer_key_items: [],
  missed_answer_key_items: [],
  verdict: "no answer key supplied; scoring skipped",
};
if (answerKey) {
  score = await agent(
    `Score the blind completeness pass against the harvest answer key.

This is NOT another derivation pass. The dimensions/findings below were produced
using only day-1 state. The answer key represents later work actually added.

Question: what fraction of later-added work did the blind pass predict as
dimensions/checks, even if it did not know the exact bug instance?

Intent:
${input.intent}

Day-1 artifact:
${input.day1_artifact}

Blind dimensions:
${JSON.stringify(dimensions, null, 2)}

Blind findings:
${JSON.stringify(findings, null, 2)}

Harvest answer key:
${JSON.stringify(answerKey, null, 2)}

Score semantic matches generously for dimensions/checks and strictly for mere
generic labels. A match is strong only if the blind pass named a check that
would plausibly surface the later-added work on day 1.`,
    agentOptions("score-against-answer-key", SCORE, primaryHarness),
  );
}

phase("Gate");
const coverage = await agent(
  `Decide whether completeness coverage is good enough to call this day-1 artifact done.

Intent:
${input.intent}

Dimensions:
${JSON.stringify(dimensions, null, 2)}

Findings:
${JSON.stringify(findings, null, 2)}

Dry-loop reason:
${dryReason}

Answer-key score:
${JSON.stringify(score, null, 2)}

Rules:
- ok=true only when every high-impact intent-derived dimension is covered by
  concrete evidence or has a deliberate, tracked empirical check.
- open, unknown, needs-evidence, and needs-empirical-check are blocking unless
  explicitly accepted as out of scope by the intent.
- if an answer key is supplied, ok=true also requires recall_estimate >=
  ${minAnswerKeyRecall}; otherwise this run falsifies the adaptive-search claim.
- The output cells are the worklist humans and agents should execute next.`,
  agentOptions("coverage-verdict", COVERAGE, primaryHarness),
);

const openGaps = (coverage?.cells || []).filter((cell) => cell.blocking !== false || cell.status !== "covered");
const scoreGaps =
  score?.evaluated === true && Number(score.recall_estimate || 0) < minAnswerKeyRecall
    ? [
        {
          dimension_id: "answer-key-recall",
          title: "Blind pass missed too much later-added work",
          status: "open",
          blocking: true,
          evidence: score.verdict,
          required_next_step: "Improve derivation/search prompts or reject the intent-derived 80% claim for this feature.",
        },
      ]
    : [];
await gate(
  () => ({
    ok: coverage?.ok === true && openGaps.length === 0 && scoreGaps.length === 0,
    openGaps: openGaps.concat(scoreGaps),
  }),
  { label: "completeness" },
);

return {
  input,
  orientation,
  dimensions,
  findings,
  score,
  coverage,
};
