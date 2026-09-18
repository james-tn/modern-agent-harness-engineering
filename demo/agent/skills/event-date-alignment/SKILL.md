---
name: event-date-alignment
description: Map announcement timestamps to the correct trading event date and prevent look-ahead bias.
license: MIT
metadata:
  version: "1.0"
---

# Event-date alignment

Read the internal event-date policy before calculating returns.

- Before market open: use that trading day.
- During the session: use that trading day and label the partial-session limitation.
- After market close: use the next trading day.
- Skip weekends and holidays using the supplied trading calendar.

Store the announcement timestamp and selected event date separately. Never infer that they
are the same.
