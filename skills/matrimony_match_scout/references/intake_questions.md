# Intake questions

## Quick Start (always first — 5 questions, then scan)
Ask ONLY these five. Everything else is "don't care" until the first report.

| # | Question | Saved as |
|---|---|---|
| QS1 | Which matrimony site is the account on? | `site` ("Shaadi" → `shaadi.com`) |
| QS2 | Who is the search for — you, or someone in your family? | `search_for` |
| QS3 | What age range is okay? | `age_min`, `age_max` ("under 30" sets only the max) |
| QS4 | Which places are okay — cities, states or countries? | `places` (list; "anywhere" = `[]`) |
| QS5 | One dealbreaker I must never let through? | `dealbreakers` (list; "no smokers" → `smoking`) |

Then: save, read all five back in one plain sentence, and ask "Is that right?".
A change in the reply ("make it 27 to 31") is applied and read back again.
Default red flags are added silently: asks for money, pressure to move off-platform.

## Refine later — from real examples
After the first report, offer to fine-tune. Use real stored profiles as
examples in the questions ("Priya shows education 'B.Tech' — what is the lowest
education that is okay?"; "You passed on both Austin profiles — should Austin
come off your places?"). Every question is skippable.

| Topic | Question | Saved as |
|---|---|---|
| Education | Lowest education that is okay? | `min_education` |
| Religion | Must match, preferred, or don't care? | `religion_must` or `religion_preferred` (list) |
| Community | Must, preferred, or don't care? | `community_must` or `community_preferred` (list) |
| Language | Mother tongue that matters? Must it match? | `mother_tongue`, `must_match_tongue` |
| Food | Which food habits are okay? | `food_ok` (vegetarian / eggetarian / non_vegetarian / vegan / jain) |
| Smoking / drinking | Okay, occasionally okay, or never? (each) | `smoking_ok`, `drinking_ok` (lists of never / occasionally / regularly) |
| Relocation | Must they be open to relocating? | `relocation_needed` |
| Timeline | Your marriage timeline? | `timeline` |
| Red flags | What should I watch for in chats? | `red_flags` (list) |
| Green flags | What should boost someone? | `green_flags` (list) |
| Good match | In a few words, what does a very good match care about? | `good_match_words` (list) |
| More dealbreakers | Anything else that is a hard no? | `dealbreakers` |
| Height | Height range, if it matters? | `height_min_cm`, `height_max_cm` |
| Scan size | How many profiles per scan? (max 50) | `max_profiles_per_run` |

Finish with the full read-back and save only after the user says it is right.

## Saving
`scout.py --data-dir <D> save-interests <file.json>` with the whole criteria
object (see `templates/interests_template.json` for every key). Null or `[]`
means don't care. If it returns `interests_hand_edited`, stop and run the
hand-edit confirmation in SKILL.md section 0 first.
