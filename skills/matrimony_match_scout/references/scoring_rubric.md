# Scoring rubric

Implemented in `scripts/score.py`. Same profile + same interests = same score.

## 1. Hard filters and dealbreakers — a known fail excludes, no exceptions
Checked only for criteria the user set:
- age outside `age_min`–`age_max`
- location: city, state or country not in `places` (aliases: Bay Area includes
  San Jose, Sunnyvale…; Seattle includes Bellevue, Redmond…; USA = US = United
  States). A stated plan to settle in one of the places also passes.
- marital status not in `marital_statuses`; education below `min_education`
  (high school < diploma < bachelors < masters = professional < doctorate)
- mother tongue when `must_match_tongue`; religion / community when `*_must`
- height outside the range; food / drinking / smoking value not in `*_ok`
- every `dealbreakers` entry: smoking, drinking, non-veg, divorced / widowed /
  previously married, children, manglik, not willing to relocate, lives abroad;
  any other phrase excludes when the profile text mentions it, and is otherwise
  listed as "check yourself — I cannot verify this from the profile text"
- a profile ID in `excluded_profile_ids`

**Unknown never passes and never fails.** A profile that does not show a
value for a filter stays in, is listed under "Unknown - please check: …", and
gets lower confidence. It is never counted as meeting the filter.

## 2. Weighted points — 0 to 80
Only over criteria the user set AND the profile shows. Unknown values are left
out of the sum, so they neither help nor hurt.
- location 20 (city 20, state 14, country 8, plans to settle 6)
- education 15 (at minimum 12, one level above 14, two or more 15)
- career 15 (profession or employer matches `profession_keywords`)
- lifestyle (food, drinking, smoking, relocation when set) 5 each
- language and family: mother tongue 8, religion preferred 4, community preferred 3
- green flags found in their text: +4 each, up to +10 (never above 80)
No criteria set at all → 40 (neutral).

## 3. Judgement — 0 to 20, always with a reason
AI chat mode (you), anchored:
- About-me fit with the user's "good match" words: 0 clashes or empty,
  5 generic, 10 several shared values, 15 strong overlap in their own words.
- Chat (only if one exists): 0 red flag, 2 one-sided or evasive,
  5 warm, responsive, consistent with the profile.
If no AI judgement is given for a profile, `score.py` applies the same anchors
with simple rules and labels it "Rule-based reading".

## 4. Red-flag cap
Any red flag from the user's list — found in the chat or in their profile text —
caps the total at **40** and is named in the risks with a few words of evidence.

## Output per profile
score 0–100, excluded + reasons, why it fits (up to 4 plain reasons), risks
(red flags, contradictions, unknowns, things to check yourself), confidence
(high / medium / low: how much of what the user cares about is shown), the
judgement and who made it, and a next step (reply, wait, ask about unknowns,
send interest only after you say so, pass). Sorted by score, then fewer unknowns.
No photo, face or looks input exists anywhere.
