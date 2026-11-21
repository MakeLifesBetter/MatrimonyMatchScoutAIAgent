# Generic site playbook

For any matrimony site without its own playbook, follow
`references/site_learning.md` in full: map navigation, one list page, one
profile page, one chat thread, calibrate on one profile with the user, then scan.

What to look for:
- Sources by link text: Inbox / Chats / Messages; Interests received /
  Requests / Invitations; My matches / New matches / Daily / Recommended;
  Search / Search results.
- Profile links: URLs containing `/profile/<id>`, `/member/<id>`, `/view/<id>`,
  or `?profileid=`. Own-profile, edit, settings, upgrade and payment links are
  ignored.
- Chat threads: URLs containing `/chat/`, `/messages/`, `/conversation/`,
  `/inbox/<id>`. The thread's "View profile" link leads to the profile.
- "Next" link on list pages: followed once (two list pages per source).

Dedicated playbooks belong in this folder. A playbook may record, for that
site only: the names of its sections, where each schema field appears, how
pagination works, and login quirks seen. It must never contain credentials,
real profiles, or ways around a site check or warning.
