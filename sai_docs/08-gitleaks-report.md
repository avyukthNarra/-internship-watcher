# Gitleaks full-history report

Scan: `gitleaks detect --source . --log-opts="--all" --redact`; 13,397 commits scanned (about 88.89 MB). The report contained 90 findings, all `generic-api-key` matches in state JSON files. No live credential was identified from these matches, so there is no URGENT item. No secret values, partial values, or match text are included below.

Assessment for every entry: **False positive** — the generic detector matched opaque operational identifiers in state records; the findings are not from test fixtures and no match had a public Discord webhook URL pattern. Recommended action: keep operational state private under T03 and re-scan after the private-state migration; do not treat these identifiers as credentials.

| # | Rule | File | Commit | Line | Assessment | Recommended action |
|---:|---|---|---|---:|---|---|
| 1 | `generic-api-key` | `seen.json` | `3df3410` | 2 | False positive | Private-state migration under T03; re-scan |
| 2 | `generic-api-key` | `seen.json` | `3df3410` | 11 | False positive | Private-state migration under T03; re-scan |
| 3 | `generic-api-key` | `seen.json` | `3df3410` | 21 | False positive | Private-state migration under T03; re-scan |
| 4 | `generic-api-key` | `delivery_state.json` | `3df3410` | 3458 | False positive | Private-state migration under T03; re-scan |
| 5 | `generic-api-key` | `delivery_state.json` | `3df3410` | 3458 | False positive | Private-state migration under T03; re-scan |
| 6 | `generic-api-key` | `message_map.json` | `3df3410` | 3713 | False positive | Private-state migration under T03; re-scan |
| 7 | `generic-api-key` | `message_map.json` | `3df3410` | 3724 | False positive | Private-state migration under T03; re-scan |
| 8 | `generic-api-key` | `message_map.json` | `3df3410` | 3735 | False positive | Private-state migration under T03; re-scan |
| 9 | `generic-api-key` | `delivery_state.json` | `3df3410` | 3463 | False positive | Private-state migration under T03; re-scan |
| 10 | `generic-api-key` | `delivery_state.json` | `3df3410` | 3463 | False positive | Private-state migration under T03; re-scan |
| 11 | `generic-api-key` | `delivery_state.json` | `3df3410` | 3468 | False positive | Private-state migration under T03; re-scan |
| 12 | `generic-api-key` | `delivery_state.json` | `3df3410` | 3468 | False positive | Private-state migration under T03; re-scan |
| 13 | `generic-api-key` | `delivery_state.json` | `3df3410` | 10682 | False positive | Private-state migration under T03; re-scan |
| 14 | `generic-api-key` | `delivery_state.json` | `3df3410` | 10691 | False positive | Private-state migration under T03; re-scan |
| 15 | `generic-api-key` | `delivery_state.json` | `3df3410` | 10701 | False positive | Private-state migration under T03; re-scan |
| 16 | `generic-api-key` | `delivery_state.json` | `e9cafde` | 3452 | False positive | Private-state migration under T03; re-scan |
| 17 | `generic-api-key` | `delivery_state.json` | `e9cafde` | 3452 | False positive | Private-state migration under T03; re-scan |
| 18 | `generic-api-key` | `delivery_state.json` | `e9cafde` | 10540 | False positive | Private-state migration under T03; re-scan |
| 19 | `generic-api-key` | `message_map.json` | `e9cafde` | 3412 | False positive | Private-state migration under T03; re-scan |
| 20 | `generic-api-key` | `seen.json` | `e9cafde` | 9 | False positive | Private-state migration under T03; re-scan |
| 21 | `generic-api-key` | `delivery_state.json` | `c82e1dd` | 3465 | False positive | Private-state migration under T03; re-scan |
| 22 | `generic-api-key` | `delivery_state.json` | `c82e1dd` | 3465 | False positive | Private-state migration under T03; re-scan |
| 23 | `generic-api-key` | `delivery_state.json` | `c82e1dd` | 3468 | False positive | Private-state migration under T03; re-scan |
| 24 | `generic-api-key` | `delivery_state.json` | `c82e1dd` | 3468 | False positive | Private-state migration under T03; re-scan |
| 25 | `generic-api-key` | `delivery_state.json` | `c82e1dd` | 3469 | False positive | Private-state migration under T03; re-scan |
| 26 | `generic-api-key` | `delivery_state.json` | `c82e1dd` | 3469 | False positive | Private-state migration under T03; re-scan |
| 27 | `generic-api-key` | `delivery_state.json` | `c82e1dd` | 3470 | False positive | Private-state migration under T03; re-scan |
| 28 | `generic-api-key` | `delivery_state.json` | `c82e1dd` | 3470 | False positive | Private-state migration under T03; re-scan |
| 29 | `generic-api-key` | `delivery_state.json` | `c82e1dd` | 10525 | False positive | Private-state migration under T03; re-scan |
| 30 | `generic-api-key` | `delivery_state.json` | `c82e1dd` | 10533 | False positive | Private-state migration under T03; re-scan |
| 31 | `generic-api-key` | `delivery_state.json` | `c82e1dd` | 10534 | False positive | Private-state migration under T03; re-scan |
| 32 | `generic-api-key` | `delivery_state.json` | `c82e1dd` | 10537 | False positive | Private-state migration under T03; re-scan |
| 33 | `generic-api-key` | `seen.json` | `c82e1dd` | 6 | False positive | Private-state migration under T03; re-scan |
| 34 | `generic-api-key` | `message_map.json` | `c82e1dd` | 3427 | False positive | Private-state migration under T03; re-scan |
| 35 | `generic-api-key` | `message_map.json` | `c82e1dd` | 3438 | False positive | Private-state migration under T03; re-scan |
| 36 | `generic-api-key` | `message_map.json` | `c82e1dd` | 3449 | False positive | Private-state migration under T03; re-scan |
| 37 | `generic-api-key` | `message_map.json` | `c82e1dd` | 3460 | False positive | Private-state migration under T03; re-scan |
| 38 | `generic-api-key` | `delivery_state.json` | `5d265ab` | 3461 | False positive | Private-state migration under T03; re-scan |
| 39 | `generic-api-key` | `delivery_state.json` | `5d265ab` | 3461 | False positive | Private-state migration under T03; re-scan |
| 40 | `generic-api-key` | `delivery_state.json` | `5d265ab` | 3462 | False positive | Private-state migration under T03; re-scan |
| 41 | `generic-api-key` | `delivery_state.json` | `5d265ab` | 3462 | False positive | Private-state migration under T03; re-scan |
| 42 | `generic-api-key` | `seen.json` | `5d265ab` | 7 | False positive | Private-state migration under T03; re-scan |
| 43 | `generic-api-key` | `delivery_state.json` | `5d265ab` | 10518 | False positive | Private-state migration under T03; re-scan |
| 44 | `generic-api-key` | `seen.json` | `5d265ab` | 9 | False positive | Private-state migration under T03; re-scan |
| 45 | `generic-api-key` | `seen.json` | `c82e1dd` | 14 | False positive | Private-state migration under T03; re-scan |
| 46 | `generic-api-key` | `seen.json` | `c82e1dd` | 15 | False positive | Private-state migration under T03; re-scan |
| 47 | `generic-api-key` | `delivery_state.json` | `5d265ab` | 10520 | False positive | Private-state migration under T03; re-scan |
| 48 | `generic-api-key` | `seen.json` | `c82e1dd` | 18 | False positive | Private-state migration under T03; re-scan |
| 49 | `generic-api-key` | `message_map.json` | `5d265ab` | 3405 | False positive | Private-state migration under T03; re-scan |
| 50 | `generic-api-key` | `message_map.json` | `5d265ab` | 3416 | False positive | Private-state migration under T03; re-scan |
| 51 | `generic-api-key` | `seen.json` | `36c480a` | 10 | False positive | Private-state migration under T03; re-scan |
| 52 | `generic-api-key` | `seen.json` | `b2b6d1c` | 6 | False positive | Private-state migration under T03; re-scan |
| 53 | `generic-api-key` | `message_map.json` | `b2b6d1c` | 1590 | False positive | Private-state migration under T03; re-scan |
| 54 | `generic-api-key` | `message_map.json` | `36c480a` | 1931 | False positive | Private-state migration under T03; re-scan |
| 55 | `generic-api-key` | `seen.json` | `384d473` | 10 | False positive | Private-state migration under T03; re-scan |
| 56 | `generic-api-key` | `message_map.json` | `6c9e11d` | 1414 | False positive | Private-state migration under T03; re-scan |
| 57 | `generic-api-key` | `seen.json` | `6c9e11d` | 2 | False positive | Private-state migration under T03; re-scan |
| 58 | `generic-api-key` | `message_map.json` | `384d473` | 2316 | False positive | Private-state migration under T03; re-scan |
| 59 | `generic-api-key` | `seen.json` | `2de1aff` | 2 | False positive | Private-state migration under T03; re-scan |
| 60 | `generic-api-key` | `seen.json` | `2de1aff` | 3 | False positive | Private-state migration under T03; re-scan |
| 61 | `generic-api-key` | `seen.json` | `2de1aff` | 4 | False positive | Private-state migration under T03; re-scan |
| 62 | `generic-api-key` | `seen.json` | `2de1aff` | 6 | False positive | Private-state migration under T03; re-scan |
| 63 | `generic-api-key` | `seen.json` | `2de1aff` | 7 | False positive | Private-state migration under T03; re-scan |
| 64 | `generic-api-key` | `seen.json` | `2de1aff` | 8 | False positive | Private-state migration under T03; re-scan |
| 65 | `generic-api-key` | `seen.json` | `2de1aff` | 9 | False positive | Private-state migration under T03; re-scan |
| 66 | `generic-api-key` | `seen.json` | `2de1aff` | 10 | False positive | Private-state migration under T03; re-scan |
| 67 | `generic-api-key` | `seen.json` | `2dc14e9` | 2 | False positive | Private-state migration under T03; re-scan |
| 68 | `generic-api-key` | `seen.json` | `2dc14e9` | 3 | False positive | Private-state migration under T03; re-scan |
| 69 | `generic-api-key` | `seen.json` | `2dc14e9` | 4 | False positive | Private-state migration under T03; re-scan |
| 70 | `generic-api-key` | `seen.json` | `2dc14e9` | 5 | False positive | Private-state migration under T03; re-scan |
| 71 | `generic-api-key` | `seen.json` | `2dc14e9` | 6 | False positive | Private-state migration under T03; re-scan |
| 72 | `generic-api-key` | `seen.json` | `2dc14e9` | 8 | False positive | Private-state migration under T03; re-scan |
| 73 | `generic-api-key` | `seen.json` | `2dc14e9` | 10 | False positive | Private-state migration under T03; re-scan |
| 74 | `generic-api-key` | `seen.json` | `2dc14e9` | 11 | False positive | Private-state migration under T03; re-scan |
| 75 | `generic-api-key` | `seen.json` | `2dc14e9` | 12 | False positive | Private-state migration under T03; re-scan |
| 76 | `generic-api-key` | `seen.json` | `2dc14e9` | 13 | False positive | Private-state migration under T03; re-scan |
| 77 | `generic-api-key` | `seen.json` | `2dc14e9` | 14 | False positive | Private-state migration under T03; re-scan |
| 78 | `generic-api-key` | `seen.json` | `2dc14e9` | 15 | False positive | Private-state migration under T03; re-scan |
| 79 | `generic-api-key` | `delivery_state.json` | `2dc14e9` | 1097 | False positive | Private-state migration under T03; re-scan |
| 80 | `generic-api-key` | `delivery_state.json` | `2dc14e9` | 1098 | False positive | Private-state migration under T03; re-scan |
| 81 | `generic-api-key` | `delivery_state.json` | `2dc14e9` | 1099 | False positive | Private-state migration under T03; re-scan |
| 82 | `generic-api-key` | `delivery_state.json` | `2dc14e9` | 1100 | False positive | Private-state migration under T03; re-scan |
| 83 | `generic-api-key` | `delivery_state.json` | `2dc14e9` | 1101 | False positive | Private-state migration under T03; re-scan |
| 84 | `generic-api-key` | `delivery_state.json` | `2dc14e9` | 1103 | False positive | Private-state migration under T03; re-scan |
| 85 | `generic-api-key` | `delivery_state.json` | `2dc14e9` | 1105 | False positive | Private-state migration under T03; re-scan |
| 86 | `generic-api-key` | `delivery_state.json` | `2dc14e9` | 1106 | False positive | Private-state migration under T03; re-scan |
| 87 | `generic-api-key` | `delivery_state.json` | `2dc14e9` | 1107 | False positive | Private-state migration under T03; re-scan |
| 88 | `generic-api-key` | `delivery_state.json` | `2dc14e9` | 1108 | False positive | Private-state migration under T03; re-scan |
| 89 | `generic-api-key` | `delivery_state.json` | `2dc14e9` | 1109 | False positive | Private-state migration under T03; re-scan |
| 90 | `generic-api-key` | `delivery_state.json` | `2dc14e9` | 1110 | False positive | Private-state migration under T03; re-scan |

## File totals

- `delivery_state.json`: 42
- `message_map.json`: 14
- `seen.json`: 34

The full redacted machine report is in Pane scratch at `$PANE_SCRATCH_DIR/gitleaks.json`; it is intentionally not committed. The public state files flagged by this scan contain sensitive operational data even though these particular generic-key matches appear to be identifiers. The owner should proceed with the T03 private-store decision.
