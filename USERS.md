# USERS.md — Clinical Co-Pilot

## Target User

**Dr. M, a primary care physician (PCP) in a mid-sized outpatient clinic.**

- Panel of approximately 1,800 patients.
- Sees 18-22 patients per day in 15-minute slots, plus message-based work between visits.
- Visit mix: acute complaints, chronic disease management (diabetes, hypertension, hyperlipidemia, depression are the dominant ones), preventive care, and post-discharge follow-ups.
- Most patients on the day's schedule are returning patients. Dr. M has seen them before, often multiple times, but cannot reliably recall the specifics of every patient's history, recent labs, or last visit's plan.
- Charts in OpenEMR. Time pressure is steady-state rather than acute: there is no single emergency, but every minute spent re-reading notes is a minute not spent looking at the patient.

### Why this user, and not another

The case study offers three example users — PCP, ED resident, hospitalist — and an ICU intensivist was considered as well. The PCP was selected because:

1. **Best fit with OpenEMR's data model.** OpenEMR is primarily an ambulatory (outpatient) EHR. Its native data structures — appointments with reasons, problem lists, encounter notes, prescription-oriented medication records, lab results — naturally support the PCP workflow. ICU and ED workflows would require fabricating data structures (continuous vitals, vasoactive drips, ED triage data) that OpenEMR does not represent, burning a meaningful share of the one-week build budget on data plumbing rather than agent work.
2. **Cleanest demo narrative.** The 90-seconds-between-rooms scenario is universally recognizable and matches the case study's opening framing.
3. **Strongest justification for an agent over a dashboard.** The relevance of "what matters today" depends on visit context the user supplies in conversation. A static dashboard cannot do this; a conversational agent can.

### What this user is *not*

This user is not a generalized "physician." Specialty providers (cardiology, oncology, etc.), nurses, residents under supervision, and front-desk staff have different workflows and different agent needs. They are out of scope for v1 — though the system's authorization model is designed to accommodate role-based differentiation in the future.

---

## The Workflow Moment

The agent is designed around four moments in Dr. M's day:

1. **Pre-room (primary).** Patient is roomed by the medical assistant. Dr. M is at the workstation outside the room, with 60-90 seconds before walking in. The chart is open. The agent is asked: *what do I need to know about this visit?*

2. **Mid-visit, factual.** During the encounter, a question arises that requires a specific factual answer from the patient's record (a date, a dose, a value). Dr. M asks the agent rather than spelunking through the chart, which would break attention from the patient.

3. **Mid-visit, pivot.** During the encounter, the patient raises a concern that was not the stated reason for visit. Dr. M asks the agent for context on the new topic, and the agent reasons over the relevant history.

4. **Post-visit recap.** After the encounter, before closing the chart, Dr. M reviews the agent's recap of what happened and what's pending. The agent does not write the note; it reasons over what Dr. M captured during the visit and helps Dr. M verify that nothing was missed.

---

## Use Cases

Each use case below traces to one of the four workflow moments above. Each capability the agent ships in v1 must trace to one of these use cases. If a future capability cannot be traced to a use case here, this document is updated first.

### Use Case 1 — Pre-room briefing

**Moment:** 60-90 seconds before entering the exam room.

**Trigger:** Dr. M opens the patient's chart in OpenEMR and invokes the agent.

**Agent inputs:**
- Today's appointment, including the patient-stated reason for visit (when present).
- The patient's active problem list, with chronic conditions surfaced regardless of today's visit reason.
- Recent encounters (typically the last 1-3, depending on density).
- Recent lab results (typically the last 90 days for relevant chronic conditions; broader on request).
- Recent medication changes.
- Any open follow-up items flagged at prior visits.

**Agent output:** A tight, structured summary Dr. M can absorb in roughly 30 seconds. The summary surfaces (a) what today's visit appears to be about, (b) what's changed since the last visit, and (c) anything on the active problem list that warrants attention even if it's not today's reason.

**Treatment of the patient-stated reason for visit:** The patient-stated reason is treated as an *input signal* that shapes relevance, not as ground truth about the encounter. The agent surfaces it explicitly to Dr. M ("the patient indicated they're here for X") rather than acting on it silently. Dr. M confirms or corrects the actual reason in the room.

**Why an agent, not a dashboard:** The relevant context depends on *why this patient is here today*. A diabetic coming in for a knee injury and a diabetic coming in for diabetes follow-up need different summaries. A static dashboard would either show too much (overwhelming the 90-second window) or the wrong things. The agent uses the visit reason and chronic-condition context to filter to relevance.

### Use Case 2 — Mid-visit factual lookup

**Moment:** During the encounter, with the patient present.

**Trigger:** A question arises during conversation. Examples: "When did we last check her TSH?", "What dose of metformin is she on?", "Has she had a colonoscopy?"

**Agent inputs:** The specific question, plus full read access to the patient's record.

**Agent output:** A direct factual answer, with a citation to the source record (encounter, lab order, medication entry). Optimized for low latency — the goal is for Dr. M to get the answer without disengaging from the patient.

**Why an agent, not a search bar:** The PCP's question is in natural language and often depends on context already established in the conversation ("when did we last check it?" — meaning the lab they were just discussing). A keyword search requires the PCP to translate intent into query terms and parse a results list; the agent answers the question directly.

### Use Case 3 — Mid-visit pivot

**Moment:** During the encounter, when the patient raises a concern outside the planned visit reason.

**Trigger:** "By the way, I've been having these headaches for three months." Dr. M asks the agent for relevant history on the new topic.

**Agent inputs:** The new topic, plus full read access to the patient's record. Chronic conditions on the active problem list remain in working context.

**Agent output:** Focused context on the new concern — prior workup if any, related medications, related family history, prior similar complaints. Multi-turn capable: Dr. M may ask follow-ups ("any imaging?", "did we ever try a beta-blocker?").

**Why an agent, not a search bar:** This is fundamentally a multi-turn reasoning task. The first answer informs the next question, and the relevance of the second answer depends on what was found in the first. This use case is the cleanest justification for multi-turn conversation as a required capability.

### Use Case 4 — Post-visit recap

**Moment:** After the encounter, before Dr. M closes the chart and moves to the next patient.

**Trigger:** Dr. M asks the agent to recap the visit.

**Agent inputs:** The encounter content as captured by Dr. M during the visit (typed notes, structured fields, or other inputs OpenEMR supports), plus the patient's broader record for context.

**Agent output:** A structured recap with two parts:

- **What happened.** The agent's understanding of the encounter: visit reason as it evolved during the visit, what was discussed, what was assessed, what was decided. Dr. M confirms or corrects.
- **What's pending.** Unresolved items from the visit: labs ordered awaiting results, referrals placed, follow-up appointments discussed, medication changes that require pharmacy action, anything Dr. M flagged as "revisit next time."

**Important constraint:** The agent does **not** generate the visit's clinical note, and does **not** write to the medical record. It reasons over what Dr. M has captured and surfaces it for verification. Generating clinical documentation that lands in the legal medical record is a separate, harder problem with a different verification surface, and it is deliberately out of scope for v1.

**Why an agent, not a checklist:** The pending-items list cannot be hand-written in advance — it depends on what was actually discussed and ordered during the visit. The recap requires reasoning over the visit's events, not just displaying a static template.

**Limitation worth naming:** The recap can only reflect what Dr. M has captured. If little is typed during the visit, the recap will be thin. This is an honest property of any EHR-based agent and is communicated transparently rather than disguised.

---

## How the use cases compound

The four use cases are not independent — they form a flywheel across visits.

UC3 (mid-visit pivot) often produces new clinical content: a new symptom is documented, a new condition is assessed, a new medication is started, a new follow-up is planned. UC4 (post-visit recap) helps Dr. M verify that this content was captured before closing the chart. None of this content is written by the agent — Dr. M types or dictates it into OpenEMR using OpenEMR's existing interfaces, the same way they would without the agent.

At the next visit, that content is part of the patient's record. UC1's pre-room briefing reads it, surfaces it as part of the active problem list, and treats it with the same chronic-condition awareness as any other condition. Today's documented visit becomes tomorrow's input.

The agent's read-only constraint is preserved throughout. The chart grows because humans write to it through OpenEMR; the agent never writes anything, but it reads more each time because more has accumulated.

---

## Scope and Non-Goals (v1)

In scope:
- The four use cases above, all for a single user role (PCP).
- Read-only agent. The agent reads the patient record and reasons over it; it does not write notes, place orders, or modify chart data. The patient record continues to be updated by humans (PCPs, nurses, lab interfaces, pharmacy systems) through OpenEMR's existing interfaces, exactly as it would be without the agent. The agent reads the current state of the record at the moment of each query.
- Patient-stated reason for visit treated as untrusted input — surfaced to Dr. M as a signal, not acted on as ground truth, and handled with awareness that free-text patient input is a prompt injection surface.
- HIPAA-aware architecture. Every architectural decision in v1 is consistent with HIPAA's Security and Privacy Rules, and no decision creates compliance debt that a production deployment would have to undo. v1 does not claim certified HIPAA compliance — that posture requires signed BAAs, formal risk assessment, breach notification procedures, workforce training, physical safeguards, and ongoing audit, none of which are in scope for a one-week academic build. Per the case study's standing assumption, BAAs with LLM providers are treated as in place. Detailed compliance treatment lives in AUDIT.md and ARCHITECTURE.md.

### Handling information gaps

When the patient's record is silent on a topic, the agent reports the silence rather than filling it. "No prior headache complaints documented in the record" is a valid and useful answer — it tells Dr. M that this is a new presentation, not a recurrence, and Dr. M's clinical reasoning can proceed on that basis. The agent does not infer, speculate, or pull in medical knowledge from outside the record to fill gaps. New conditions raised or diagnosed during today's visit are handled via UC4 (post-visit recap) and become part of the record the agent reads at future visits, per the flywheel above.

Explicitly out of scope for v1 (some likely future work):
- **Other user roles.** Nurses, residents, specialists, and administrative staff are not v1 agent users. Notes they author in OpenEMR are read by the agent; they do not interact with the agent directly. The authorization model is designed to support role-based differentiation later.
- **Write capabilities.** No agent-generated chart notes, no agent-placed orders, no agent-sent messages. All write actions remain with Dr. M.
- **Inbox / message triage.** End-of-day inbox work (lab results, refill requests, patient messages) is a different workflow with a different shape and is not a v1 use case.
- **Medical knowledge Q&A.** The agent answers questions grounded in *this patient's* record. It is not a generalized medical reference and will redirect general medical knowledge questions.
- **Cross-patient queries.** The agent operates on one patient at a time. Panel-level or cohort-level queries ("show me all my diabetics with A1c > 9") are out of scope.

---

## Traceability

| Agent capability | Justified by use case |
|---|---|
| Multi-turn conversation | UC3 (mid-visit pivot), UC4 (recap follow-ups) |
| Tool calling for record retrieval | UC1, UC2, UC3 |
| Source citation on every claim | All UCs (verification requirement) |
| Visit-reason awareness | UC1, UC4 |
| Chronic condition awareness regardless of visit reason | UC1, UC3 |
| Low-latency factual lookup | UC2 |
| Reasoning over visit events (not just records) | UC4 |
| Graceful handling of record silence (no inference, no speculation) | All UCs (verification requirement; "Handling information gaps") |
| HIPAA-aware data handling, audit logging, role-based access | All UCs (Scope: HIPAA-aware architecture) |

ARCHITECTURE.md will reference this table. Any agent capability built that does not appear in this table is either an omission to be added here, or a scope creep to be cut.
