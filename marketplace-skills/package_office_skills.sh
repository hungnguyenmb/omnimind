#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_DIR="${SCRIPT_DIR}/dist"

mkdir -p "$OUT_DIR"
rm -f "$OUT_DIR"/*.zip

pushd "$SCRIPT_DIR" >/dev/null

# Keep public artifact names stable for existing marketplace URLs.
zip -qr "$OUT_DIR/office_meeting_notes.zip" "office-meeting-notes"
zip -qr "$OUT_DIR/office_email_assistant.zip" "office-email-assistant"
zip -qr "$OUT_DIR/office_excel_report.zip" "office-excel-report"
zip -qr "$OUT_DIR/office_document_qa.zip" "office-document-qa"
zip -qr "$OUT_DIR/office_task_planner.zip" "office-task-planner"

popd >/dev/null

echo "Packaged skills into: $OUT_DIR"
ls -lh "$OUT_DIR"/*.zip
