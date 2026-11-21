# Extraction schema

Every profile, from any site or file, is one JSON object like this. Use
`null` for anything the source does not show. Never invent a value. Never
record anything about photos.

```json
{
  "profile_id": "site ID, or null (the store builds a fingerprint)",
  "profile_url": "full URL, or null",
  "name": "display name",
  "age": 27,
  "height_text": "5' 4\" (as shown)",
  "height_cm": 163,
  "city": "Seattle", "state": "Washington", "country": "USA",
  "marital_status": "never_married | divorced | awaiting_divorce | widowed | null",
  "mother_tongue": "Telugu",
  "religion": "Hindu", "community": null,
  "education": "MS Computer Science", "education_detail": null,
  "profession": "Software Engineer", "employer": null,
  "income_text": "as worded on the site, or null when not shown",
  "food": "vegetarian | eggetarian | non_vegetarian | vegan | jain | null",
  "drinking": "never | occasionally | regularly | null",
  "smoking": "never | occasionally | regularly | null",
  "has_children": "yes | no | null",
  "relocate": "yes | no | open | null",
  "settle_plans": "where they plan to settle, if stated",
  "timeline": "marriage timeline, if stated",
  "family_summary": "one or two sentences",
  "about_me": "their own words, trimmed to about 800 characters",
  "partner_preference_text": "trimmed",
  "horoscope": {"rashi": "Mesha", "nakshatra": "Ashwini", "manglik": "no",
                "gothra": null, "birth_time": null, "birth_place": null},
  "chat": {
    "exists": true,
    "initiated_by": "them | user",
    "message_count": 3,
    "last_message_by": "them | user",
    "last_message_summary": "3 message(s); they started; last message from them and it asks you something. Talked about a phone or video call, the weekend.",
    "open_questions": ["asked about a phone or video call"],
    "contradictions": ["chat says Austin, profile says Seattle"],
    "red_flags": ["asks for money (mentions 'gift card')"]
  },
  "source": "chats | interests_received | matches | search | file | scan_capture",
  "source_detail": "page URL, thread, or file name and row",
  "qualitative": 14,
  "ai_judgement": "One sentence: why the 0-20 judgement (AI chat mode only)."
}
```

Rules:
- `chat.exists: null` means "not checked from this source" — the store keeps
  the chat it already had. `false` means you looked and there is no chat.
- Chat summaries are your own words. Quote at most a few words, and only as
  evidence for a red flag or contradiction. Never store a conversation.
- Never store phone numbers, emails or addresses, even if visible.
- `qualitative` and `ai_judgement` are kept apart from the profile, so a new
  judgement never makes a profile look "updated".
- The terminal's rule-based extractor (`scripts/extract.py`) fills the same
  schema; `scout.py extract <page.txt> --url <url>` runs it on one page.
