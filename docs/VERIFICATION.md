# Verification record

## Latest complete audit — 1 November 2026

See [the full audit](AUDIT_2026-11-01.md). **71 backend + 8 frontend tests passed**, all 19 demo pipelines passed, and the production build passed. Actual live collection, mandatory speed measurements, PDF/DOCX/JSON exports and weekly/monthly snapshots passed. Monitoring is now **5 minutes**; older 15-minute entries below are historical. A device/internal graph-ID collision was reproduced and fixed with a regression test. DOCX visual layout remains unverified; detailed implemented-versus-unavailable boundaries are in the audit.

## NOC workspace reorganization

- Full backend suite: **50 passed**, including the original diagnostic/export tests plus operator-confirmed completion, persisted recommendation history, system status, workspace backups and history preservation. The ten NOC/intelligence tests also passed after the final monitoring collection-status change.
- Frontend suite: **8 passed** in Vitest/jsdom. Tests cover six navigation sections, three diagnosis launchers, live KPI rendering, eight separate incident tabs, six-agent execution, report filtering, completion guards, investigation tracking, settings saves and recommendation queues. Production TypeScript/Vite build passed.
- Before/after API verification found **zero missing pre-existing incident IDs and zero missing pre-existing report IDs**. Monitoring remained enabled at 15 minutes with the exact same next scheduled timestamp across the backend restart. No database migration, reset or data deletion was performed.
- Browser walkthrough created a labelled healthy demo from the 19-scenario selector, verified all eight incident tabs and six agent cards, opened its recommendation detail, started a synthetic investigation, observed its history entry, and confirmed the completion button remained disabled without operator notes and confirmation. The dialog was cancelled; no real action was falsely marked completed.
- A real live retest from that recommendation completed and created report `RPT-146712b732e8`. Its preview retained the originating-incident link. PDF, DOCX and JSON downloaded through browser buttons; copy-summary reported success. Existing export generation was also rechecked through the API.
- Weekly report filtering and browser report-preference persistence were checked; the temporary JSON quick-download preference was restored to Preview first. All ten Settings sections and actual About health/test data were inspected.
- Responsive checks covered the 1440-pixel desktop layout and 390-pixel mobile layout. The mobile navigation opened and navigated to recommendation queues; document width matched viewport width without horizontal page overflow. Wide tables/tabs retain their own horizontal scrolling.
- About test counts are read from `docs/test-status.json`, generated from actual saved test-run outputs. This does not imply that the tests are rerun on every page visit.

## 1 November 2026 feature verification

- Dependency graph addition: full suite **48 passed**; production build passed. Follow-up graph tests also passed after cross-diagram label corrections. Tests verify switch-to-access-point dependency edges, potential hostel/service impact, evidence references, cycles, safe SVG text, embedded DOCX images and PDF graph generation. Period-report tests passed with per-check dependency graphs.
- Generated actual campus graph report `RPT-b8c6958e5cf2` in PDF, DOCX and JSON. PDF pages were rendered for visual review. DOCX contains embedded graph images; the previously documented DOCX visual-render limitation remains.

- Full suite: **46 tests passed** after topology grouping, traceable explanations, confidence/uncertainty, competing-cause resolution, historical anomaly evidence, persistent scheduler and period reporting were integrated. The eight intelligence tests also passed after the final period-statistics formatting changes.
- Production React/TypeScript build passed after the final topology layout and Home change-alert integration. Non-blocking chart bundle size warning remains.
- The browser ran the Campus segment outage demo. It displayed the observed switch fault, supporting evidence IDs and detecting agent, plus potentially affected Hostel A, Computer Science, Academic LAN, Distribution, and Hostel Wi-Fi groups. Supplied topology was inspected visually.
- Enabled actual backend monitoring at 15-minute intervals. Its first real gateway/speed check completed and produced incident `INC-7751760b562e` and report `RPT-59f00dc30d5c`; persisted state recorded the next due time exactly 900 seconds after the attempt time, with no collection error. Scheduler timing/failure/stop behavior is additionally covered by tests; no claim is made that a week or month of observations has already elapsed.
- Generated a current monthly report from recorded live history and downloaded its actual PDF. It contains one recorded check for November at verification time and explicitly states that missing coverage is unknown. PDF pages were rendered and visually inspected.
- Calendar weekly/monthly boundary behavior, empty periods, automatic period-report deduplication and PDF/DOCX generation are tested.
- Five comparable historical readings are required before anomaly alerts. Tests cover insufficient baselines, source/scenario isolation, median/MAD thresholds, evidence linkage and alert inclusion in report sections.
- Monitoring continues only while the app server/computer are running; no Windows service, sleep wake-up, external notification delivery or automatic campus discovery is claimed. Anomaly detection is a transparent change-warning method, not a trained outage prediction model. DOCX visual-render limitations described below remain.

Verified on 31 October 2026 in the Windows workspace.

## Automated checks

- `pytest backend/tests -q --tb=short`: **28 passed**, including seven additional demo scenarios. One upstream Starlette deprecation warning about the httpx test client; no test failures.
- `npm run build`: **passed**, including strict TypeScript compilation and Vite production bundling. Vite reports a non-blocking bundle size warning because charts are in the main bundle.
- Dependency versions are recorded in `requirements.lock.txt` and `frontend/package-lock.json`.
- Generated actual PDF, DOCX, and JSON report files from the Router Overload pipeline using `scripts/verify_exports.py`.
- PDF signature, DOCX ZIP/document readability and expected paragraphs, JSON equality to canonical report, correct API content types and safe download filenames are tested.
- Tests use separate temporary databases, not the interactive workspace history.

## Visual and browser checks

- Application served successfully from `http://127.0.0.1:8000` with the built React application.
- Empty-state dashboard showed zero history and idle agents without invented measurements.
- Browser exercised Home → Run a demo → Router Overload → Incident Details → View Full Report.
- Observed all six agents completed, 85% heuristic evidence score, RTR-01 affected, evidence IDs and advisory next step.
- Report preview displayed the same stored diagnosis, telemetry and evidence.
- Clicking Download PDF produced a real file in the browser download directory.
- Share Summary displayed “Summary copied. The local link is not public.”
- All four remaining demo scenarios were also run through the browser. Congestion, connectivity failure, resource failure, and healthy assessments appeared correctly; Healthy Network reported no observed fault.
- Desktop layout inspected at 1440 px; narrow tablet layout also inspected. No browser console errors were reported.
- Poppler rendered all five pages of the generated PDF; every page was visually inspected. Headings, metadata, evidence entries and page footers were readable without clipping.

## Remaining verification limits

- DOCX generation and readable document structure passed, but **DOCX visual layout is not fully verified**: the packaged `render_docx.py` cannot run because the Windows artifact runtime does not include LibreOffice (`soffice.exe`). PDF is the visually verified report format.
- Print stylesheet is implemented; physical printing and OS print-dialog behavior are not automated acceptance tests.
- The test harness verifies upload parsing/API behavior; a browser file-picker upload was not separately exercised.
- Live monitoring and remote/public sharing are intentionally unavailable and were not claimed as tested integrations.

## Environment notes

Windows sandbox restrictions prevented uv cache writes and pytest temporary-directory access; approved dependency installation and test execution outside the sandbox succeeded. The sandboxed server/report run stalled, while approved local execution completed. The application code does not depend on those assistant-specific permissions when launched normally by the user.
