# CampX staging UI captures (real, medha tenant, as-is data)

Source: https://medha.schoolsquare.in (staging), tenant medha, logged in as the staging admin+evaluator. Marking shots are script 191 of bundle 168 (cycle 4, "Booklet 2", E2E P24CM109 Construction Equipment and Management, finished AI run, nothing saved or submitted).
Light theme only (the app has no dark theme). Boxes are x,y,w,h in PNG pixels (origin top-left); all were verified by cropping.

- Standard size 3200x1800 (1600x900 CSS viewport at deviceScaleFactor 2). Files marked TALL are 1600xH CSS px at 2x (see size) so the whole AI panel fits.
- Marking-screen layout (3200x1800 shots): top bar y 0-140; tool rail x 0-240; scan page canvas x 192-2360, y 112-1712 (scrolls; the purple wash on the handwriting is Medha's mapped answer region, with a small "Q4" tag at its top-left); right panel x 2362-3200 = question header, Medha AI / Marking scheme toggle (y ~300-370), AI card, then the marks dock + question tabs at the bottom.
- Admin-page boxes mark the nearest container of the named element (a row, tile or section), not always the whole card; where a "card" box exists it is the full block.
- Best picks: control_workspace_q4 (hero, partial credit 6/12 with matched, unsure and missed points), control_hover_accept_q4, markui_q4_tall (full AI breakdown), control_flagged_q1 (placement warning + unsure flags), readui_compare_q4_tall (Compare dialog), readui_transcript_q4(_tall), control_evaluators_medha_ai_seat, ingestui_batch_stages_tall, ingestui_uploads_list, ingestui_exceptions, dash_admin_dashboard.
- Not captured: an admin "AI evaluation jobs" page (no such page exists in the staging UI; Medha AI appears as an evaluator seat on the subject Evaluators and Bundles tabs instead), an analytics page beyond the admin dashboard (Reports is empty), an override edit (would write marks).

## control_bundle_scripts.png
- size: 3200x1800
- screen: Evaluator bundle 168: script list for marking (read only; no script opened).
- route: /medha/evaluator-workspace/bundles/168
- regions (x,y,w,h):
  - page title: 706,269,1535,72
  - scripts table: 706,822,2304,978

## control_evaluator_dashboard.png
- size: 3200x1800
- screen: Evaluator workspace dashboard.
- route: /medha/evaluator-workspace/dashboard
- regions (x,y,w,h):
  - page title: 558,174,2600,68

## control_evaluators_medha_ai_seat.png
- size: 3200x1800
- screen: Evaluators tab: Medha AI listed as an evaluator seat next to the human evaluator.
- route: /medha/evaluation-admin-workspace/subjects/E2E-24BS1T02-Linear-Algebra-Calculus%E2%87%A512
- regions (x,y,w,h):
  - subject header: 558,122,1404,84
  - evaluators table: 592,378,2532,47
  - Medha AI row: 592,491,2532,388

## control_flagged_q1.png
- size: 3200x1800
- screen: Q1 with Medha AI suggestion 10/12 and the "Check: page 11 may belong to 1 or 7" placement warning plus "Medha AI is unsure about this point. Check it yourself." flags.
- route: /medha/evaluator-workspace/bundles/168/scripts/191
- regions (x,y,w,h):
  - AI suggestion panel: 2394,400,774,1400
  - AI ready chip: 2389,30,160,50
  - Review & submit button: 2853,20,316,72
  - page viewer canvas (scan pages, scrollable): 192,112,2168,1600
  - AI card (mark + key points): 2394,400,774,1400
  - suggested mark + Accept: 2424,426,714,64
  - Accept button: 2954,426,184,64
  - marks dock: 2362,1463,838,337
  - question tabs: 2466,1627,630,72
  - unsure chip: 2476,813,662,37

## control_flagged_q3.png
- size: 3200x1800
- screen: Q3 with suggestion 8.5/12 and label-read placement notes (label read as 4 (0.60); the text reads as 3).
- route: /medha/evaluator-workspace/bundles/168/scripts/191
- regions (x,y,w,h):
  - AI suggestion panel: 2394,400,774,1364
  - AI ready chip: 2389,30,160,50
  - Review & submit button: 2853,20,316,72
  - page viewer canvas (scan pages, scrollable): 192,112,2168,1600
  - AI card (mark + key points): 2394,400,774,1246
  - suggested mark + Accept: 2424,426,714,64
  - Accept button: 2946,426,192,64
  - marks dock: 2362,1463,838,337
  - question tabs: 2466,1627,630,72
  - unsure chip: 2476,1032,662,37

## control_hover_accept_q4.png
- size: 3200x1800
- screen: Q4 workspace with the pointer hovering the Accept 6 button (nothing clicked).
- route: /medha/evaluator-workspace/bundles/168/scripts/191
- regions (x,y,w,h):
  - AI suggestion panel: 2394,400,774,1276
  - AI ready chip: 2389,30,160,50
  - Review & submit button: 2853,20,316,72
  - page viewer canvas (scan pages, scrollable): 192,112,2168,1600
  - AI card (mark + key points): 2394,400,774,1158
  - suggested mark + Accept: 2424,426,714,64
  - Accept button: 2970,426,168,64
  - marks dock: 2362,1463,838,337
  - question tabs: 2466,1627,630,72
  - unsure chip: 2476,829,662,37

## control_marking_scheme_q4.png
- size: 3200x1800
- screen: Marking scheme (answer key points) view of the right panel for Q4.
- route: /medha/evaluator-workspace/bundles/168/scripts/191
- regions (x,y,w,h):
  - marks dock: 2362,1463,838,337
  - AI ready chip: 2389,30,160,50
  - Review & submit button: 2853,20,316,72
  - page viewer canvas (scan pages, scrollable): 192,112,2168,1600
  - question tabs: 2466,1627,630,72
  - scheme panel: 2394,400,774,402

## control_no_suggestion_q2.png
- size: 3200x1800
- screen: A question without a Medha AI suggestion: "Mark it as usual."
- route: /medha/evaluator-workspace/bundles/168/scripts/191
- regions (x,y,w,h):
  - AI suggestion panel: 2394,400,774,137
  - AI ready chip: 2389,30,160,50
  - Review & submit button: 2853,20,316,72
  - page viewer canvas (scan pages, scrollable): 192,112,2168,1600
  - AI card (mark + key points): 2394,400,774,137
  - suggested mark + Accept: 2424,426,714,28
  - marks dock: 2362,1463,838,337
  - question tabs: 2466,1627,630,72

## control_workspace_q4.png
- size: 3200x1800
- screen: Evaluator marking workspace, bundle 168 script, Q4 (partial credit): scanned handwritten page with Medha AI mapped answer region (purple) beside the AI suggestion panel (suggested 6/12; key points matched / unsure / missed with reasoning; Accept 6 button).
- route: /medha/evaluator-workspace/bundles/168/scripts/191
- regions (x,y,w,h):
  - AI suggestion panel: 2394,400,774,1276
  - AI ready chip: 2389,30,160,50
  - Review & submit button: 2853,20,316,72
  - page viewer canvas (scan pages, scrollable): 192,112,2168,1600
  - AI card (mark + key points): 2394,400,774,1158
  - suggested mark + Accept: 2424,426,714,64
  - Accept button: 2970,426,168,64
  - marks dock: 2362,1463,838,337
  - question tabs: 2466,1627,630,72
  - unsure chip: 2476,829,662,37

## control_workspace_q7.png
- size: 3200x1800
- screen: Q7 suggestion 8.5/12.
- route: /medha/evaluator-workspace/bundles/168/scripts/191
- regions (x,y,w,h):
  - AI suggestion panel: 2394,400,774,1400
  - AI ready chip: 2389,30,160,50
  - Review & submit button: 2853,20,316,72
  - page viewer canvas (scan pages, scrollable): 192,112,2168,1600
  - AI card (mark + key points): 2394,400,774,1400
  - suggested mark + Accept: 2424,426,714,64
  - Accept button: 2946,426,192,64
  - marks dock: 2362,1463,838,337
  - question tabs: 2466,1627,630,72
  - unsure chip: 2476,1220,662,37

## control_workspace_q8.png
- size: 3200x1800
- screen: Evaluator marking workspace, Q8 (suggested 9/12): handwriting with mapped answer region and key point list with matched ticks and flagged-unsure points.
- route: /medha/evaluator-workspace/bundles/168/scripts/191
- regions (x,y,w,h):
  - AI suggestion panel: 2394,400,774,1400
  - AI ready chip: 2389,30,160,50
  - Review & submit button: 2853,20,316,72
  - page viewer canvas (scan pages, scrollable): 192,112,2168,1600
  - AI card (mark + key points): 2394,400,774,1400
  - suggested mark + Accept: 2424,426,714,64
  - Accept button: 2970,426,168,64
  - marks dock: 2362,1463,838,337
  - question tabs: 2466,1627,630,72
  - unsure chip: 2476,1286,662,37

## markui_q4_scrolled.png
- size: 3200x1800
- screen: Q4 with the AI panel scrolled to the end (key point reasoning, Compare, What the AI read, Unattempted).
- route: /medha/evaluator-workspace/bundles/168/scripts/191
- regions (x,y,w,h):
  - AI suggestion panel: 2394,156,774,1276
  - AI ready chip: 2389,30,160,50
  - Review & submit button: 2853,20,316,72
  - page viewer canvas (scan pages, scrollable): 192,112,2168,1600
  - AI card (mark + key points): 2394,156,774,1158
  - suggested mark + Accept: 2424,182,714,64
  - Accept button: 2970,182,168,64
  - marks dock: 2362,1463,838,337
  - question tabs: 2466,1627,630,72
  - unsure chip: 2476,585,662,37

## markui_q4_tall.png
- size: 3200x3000
- screen: TALL variant (1600x1500 CSS viewport): Q4 workspace with the whole AI card visible: suggested 6/12, matched, unsure and missed key points with written reasoning, Compare, What the AI read.
- route: /medha/evaluator-workspace/bundles/168/scripts/191
- regions (x,y,w,h):
  - AI suggestion panel: 2394,400,774,1276
  - AI ready chip: 2389,30,160,50
  - Review & submit button: 2853,20,316,72
  - page viewer canvas (scan pages, scrollable): 192,112,2168,2800
  - AI card (mark + key points): 2394,400,774,1158
  - suggested mark + Accept: 2424,426,714,64
  - Accept button: 2970,426,168,64
  - marks dock: 2362,2663,838,337
  - question tabs: 2466,2827,630,72
  - unsure chip: 2476,829,662,37

## markui_q8_tall.png
- size: 3200x3000
- screen: TALL variant (1600x1500): Q8 suggested 9/12 with every key point listed (matched ticks, unsure flags) in the panel beside the scan.
- route: /medha/evaluator-workspace/bundles/168/scripts/191
- regions (x,y,w,h):
  - AI suggestion panel: 2394,400,774,2014
  - AI ready chip: 2389,30,160,50
  - Review & submit button: 2853,20,316,72
  - page viewer canvas (scan pages, scrollable): 192,112,2168,2800
  - AI card (mark + key points): 2394,400,774,1896
  - suggested mark + Accept: 2424,426,714,64
  - Accept button: 2970,426,168,64
  - marks dock: 2362,2663,838,337
  - question tabs: 2466,2827,630,72
  - unsure chip: 2476,1286,662,37

## readui_compare_q4_tall.png
- size: 3200x3000
- screen: TALL variant (1600x1500): "Compare" dialog: what Medha AI read of the handwriting next to the scan.
- route: /medha/evaluator-workspace/bundles/168/scripts/191
- regions (x,y,w,h):
  - dialog: 928,150,1344,2266

## readui_paper_answer_key.png
- size: 3200x1800
- screen: Question paper & answer key tab: locked paper, uploaded files, structure tree with answer-key points matched ("27 matched / 2 to check").
- route: /medha/evaluation-admin-workspace/subjects/E2E-24BS1T02-Linear-Algebra-Calculus%E2%87%A512
- regions (x,y,w,h):
  - subject header: 558,122,1404,84
  - tabs: 558,238,1766,72
  - structure tree: 558,1269,2600,47

## readui_transcript_q4.png
- size: 3200x1800
- screen: Q4 with "What the AI read" expanded: transcription text of the handwriting beside the page.
- route: /medha/evaluator-workspace/bundles/168/scripts/191
- regions (x,y,w,h):
  - AI suggestion panel: 2394,0,774,1432
  - AI ready chip: 2389,30,160,50
  - Review & submit button: 2853,20,316,72
  - page viewer canvas (scan pages, scrollable): 192,112,2168,1600
  - AI card (mark + key points): 2394,0,774,532
  - marks dock: 2362,1463,838,337
  - question tabs: 2466,1627,630,72
  - transcript: 2428,758,706,640

## readui_transcript_q4_tall.png
- size: 3200x3000
- screen: TALL variant (1600x1500): "What the AI read" expanded: Medha AI's transcription of the Q4 answer beside the scanned page with mapped answer region.
- route: /medha/evaluator-workspace/bundles/168/scripts/191
- regions (x,y,w,h):
  - AI suggestion panel: 2394,400,774,2058
  - AI ready chip: 2389,30,160,50
  - Review & submit button: 2853,20,316,72
  - page viewer canvas (scan pages, scrollable): 192,112,2168,2800
  - AI card (mark + key points): 2394,400,774,1158
  - suggested mark + Accept: 2424,426,714,64
  - Accept button: 2970,426,168,64
  - marks dock: 2362,2663,838,337
  - question tabs: 2466,2827,630,72
  - unsure chip: 2476,829,662,37
  - transcript: 2428,1784,706,640

## ingestui_batch31_overview.png
- size: 3200x1800
- screen: Batch #31 (523 MB ZIP, 101 scripts) overview with counts and needs-review status.
- route: /medha/evaluation-admin-workspace/uploads/batch-31%E2%87%A531
- regions (x,y,w,h):
  - batch title + status: 558,122,1260,105
  - stat tiles: 558,397,626,192

## ingestui_batch31_scripts.png
- size: 3200x1800
- screen: Batch #31 Scripts tab.
- route: /medha/evaluation-admin-workspace/uploads/batch-31%E2%87%A531
- regions (x,y,w,h):
  - batch title + status: 558,122,1260,105

## ingestui_batch_overview.png
- size: 3200x1800
- screen: Upload batch #33 overview: scripts received, ready for bundling, need checking, still processing; green "All scripts processed" banner; by-subject table.
- route: /medha/evaluation-admin-workspace/uploads/batch-33%E2%87%A533
- regions (x,y,w,h):
  - batch title + status: 558,122,1458,105
  - stat tiles: 558,397,626,192
  - All scripts processed banner: 648,663,2484,84
  - by subject table: 558,820,150,51

## ingestui_batch_scripts.png
- size: 3200x1800
- screen: Batch #33 Scripts tab: the scripts produced from the ZIP.
- route: /medha/evaluation-admin-workspace/uploads/batch-33%E2%87%A533
- regions (x,y,w,h):
  - batch title + status: 558,122,1458,105

## ingestui_batch_stages_tall.png
- size: 3200x2500
- screen: TALL variant (1600x1250 CSS viewport): batch #33 with the Ingestion pipeline expanded: upload verified, archive validated and indexed, script identification, registration matching, etc., each Complete 2/2.
- route: /medha/evaluation-admin-workspace/uploads/batch-33%E2%87%A533
- regions (x,y,w,h):
  - batch title + status: 558,122,1458,105
  - stat tiles: 558,397,626,192
  - ingestion pipeline stages: 592,1252,2532,1167

## ingestui_bundles.png
- size: 3200x1800
- screen: Bundles tab: bundles with script counts, assigned evaluators (Ramchander Peddada + Medha AI) and status.
- route: /medha/evaluation-admin-workspace/subjects/E2E-24BS1T02-Linear-Algebra-Calculus%E2%87%A512
- regions (x,y,w,h):
  - subject header: 558,122,1404,84
  - tabs: 558,238,1766,72
  - Medha AI seat: 558,586,2600,775

## ingestui_cycle_overview.png
- size: 3200x1800
- screen: Exam subject 24BS1T02 Linear Algebra & Calculus: overview with readiness checklist (rule set, paper approved, scripts ready, bundles created, evaluators assigned) and the pipeline counts Registered / Uploaded / Ready / Bundled / Evaluated / Final.
- route: /medha/evaluation-admin-workspace/subjects/E2E-24BS1T02-Linear-Algebra-Calculus%E2%87%A512
- regions (x,y,w,h):
  - subject header: 558,122,1404,84
  - tabs: 558,238,1766,72
  - readiness checklist: 592,378,2532,148
  - pipeline counters: 558,1243,420,137

## ingestui_exceptions.png
- size: 3200x1800
- screen: Batch #31 Reconciliation tab: exceptions list (file, kind, reason, age) that need checking, with Re-upload scripts.
- route: /medha/evaluation-admin-workspace/uploads/batch-31%E2%87%A531
- regions (x,y,w,h):
  - issues header: 560,399,2596,114
  - Re-upload button: 560,399,2596,114
  - exception rows: 592,537,2532,131

## ingestui_scripts_list.png
- size: 3200x1800
- screen: Subject Scripts tab: barcode, status (Ready), problem columns.
- route: /medha/evaluation-admin-workspace/subjects/E2E-24BS1T02-Linear-Algebra-Calculus%E2%87%A512
- regions (x,y,w,h):
  - subject header: 558,122,1404,84
  - tabs: 558,238,1766,72
  - scripts table: 560,442,2596,96

## ingestui_uploads_completed.png
- size: 3200x1800
- screen: Script Uploads filtered to Completed.
- route: /medha/evaluation-admin-workspace/uploads
- regions (x,y,w,h):
  - batch list card: 558,394,2600,1390
  - page title: 558,122,1230,105
  - batch list: 592,513,2532,150

## ingestui_uploads_list.png
- size: 3200x1800
- screen: Admin > Script Uploads: every upload batch with file name, subject, status chip (Completed / Needs review), script counts, ready and "could not be read" counts, Review scripts buttons.
- route: /medha/evaluation-admin-workspace/uploads
- regions (x,y,w,h):
  - batch list card (all rows): 558,394,2600,1390
  - page title: 558,122,1230,105
  - status filter tabs: 558,259,858,86
  - batch list: 592,869,2260,150
  - Upload scripts button: 2670,155,488,72

## dash_admin_activity.png
- size: 3200x1800
- screen: Admin Activity log.
- route: /medha/evaluation-admin-workspace/activity
- regions (x,y,w,h):
  - page title: 558,122,976,105

## dash_admin_dashboard.png
- size: 3200x1800
- screen: Admin dashboard: pipeline counters (Registered, Present, Uploaded, Bundled, Evaluated, Final), Needs action list, Subjects behind.
- route: /medha/evaluation-admin-workspace/dashboard
- regions (x,y,w,h):
  - Needs action card: 558,608,2600,784
  - counter tiles row (all six): 558,384,2600,189
  - page title: 558,122,268,68
  - counter tiles: 558,383,407,192
  - needs action: 608,657,2332,47
  - subjects behind: 608,1474,2282,47

