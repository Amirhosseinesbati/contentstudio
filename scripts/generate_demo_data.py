"""Reproducible fictional ContentStudio scenarios. No model calls or network access.

The full dataset is generated from authored topic notes, not extracted from any
customer material. Evaluation answers are written outside the runtime fixtures.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
from datetime import date, timedelta
from pathlib import Path


TOPICS = [
    (
        "onboarding", "A calmer first 30 days for B2B onboarding", "customer onboarding",
        "A useful onboarding program removes ambiguity before it adds automation.",
        [
            ("the first handoff", "sales promises are sometimes compressed into a one-line note", "a fictional analytics buyer expected a migration plan but received only a login link", "put the promise, owner, and due date in the handoff record", "a detailed handoff is still useless if the buyer never confirms the goal"),
            ("the kickoff", "a kickoff can sound successful while leaving the next action vague", "the implementation lead and sponsor each thought the other would invite the data owner", "end with named owners and a written next checkpoint", "a rigid agenda can silence a buyer's unexpected concern"),
            ("the first value moment", "teams often track setup tasks rather than the buyer's first useful result", "a sandbox dashboard looked polished but used an irrelevant sample metric", "agree on a small result the customer can verify", "some outcomes depend on data the buyer has not yet supplied"),
            ("risk signals", "silence is often interpreted as satisfaction", "three unanswered access requests delayed the fictional pilot without appearing in the status report", "record blockers and ask a precise question before escalating", "a slow reply alone does not prove disengagement"),
            ("the correction loop", "early assumptions should be easy to revise", "the team first called training complete, then learned only one of four roles had attended", "change the status and explain the narrower evidence", "do not erase the earlier note because the history explains the change"),
            ("the close of month one", "a signed checklist does not tell the entire adoption story", "the sponsor approved launch while two daily users still lacked access", "review usage, unresolved work, and an owner for the next month", "small pilots should not be judged by mature-account benchmarks"),
        ],
    ),
    (
        "privacy", "Privacy reviews that move product work forward", "privacy operations",
        "A privacy review should reveal the data path and decision owner, not create a ceremonial approval.",
        [
            ("data inventory", "a field name rarely explains what the field reveals", "an events table called metadata contained free-form customer comments", "trace sample records and classify the actual contents", "samples cannot establish that every old record has the same shape"),
            ("purpose", "teams collect extra fields because the form makes it easy", "a pilot signup asked for job titles it never used", "tie each field to a named product purpose", "future use is not a substitute for a current reason"),
            ("access", "shared access blurs responsibility during an incident", "a broad support role could export every workspace in the fictional test", "grant the narrowest role needed and review exceptions", "an emergency path still needs an auditable owner"),
            ("retention", "deletion promises fail when derived files are ignored", "a transcript disappeared from the UI while an old export remained in storage", "map source, cache, export, and backup retention together", "backup deletion may follow a documented rotation rather than an instant action"),
            ("correction", "a green review badge can hide a changed scope", "the team first approved anonymized notes, then learned the notes kept unique account names", "withdraw the earlier approval and record the new decision", "the old decision should remain visible as history"),
            ("vendor boundary", "a provider contract does not verify the application's own controls", "a signed agreement coexisted with a public test bucket", "test the actual data path before enabling the integration", "vendor assurances and implementation evidence answer different questions"),
        ],
    ),
    (
        "energy", "A practical energy retrofit decision meeting", "building energy retrofits",
        "A retrofit decision is credible when baseline, uncertainty, and occupant needs are visible together.",
        [
            ("baseline", "a utility bill includes more than equipment performance", "a cold month made the fictional building look worse even though occupancy had doubled", "normalize by weather and use before comparing options", "normalization is an estimate, not a meter reading"),
            ("comfort", "energy savings can conceal uneven room conditions", "a corner office stayed cold after a controls update", "collect room-level observations alongside aggregate consumption", "a few complaints do not describe every occupant"),
            ("controls", "an elaborate schedule is fragile if operators cannot maintain it", "a holiday override stayed active for several weeks", "choose settings the facilities team can inspect and reverse", "automation cannot repair a faulty sensor"),
            ("capital plan", "the cheapest quote may omit downtime and commissioning", "a low bid excluded access equipment needed for the rooftop units", "compare complete scopes and record assumptions", "a price range is not a promise of final cost"),
            ("correcting a claim", "teams should revise savings claims as evidence improves", "the first slide said a 20 percent saving; review found that was a scenario, not a measured result", "label the figure as a scenario until post-installation data exists", "do not reuse a scenario number as a customer result"),
            ("verification", "success needs an observation window and an owner", "the building changed tenants during the proposed comparison period", "define the measurement window and explain confounding changes", "some benefits, like comfort, need both numbers and occupant feedback"),
        ],
    ),
    (
        "supply", "Supplier resilience without a giant scorecard", "supplier operations",
        "Resilience comes from understanding bottlenecks and workable alternatives rather than multiplying grades.",
        [
            ("critical parts", "spend rank can hide a low-cost single point of failure", "a small valve stopped a fictional assembly line for a day", "map the parts that interrupt delivery when missing", "a criticality list should be revisited when designs change"),
            ("lead time", "a quoted lead time is not the same as observed delivery", "the supplier's six-week quote excluded export inspection", "track actual milestones and uncertainty bands", "one late shipment does not establish a stable pattern"),
            ("alternative sources", "an alternate vendor is not ready merely because it has a catalog match", "the substitute fitting needed a new quality test", "qualify substitutions before the primary path fails", "qualification itself may require scarce engineering time"),
            ("communication", "generic escalation messages delay useful answers", "buyers repeatedly asked when an order would ship without naming the blocked production date", "share the specific decision deadline and acceptable options", "a supplier cannot solve a problem it does not see"),
            ("revision", "an early green status can become misleading", "the team first marked a backup approved, then discovered its tooling was unavailable", "reopen the risk and preserve the earlier basis", "do not treat a new quote as verified capacity"),
            ("recovery", "a resilience plan must specify the first action during disruption", "the team had a vendor list but no owner authorized to switch", "record trigger, owner, and recovery path", "stock buffers consume cash and may expire"),
        ],
    ),
    (
        "accessibility", "Making accessibility review part of delivery", "digital accessibility",
        "Accessibility improves when real tasks are tested throughout delivery, not only at release.",
        [
            ("task selection", "a home page audit can miss the workflow people actually need", "a fictional buyer could browse pricing but could not finish the upload form by keyboard", "choose critical journeys for repeated checks", "an automated scan covers only a subset of barriers"),
            ("content structure", "visual hierarchy is not always programmatic hierarchy", "a bold line looked like a heading but screen-reader navigation skipped it", "use semantic headings and labels in the component system", "semantics need human testing in context"),
            ("focus", "a keyboard user needs to know where an action moved them", "a modal closed and focus returned to the page top", "define focus return behavior for each interaction", "some browser and assistive-technology combinations differ"),
            ("error recovery", "a red border alone is hard to interpret", "a required date field failed without an explanation", "place clear text errors next to fields and announce changes", "errors should not erase the user's draft"),
            ("correction", "passing one test does not justify a universal claim", "the team first said the flow was accessible, then found the mobile review panel trapped focus", "narrow the claim and fix the blocked journey", "keep the failed test in the record"),
            ("maintenance", "a component fix can be undone by a later feature", "a new tooltip covered the submit control at narrow width", "include accessibility checks in routine review", "responsibility cannot sit with a single specialist"),
        ],
    ),
    (
        "data_quality", "Data quality meetings that end with a decision", "analytics data quality",
        "Useful quality work connects each defect to a decision, an owner, and a measured repair.",
        [
            ("definitions", "the same metric name can carry different filters", "sales counted signed pilots while finance counted first invoices", "publish the filter and unit beside the chart", "a shared definition may need a time-bound exception"),
            ("missing values", "a blank field is not always an error", "a renewal date was blank for contracts with no renewal clause", "separate not-applicable from unknown", "forcing a value may create more false certainty"),
            ("duplicates", "matching names does not prove two rows are the same entity", "two fictional customers shared an abbreviation", "review stable identifiers and provenance before merging", "some duplicates remain ambiguous and need a human decision"),
            ("timeliness", "fresh-looking dashboards can contain stale upstream feeds", "one region stopped sending updates while the page continued to refresh", "show source freshness and alert the owner", "a frequent refresh does not guarantee complete data"),
            ("correction", "an aggregate should be recomputed after source fixes", "the first report showed 42 open items, but a duplicate import had inflated it", "replace the count with a traced correction", "retain the prior report for audit"),
            ("ownership", "quality metrics without repair paths become background noise", "three teams saw the anomaly but none owned the source mapping", "assign the correction where the data is created", "downstream validation still has a role"),
        ],
    ),
    (
        "remote_work", "Better remote workshops for complex decisions", "remote facilitation",
        "A good remote workshop makes decisions inspectable while leaving room for dissent.",
        [
            ("preparation", "sending a long deck is not the same as preparing participants", "the fictional team arrived with three incompatible definitions of launch", "send a short decision brief and explicit questions", "pre-reading cannot replace a live clarification"),
            ("participation", "the loudest voice can appear to represent consensus", "quiet operators raised a blocker only after the call", "use a written round before open discussion", "a written prompt should not become a test of typing speed"),
            ("evidence", "a persuasive anecdote can outrun the available data", "one memorable customer complaint became the assumed typical case", "label examples and compare them with broader evidence", "aggregate data can also conceal important exceptions"),
            ("timeboxing", "a timer helps only when the decision can fit the time", "the team spent most of the session naming options and rushed the risk discussion", "reserve time for dissent and a closing decision", "sometimes the right outcome is a deferred decision with an owner"),
            ("correction", "minutes should reflect uncertainty honestly", "the first summary said unanimous agreement, but two participants had not voted", "amend the record and collect explicit responses", "do not erase the original draft without a revision note"),
            ("follow-through", "actions need a recipient and a test of completion", "the group agreed to investigate integration risk but named no deadline", "publish owners, dates, and what evidence will close each action", "a meeting cannot guarantee execution by itself"),
        ],
    ),
    (
        "incident", "A measured response to a security incident", "security operations",
        "A useful incident response protects evidence and people while keeping uncertainty explicit.",
        [
            ("first signal", "an alert is a prompt to investigate, not a confirmed breach", "the fictional monitor saw unusual exports during a scheduled migration", "preserve logs and identify the responsible change", "the absence of another alert does not prove safety"),
            ("containment", "a quick block can harm legitimate work if its scope is unclear", "rotating a shared credential interrupted two unrelated services", "choose the smallest effective containment action and record impact", "some emergencies require broader temporary controls"),
            ("timeline", "memory becomes unreliable under pressure", "two responders recalled the same access event in a different order", "record timestamps, source systems, and timezone", "log clocks can drift and should be reconciled"),
            ("communication", "premature certainty can mislead stakeholders", "the first draft notice declared no customer impact before export review finished", "state what is known, unknown, and the next update time", "specific legal duties depend on facts and jurisdiction"),
            ("correction", "a revised finding should be visible", "the team first called the event a test, then discovered an unrelated access path", "publish a dated correction to the working timeline", "a correction does not imply that every earlier action was wrong"),
            ("learning", "a postmortem should change a control, not only describe people", "a missing owner allowed an alert rule to remain disabled", "assign measurable follow-up and verify it", "training alone may not fix a structural gap"),
        ],
    ),
    (
        "circular", "Circular purchasing for ordinary operations", "circular procurement",
        "Circular purchasing starts with service life and repairability rather than a vague green label.",
        [
            ("need", "a replacement request can bypass a workable repair", "a fictional office replaced devices because batteries were not quoted separately", "compare repair, reuse, and replacement options", "repair may be unsafe or uneconomic for some assets"),
            ("specification", "broad sustainability language is hard to verify", "a supplier claimed recyclability without material detail", "ask for evidence tied to the exact product", "a document can be valid yet irrelevant to a variant"),
            ("service life", "purchase price hides maintenance and disposal effort", "a low-cost fixture required proprietary parts after year two", "estimate lifetime costs with assumptions shown", "future service prices remain uncertain"),
            ("takeback", "a takeback promise needs an actual route", "the returned units sat in storage because the carrier was never arranged", "name the receiving party and tracking record", "shipping itself has cost and impact"),
            ("correction", "a recycled-content claim may apply to only one component", "the first summary said 60 percent for the whole unit; evidence covered the housing only", "correct the scope before approval", "do not turn component evidence into a product-wide number"),
            ("governance", "exception rules should be visible", "an urgent replacement skipped review but nobody recorded why", "record the exception and revisit it afterward", "an emergency path should remain usable"),
        ],
    ),
    (
        "maintenance", "Predictive maintenance with ordinary evidence", "industrial maintenance",
        "Maintenance decisions should combine sensor trends with the people who know the equipment.",
        [
            ("baseline", "a sensor threshold without operating context creates noise", "vibration rose during a planned high-load run", "compare like-for-like operating periods", "even a stable baseline can shift after repair"),
            ("labels", "historical work orders are not clean failure truth", "a repair code described inspection rather than a broken bearing", "review labels with technicians before training", "human notes may be incomplete"),
            ("intervention", "an alert has value only if someone can act on it", "the fictional plant received weekend alerts with no approved inspection path", "set owner, severity, and safe response window", "not every warning justifies stopping a line"),
            ("feedback", "a model score is less useful than the outcome of inspection", "a high-risk pump was healthy while a low-score valve failed", "record both false alarms and missed events", "a small sample cannot establish stable precision"),
            ("correction", "an early claim about avoided downtime can overstate evidence", "the first slide claimed twelve hours saved from a single alert with no counterfactual", "describe the inspection and avoid an invented saving", "future impact needs a prospective method"),
            ("rollout", "maintenance teams need a reversible pilot", "a new dashboard added alerts before retiring duplicate email rules", "pilot one asset class with clear review dates", "a pilot result may not transfer to every machine"),
        ],
    ),
    (
        "knowledge", "Internal knowledge that stays useful", "knowledge operations",
        "Search quality depends on ownership and source freshness as much as ranking.",
        [
            ("source inventory", "a convenient document may be an outdated copy", "the fictional support team kept three versions of the same policy", "identify the authoritative owner and effective date", "older versions still matter when explaining past decisions"),
            ("question patterns", "employees ask tasks, not document titles", "a user searched how to reverse an invoice rather than for the billing handbook", "organize examples around real task language", "a few sampled queries do not represent every need"),
            ("citations", "a fluent answer without a source is hard to trust", "a search assistant mixed steps from two policy versions", "show the exact cited passage and date", "a citation can still be irrelevant to the question"),
            ("permissions", "indexing must preserve source access", "a restricted draft appeared in a broad test collection", "scope retrieval and cache by workspace and role", "permissions can change after indexing"),
            ("correction", "a corrected policy should invalidate stale answers", "the team first gave a seven-day return window, then found the current policy said fourteen days", "reindex and make the correction visible", "do not treat a model's confidence as authority"),
            ("measurement", "click counts alone can reward misleading results", "employees opened the top result but still filed repeated tickets", "review task completion and failure samples", "human review is needed for sensitive answers"),
        ],
    ),
    (
        "clinic", "Reducing handoff friction in a fictional clinic", "service operations",
        "Reliable handoffs require clear responsibility and verified context, especially when the stakes are high.",
        [
            ("intake", "missing context can be hidden by a completed form", "a fictional referral arrived without the reason for the requested follow-up", "verify the fields that affect the next action", "a form cannot replace professional judgment"),
            ("queue", "a single waiting count hides different urgency", "routine paperwork and time-sensitive callbacks sat in the same list", "use explicit priority rules set by qualified staff", "software must not infer clinical urgency from a keyword alone"),
            ("handoff", "a sent message is not proof of receipt", "the receiving team never opened a transfer note", "require acknowledgment for critical transfers", "acknowledgment is not proof that the plan was carried out"),
            ("follow-up", "a reminder should show why and who owns it", "a patient received duplicate calls after two teams set the same task", "deduplicate by a shared case and action key", "some repeated contact is intentional and must remain possible"),
            ("correction", "a mistaken status needs a visible repair", "the first dashboard marked a callback complete when only a voicemail had been left", "correct the status and retain the event trail", "the demo must never be used for real clinical decisions"),
            ("boundaries", "workflow software supports trained people rather than replacing them", "a draft note omitted a qualifying detail from the source", "require review against the original record", "this fictional exercise makes no clinical performance claim"),
        ],
    ),
]

BRANDS = [
    {"workspace_slug": "studio-alpha", "name": "Morrow Research", "version": 1,
     "tone": "clear, careful, useful", "rules": {"accent": "#D86B34", "prohibited_phrases": ["guaranteed", "viral", "always"], "max_social_chars": 650}},
    {"workspace_slug": "studio-alpha", "name": "Morrow Research", "version": 2,
     "tone": "specific, calm, evidence led", "rules": {"accent": "#CC5E2B", "prohibited_phrases": ["guaranteed", "viral", "proven ROI"], "max_social_chars": 650}},
    {"workspace_slug": "studio-beta", "name": "Alder Field Notes", "version": 1,
     "tone": "practical and direct", "rules": {"accent": "#B85C36", "prohibited_phrases": ["breakthrough", "risk free"], "max_social_chars": 650}},
    {"workspace_slug": "studio-beta", "name": "Alder Field Notes", "version": 2,
     "tone": "measured, approachable", "rules": {"accent": "#AE5B39", "prohibited_phrases": ["guaranteed", "no effort"], "max_social_chars": 650}},
]

QUESTION_VARIANTS = [
    "What changed your view of {area}, and which observation is strongest?",
    "If a small team can examine only one part of {area}, where should it begin?",
    "What did the example teach you about {area} that a checklist would miss?",
    "What assumption tends to survive too long when people discuss {area}?",
    "How would you explain the tradeoff in {area} to a skeptical operator?",
    "What should a reviewer ask before treating a claim about {area} as settled?",
]


def words(value: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", value))


def make_segments(title: str, focus: str, thesis: str, facets: list[tuple[str, ...]], rng: random.Random) -> list[dict]:
    parts: list[str] = [
        f"Welcome to this synthetic Morrow field session, {title}. This presentation is an authored example for testing an editorial workflow. The company, project situations, and participants are fictional. Our working proposition is simple: {thesis} We will examine six decisions, not a universal formula. Each example is a scenario, and any number I mention belongs to that scenario unless I explicitly say otherwise. The aim is to make an audience more precise about what it can conclude from source material. A content editor should be able to return to this recording, read the complete surrounding passage, and decide whether a headline preserves its meaning. We will also correct an earlier statement when the evidence changes. That correction is part of the story, not an embarrassment to remove.",
    ]
    for index, (area, observation, example, decision, caveat) in enumerate(facets):
        question = QUESTION_VARIANTS[index].format(area=area)
        p1 = (
            f"A participant asks: {question} Let me start with a concrete observation. In {focus}, {observation}. "
            f"That sounds ordinary, but it changes what a team should inspect before choosing a remedy. "
            f"For instance, {example}. This is a fictional situation, not a customer result. The useful detail is the sequence: "
            f"someone made an assumption, the work proceeded, and a later fact exposed the gap. "
            f"If we reduce the whole episode to an upbeat slogan, we lose the decision the team actually faced. "
            f"The first question should therefore be what is observable in the source, what remains inferred, and who can verify the missing part. "
            f"That distinction matters when this recording becomes a newsletter or a short clip."
        )
        p2 = (
            f"Here is the practical move I would make: {decision}. I would write that action where the people doing the work can see it, "
            f"attach an owner, and define what evidence would change our mind. The point is not to add a ritual. "
            f"The point is to make a choice that another person can inspect next week. In the fictional example, "
            f"I would ask the responsible team to show the original record and one counterexample before declaring the issue solved. "
            f"A presentation can make that step sound neat, while daily work is usually messier. "
            f"We should preserve that messiness in a source note. If an editor selects a sentence from here, the claim needs this surrounding explanation, "
            f"because the recommendation is conditional and depends on the observed situation."
        )
        p3 = (
            f"A follow-up question is what could make this recommendation wrong. My answer is: {caveat}. "
            f"That caveat is not a footnote to hide in small print. It sets the boundary of the claim. "
            f"An honest social post might say that this approach helped the fictional team frame a decision, "
            f"then invite the reader to check the conditions in their own setting. It should not say the approach guarantees an outcome. "
            f"If we later find a conflicting record, we will update the transcript and invalidate only the assets that depend on this point. "
            f"Other approved material can stand if its sources remain unchanged. That is how a careful editorial process can move quickly without making every revision a full restart."
        )
        if index == 4:
            p3 += (
                " I need to correct the stronger wording I used in our first draft of this session. "
                "I initially described the example as a measured result. It is a constructed scenario. "
                "The corrected version describes the observation and the proposed action, without claiming a measured benefit. "
                "Please keep the correction attached if you quote or clip this passage."
            )
        parts.extend((p1, p2, p3))
    parts.append(
        f"Let us close by returning to the core proposition: {thesis} These six examples do not prove that every team will get the same result. "
        "They provide a way to ask sharper questions about evidence, ownership, and context. If you turn this talk into an article, "
        "keep the scenario label and the caveats visible. If you turn it into a clip, leave enough of the surrounding sentence that a "
        "qualification or negation is not cut away. For a carousel, make each slide readable on its own and cite the relevant time range. "
        "For a newsletter, invite a reply about what would change the reader's decision. This synthetic presentation ends here; "
        "no external audience, customer outcome, or engagement metric is implied."
    )
    # A fixed seed controls conversational pauses without changing claim wording.
    cursor = 0
    segments = []
    for text in parts:
        duration = round(words(text) / 178 * 60_000) + rng.randint(240, 480)
        segments.append({"start_ms": cursor, "end_ms": cursor + duration, "speaker": "Synthetic narrator", "text": text})
        cursor += duration
    return segments


def validation_cases(sources: list[dict], reference_date: date) -> list[dict]:
    defects = ["altered_number", "unsupported_statistic", "quote_drift", "missing_attribution",
               "negation_removed_by_clipping", "corrected_transcript", "render_failure", "duplicate_publishing"]
    cases = []
    for index in range(80):
        split = "development" if index < 20 else "held_out"
        # Entity-disjoint: the first four source scripts never appear in held-out cases.
        defect = defects[index % len(defects)]
        pool = sources[:4] if split == "development" else sources[4:]
        if defect == "altered_number":
            numeric = [(source, j) for source in pool for j, item in enumerate(source["segments"])
                       if re.search(r"\b\d+\b", item["text"])]
            if not numeric:
                raise ValueError("Numeric claim cases need numeric source passages")
            source, segment_index = numeric[(index // 8) % len(numeric)]
        else:
            source = pool[(index // 8) % len(pool)]
            segment_index = (index * 3) % len(source["segments"])
        segment = source["segments"][segment_index]
        segment_id = f"{source['source_key']}:{segment_index}"
        candidate = {"asset_type": "social", "title": "Fixture validation candidate", "text": "",
                     "slides": [], "clip_range": None, "source_segment_ids": [segment_id]}
        expected_warning = ""
        if defect == "altered_number":
            original = re.search(r"\b\d+\b", segment["text"]).group()
            replacement = str(int(original) + 173)
            candidate["text"] = f"The scenario recorded {replacement} items."
            expected_warning = "Number lacks cited transcript evidence"
        elif defect == "unsupported_statistic":
            candidate["text"] = "A claimed 73% of teams prefer this approach."
            expected_warning = "Number lacks cited transcript evidence"
        elif defect == "quote_drift":
            candidate["text"] = f'"{segment["text"][:38].strip()} definitely"'
            expected_warning = "Quote not found verbatim"
        elif defect == "missing_attribution":
            candidate["text"] = segment["text"][:110]
            candidate["source_segment_ids"] = []
            expected_warning = "Missing source segment evidence"
        elif defect == "negation_removed_by_clipping":
            segment_with_negation = next((j for j, item in enumerate(source["segments"])
                                          if re.search(r"\bnot\b", item["text"], re.IGNORECASE)
                                          and item["end_ms"] - item["start_ms"] >= 21_000), segment_index)
            segment_index = segment_with_negation
            segment = source["segments"][segment_index]
            segment_id = f"{source['source_key']}:{segment_index}"
            candidate.update({"asset_type": "clip", "source_segment_ids": [segment_id],
                              "clip_range": {"start_ms": segment["start_ms"] + 700,
                                             "end_ms": segment["end_ms"]}})
            expected_warning = "Clip cuts through a cited transcript segment"
        elif defect == "corrected_transcript":
            candidate["text"] = segment["text"][:100]
            candidate["source_segment_ids"] = [f"replaced:{segment_id}"]
            expected_warning = "Unknown source segment evidence"
        elif defect == "render_failure":
            candidate.update({"asset_type": "carousel", "slides": [
                {"heading": "A source note", "body": segment["text"][:100], "source_segment_ids": [segment_id]}
                for _ in range(5)]})
            expected_warning = "Carousel requires 6"
        elif defect == "duplicate_publishing":
            candidate = {"operation_key": f"synthetic-dispatch-{index // 8}",
                         "attempts": 2, "expected_draft_count": 1}
            expected_warning = "integration_only"
        cases.append({
            "case_id": f"case-{index + 1:03d}",
            "split": split,
            "template_group": f"{split}-{defect}-{index // 8}",
            "source_key": source["source_key"],
            "source_segment_index": segment_index,
            "defect_type": defect,
            "candidate": candidate,
            "expected_warning": expected_warning,
            "reference_date": reference_date.isoformat(),
        })
    return cases


def generate(root: Path, seed: int, reference_date: date) -> None:
    rng = random.Random(seed)
    source_dir = root / "fixtures" / "sources"
    source_dir.mkdir(parents=True, exist_ok=True)
    sources = []
    for index, (key, title, focus, thesis, facets) in enumerate(TOPICS):
        segments = make_segments(title, focus, thesis, facets, rng)
        count = sum(words(segment["text"]) for segment in segments)
        if not 1800 <= count <= 3000:
            raise ValueError(f"{key} has {count} words; expected 1800-3000")
        source = {
            "source_key": key,
            "workspace_slug": "studio-alpha" if index < 6 else "studio-beta",
            "title": title,
            "kind": "transcript_fixture",
            "rights_status": "owned_synthetic_script",
            "provenance": "Authored fictional script; no real customer recording",
            "recorded_on": (reference_date - timedelta(days=(index + 1) * 4)).isoformat(),
            "duration_ms": segments[-1]["end_ms"],
            "word_count": count,
            "segments": segments,
        }
        source_path = source_dir / f"{index + 1:02d}-{key}.json"
        # A completed media fixture carries measured SAPI segment boundaries.
        # Keep them on repeat seeds; replacing them with script-time estimates
        # would silently make the shipped MP4's captions inaccurate.
        if source_path.exists():
            previous = json.loads(source_path.read_text(encoding="utf-8"))
            if previous.get("kind") == "owned_media":
                media_path = previous.get("media_path", "")
                if not isinstance(media_path, str) or not media_path.startswith(f"media/{key}/"):
                    raise ValueError(f"Invalid existing media path for {key}")
                if not (root / "fixtures" / media_path).is_file():
                    raise ValueError(f"Existing owned-media fixture for {key} is missing")
                prior_segments = previous.get("segments", [])
                if [s["text"] for s in prior_segments] != [s["text"] for s in segments]:
                    raise ValueError(f"Script for {key} changed; regenerate its owned media before reseeding")
                for generated_segment, measured_segment in zip(segments, prior_segments):
                    generated_segment["start_ms"] = measured_segment["start_ms"]
                    generated_segment["end_ms"] = measured_segment["end_ms"]
                for field in ("kind", "rights_status", "provenance", "media_path", "duration_ms", "timestamp_method"):
                    source[field] = previous[field]
        source_path.write_text(json.dumps(source, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        sources.append(source)
    (root / "fixtures" / "brands.json").write_text(json.dumps(BRANDS, indent=2) + "\n", encoding="utf-8")
    states = ["draft", "review", "approved", "rendered", "rejected", "needs_revision"]
    assets = []
    for index in range(120):
        source = sources[index % len(sources)]
        asset_type = ["article", "newsletter", "social", "carousel", "clip"][index % 5]
        assets.append({
            "fixture_id": f"asset-version-{index + 1:03d}",
            "workspace_slug": source["workspace_slug"], "source_key": source["source_key"],
            "asset_type": asset_type, "version": 1 + index // 60,
            "status": states[index % len(states)],
            "source_segment_indices": [index % len(source["segments"])],
            "text": f"Synthetic {asset_type} draft about {source['title'].lower()}; review the cited segment before approval.",
        })
    (root / "fixtures" / "asset_versions.json").write_text(json.dumps(assets, indent=2) + "\n", encoding="utf-8")
    eval_dir = root / "evals" / "datasets"
    eval_dir.mkdir(parents=True, exist_ok=True)
    cases = validation_cases(sources, reference_date)
    (eval_dir / "validation_cases.json").write_text(json.dumps(cases, indent=2) + "\n", encoding="utf-8")
    manifest = {
        "label": "Synthetic demo dataset", "seed": seed, "reference_date": reference_date.isoformat(),
        "counts": {"transcripts": len(sources), "brands": len(BRANDS), "asset_versions": len(assets),
                   "validation_development": 20, "validation_held_out": 60},
        "transcripts": [{"source_key": source["source_key"], "words": source["word_count"],
                         "duration_ms_estimate": source["duration_ms"],
                         "duration_kind": ("measured_media" if source["kind"] == "owned_media" else "script_estimate"),
                         "sha256": hashlib.sha256("\n".join(s["text"] for s in source["segments"]).encode()).hexdigest()}
                        for source in sources],
    }
    (root / "fixtures" / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest["counts"], indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=4209)
    parser.add_argument("--reference-date", type=date.fromisoformat, default=date(2026, 9, 1))
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--cases-only", action="store_true", help="Refresh evaluation cases without resetting generated media metadata")
    args = parser.parse_args()
    if args.cases_only:
        existing_sources = [json.loads(path.read_text(encoding="utf-8"))
                            for path in sorted((args.root / "fixtures" / "sources").glob("*.json"))]
        cases = validation_cases(existing_sources, args.reference_date)
        output = args.root / "evals" / "datasets" / "validation_cases.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(cases, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {len(cases)} cases without changing source fixtures")
    else:
        generate(args.root, args.seed, args.reference_date)
