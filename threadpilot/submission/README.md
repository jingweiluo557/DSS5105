# Final submission sources (Group19.zip)

The PDFs and Word files in Group19.zip are rendered from the HTML here, so a change to any document is one edit and one command.

| Output | Source | Build |
|---|---|---|
| Readme.pdf, Teams.pdf, Documentation.pdf, Strategic_Recommendations.pdf | the HTML file of the same name | `node build_pdf.cjs <name>.html <out.pdf> "<footer title>"` |
| Evaluation.pdf | `Evaluation.html` + the tables generated from the repo | `python3 make_tables.py && python3 inject.py Evaluation.html _Evaluation.built.html && node build_pdf.cjs _Evaluation.built.html <out.pdf> "Evaluation report"` |
| *.docx | the same HTML | `docx/` holds the pandoc reference document and the conversion steps used (`pandoc <name>.html -f html -t docx --reference-doc docx/reference.docx`) |
| Slide.pdf | `../demo/slides_final/` | `node ../demo/render_slides.cjs --slides ../demo/slides_final --pdf Slide.pdf` |
| Video.mp4 | `../demo/demo_timeline_final.json` on the offline replay | `REPLAY_STEP_PACE=0.5 python3 ../demo/replay_server.py 8765` then `node ../demo/record_demo.cjs --timeline ../demo/demo_timeline_final.json --out dist/demo --compress-waits 8`; `dist/demo/demo_final.mp4` is Video.mp4 |

`make_tables.py` reads `docs/TOOL_SPECIFICATION.md`, `evaluation/EVALUATION.md`, `heldout_questions.json` and `bait_questions.json`, so the appendix tables are never retyped. The generated `fragments/` and `_*.built.html` files are build products and are not committed.
