# Running AI Coach MVP PRD

## 1. Product Summary

Running AI Coach is a post-run analysis product for runners who have watch data but do not understand how to interpret it.

The first version turns uploaded running workout files into:

- a plain-language training recap,
- a short list of important findings,
- a small set of trend insights,
- a concrete next-run suggestion.

The MVP is not a general fitness app and not a medical product.

## 2. Problem Statement

Runners already have access to a large amount of data from Garmin, Coros, Apple Watch, Strava, and similar tools, but most users cannot answer simple questions after a run:

- Was this actually a good easy run?
- Did I start too fast?
- Why did my heart rate drift up?
- Am I improving or just getting tired?
- What should I do next?

Existing watch and platform summaries are usually metric-heavy and explanation-light. The user still needs domain knowledge to turn numbers into action.

## 3. Product Goal

Help non-expert runners understand their run data and make better training decisions without needing to learn sports science concepts first.

## 4. Non-Goals

The MVP does not include:

- real-time coaching during a run,
- full adaptive training plan generation,
- social features,
- community leaderboards,
- nutrition coaching,
- medical diagnosis,
- injury diagnosis,
- direct watch vendor integrations,
- support for sports other than running.

## 5. Target Users

### Primary User

A recreational runner who:

- runs 2 to 6 times per week,
- owns a sports watch or phone running app,
- sees many metrics but cannot interpret them,
- wants useful advice instead of a dashboard full of jargon.

### Secondary User

A technical or semi-serious runner who:

- understands some metrics,
- wants deeper analysis like heart rate drift, recovery, and running mechanics,
- values trend analysis over single-run summaries.

### Later User Segment

Coaches or running club leaders who want to review multiple athletes. This is out of scope for MVP but should influence the data model.

## 6. Core Value Proposition

"Upload your run data and get a readable explanation of what happened, why it matters, and what to do next."

The product wins if users feel the output is:

- easier to understand than Garmin/Strava native summaries,
- more actionable than raw watch metrics,
- more trustworthy than a generic chatbot response.

## 7. MVP Scope

### In Scope

1. Upload one or more FIT files.
2. Parse run data into a standard internal format.
3. Generate a single-run recap.
4. Generate recent trend analysis across multiple runs.
5. Show 5 to 8 core metrics with explanations.
6. Give the user one concrete next-run recommendation.
7. Support natural-language follow-up questions about the analysis.

### Out of Scope

1. Sync with Garmin, Strava, Apple Health, Coros, Polar, or Suunto.
2. Mobile app.
3. Wearable or sensor pairing.
4. Race prediction engine.
5. Training calendar.
6. Full coach dashboard.

## 8. User Stories

### Upload and Analysis

As a runner, I want to upload a run file so that I can get an explanation of what happened in my workout.

### Plain-Language Recap

As a runner, I want a short summary in normal language so that I can understand whether the session matched its intended purpose.

### Trend Awareness

As a runner, I want to know whether I am improving or accumulating fatigue so that I can adjust training before a bad block or poor race.

### Follow-Up Q&A

As a runner, I want to ask follow-up questions so that I can learn unfamiliar concepts without leaving the app.

### Actionable Advice

As a runner, I want a next-step recommendation so that I know what to do on the next run instead of just reading a report.

## 9. MVP Experience Flow

1. User lands on the web app.
2. User uploads one or more FIT files.
3. System parses files and stores raw + derived data.
4. System computes core metrics and classifies workout type.
5. System generates a structured report.
6. User reads:
   - one-line summary,
   - three key findings,
   - two risks or cautions,
   - next-run recommendation,
   - metric explanations.
7. User asks follow-up questions in chat.

## 10. Report Structure

Every report should follow the same output shape.

### A. One-Line Summary

Example:
"This looked like a moderate-effort easy run with solid early pacing, but noticeable heart rate drift in the second half suggests aerobic durability still needs work."

### B. Key Findings

3 items maximum.

Each finding must include:

- what happened,
- why it matters,
- supporting evidence.

### C. Risk or Caution

Up to 2 items.

Examples:

- possible fatigue accumulation,
- poor pacing control,
- recovery signal weaker than usual.

### D. Next-Run Recommendation

One main suggestion only.

Examples:

- 40 minutes easy in Zone 2,
- rest day,
- short recovery jog,
- avoid threshold work tomorrow.

### E. Metric Explainability

For each surfaced metric, show:

- plain-language meaning,
- why this matters for the user,
- whether the value is improving, stable, or declining.

## 11. Core Metrics for MVP

The first version should limit the surface area and focus on metrics that can drive action.

### Required Metrics

1. Pace stability
2. Pace fade in later stages
3. Heart rate drift / decoupling
4. Heart rate recovery after stopping
5. Average cadence and cadence stability
6. Aerobic efficiency proxy
7. Weekly load trend
8. Recovery / fatigue flag

### Optional Internal Metrics

These can be calculated but hidden unless useful:

- vertical oscillation,
- ground contact time,
- stride length,
- left/right balance,
- power-based efficiency.

## 12. Product Principles

1. Explain before optimizing.
2. Translate metrics into decisions.
3. Prefer trend analysis over isolated data points.
4. Use LLMs for language and Q&A, not for core numerical truth.
5. Keep output brief by default, deeper on demand.

## 13. Functional Requirements

### Data Input

- User can upload FIT files from desktop.
- System rejects unsupported file types.
- System handles multiple activities for the same user.

### Analysis

- System identifies whether the file is a run.
- System computes derived metrics.
- System generates a structured report from derived metrics.
- System stores analysis history.

### Chat

- User can ask questions about a completed report.
- Chat references the current report plus historical summary only.
- Chat must not invent unsupported numeric facts.

### History

- User can revisit past reports.
- User can see recent trend summaries.

## 14. Trust and Safety Requirements

- The product must not present itself as a medical device.
- Reports must avoid diagnosis claims.
- The UI should include a short notice that suggestions are training guidance, not medical advice.
- When signals look abnormal, the product should recommend reducing training load or seeking professional advice without making health diagnoses.

## 15. Success Metrics

### MVP Validation Metrics

1. At least 60% of test users upload 3 or more runs.
2. At least 50% of test users ask at least one follow-up question.
3. At least 40% of test users say the report is more useful than native watch summaries.
4. At least 30% of test users return in a second week.

### Qualitative Validation Questions

1. Which finding felt most useful?
2. Which metric was still confusing?
3. Which recommendation did you actually follow?
4. Where did the report feel incorrect or generic?

## 16. Launch Plan

### Phase 1

Invite 10 to 20 runners to manually upload data and review reports.

### Phase 2

Improve metric reliability, wording quality, and trend analysis.

### Phase 3

Test willingness to pay for historical insights and personalized recommendations.

## 17. Open Questions

1. Will early users care more about single-run reports or multi-week trends?
2. Which metrics drive retention most strongly?
3. Do users trust AI advice without direct watch integrations?
4. Is the best initial customer an individual runner or a coach?

## 18. Immediate Next Steps

1. Build FIT upload and parsing pipeline.
2. Implement first 5 derived metrics.
3. Generate structured report JSON before building full chat.
4. Test with real files from 5 to 10 runners.
