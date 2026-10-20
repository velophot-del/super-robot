# Verification result

Actual DOCX curriculum extraction and major-filtered Word stage timetable exports implemented. No new dependency. User originals untouched; timetable copied as project template. Existing XLSX retained.

Actual curriculum:76 parsed rows,0 errors,33 schedulable professional rows. Missing semester,0 hours,placeholder entries and duplicate-name/semester rows retained with notices. Raw fields,source location,weekly periods,duration,tail note retained. Live demo import inactive until admin activates after review.

Word: reference OOXML package/styles/section dimensions/borders/vertical labels; dynamic18–20 weeks,dates,stage spans,two courses with teachers/room/slots; cohorts/pages. Snapshot-only authorized endpoint; major/term/cohort filters. Live fictitious demo created via real APIs,existing plan preserved,Word API+UI download verified.

Checks:22 backend tests,6 frontend tests,build pass,lint exit0 with7 existing warnings. Independent readonly reviewer found no Critical/Important issues. DemoDB backed up first.

Visual limitation: canonical renderer failed on Python3.9 annotations; compatibility task-local copy reached rendering and diagnosed broken soffice wrapper pointing to absent LibreOffice. Python3.12 venv lacks pdf2image. Quick Look fallback produced no image and cancelled. No dependency installed. XML/package verified; Word pagination/visual identity NOT verified. Internal QA DOCX samples are not delivered as visually approved documents.
