# NOC feature-to-page mapping

This change reorganizes the existing application; the SQLite record table, six diagnostic agents, evidence model, monitoring scheduler and original API routes remain.

| Workspace | Existing features and organization |
| --- | --- |
| Home `/` | Recorded network health, live/demo source selector, latency/loss/speed KPIs, devices needing attention, running diagnoses and open investigations, performance charts, topology/impact, recent incidents, actual agent execution timeline, persisted monitoring controls/last/next check |
| Network Incidents `/incidents` | Search/filter/sort/pagination; diagnosis inputs at `/incidents/new` (upload/live/demo); legacy `/start` continues to resolve |
| Incident `/incidents/:id` | Overview; Agent Execution; Root Cause Analysis; Topology and Impact; Evidence Register; Recommendations; Execution Timeline; Related Reports |
| Diagnostic Reports `/reports` | Incident/live-monitoring/weekly/monthly library, search/type/status filters, previews, linked source records, PDF/DOCX/JSON/print/copy summary; existing report snapshots retained |
| AI Recommendations `/recommendations` | Status queues, priority/severity, linked incident, evidence, rationale/impact, detail route `/recommendations/:id`, investigation tracking, fresh tests, operator completion verification and persisted event history |
| Settings `/settings` | General/browser preferences, network scope, monitoring, diagnostic thresholds, agent selection, orchestration, local data export, notification availability, API information and report preferences |
| About `/about` | Product, actual architecture and six agents, stack/version, unconfigured team/GitHub information, documentation links, actual database/API health and timestamped test-run record |

Unavailable production connectors, notifications and authentication are not fabricated. Browser preferences affect presentation only. Monitoring remains a persisted 300-second backend schedule, with no reset or re-enablement during this UI work. Completion is an explicit operator tracking action, not automatic remediation.
