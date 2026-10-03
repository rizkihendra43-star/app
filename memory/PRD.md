# UnlockVault — Product Requirements Document

## Original Problem Statement
Aplikasi web untuk membuka file PDF & Excel secara massal, memasukkan daftar password secara massal agar sistem mencari file mana yang cocok dengan tiap password, menghapus password permanen (file berikutnya tidak perlu password lagi), menyimpan/mengunduh hasil secara massal ke folder PC tanpa mengubah bentuk & nama file, tombol hapus file salah, tombol gabung PDF, dan tombol ganti file.

## User Choices
- Upload file via browser lalu proses di server.
- Masukkan daftar password → sistem coba semua password ke tiap file & tandai yang cocok.
- Hasil diunduh sekaligus sebagai 1 ZIP (nama & format tetap).
- Dukungan: PDF dan Excel (.xlsx/.xls/.xlsm).
- Tanpa login / tanpa riwayat.

## Architecture
- Frontend: React 19 + Vite + Tailwind v4 + shadcn/ui. Dark-first design (UnlockVault). Session via localStorage `unlockvault_session`.
- Backend: FastAPI. PDF via `pikepdf`, Excel via `msoffcrypto-tool`, PDF merge via `pypdf`.
- Storage: Emergent Object Storage (prefix `mass-unlocker/{session_id}/`). Metadata in MongoDB `files` collection.
- All processing downloads bytes to a local temp file, processes, re-uploads.

## Core Requirements (static)
1. Bulk upload PDF/Excel.
2. Bulk password matching across files.
3. Permanent password removal (unlock).
4. Bulk ZIP download preserving names/formats.
5. Delete, Replace, Merge-PDF actions.

## Implemented (2026-10-03)
- Upload with encryption auto-detection (locked / ready).
- Match-passwords engine (tries each password per locked file).
- Unlock (removes password; file opens without password afterward — verified).
- Per-file download + bulk ZIP download.
- Delete (with confirm), Replace (re-detects encryption), Merge PDF (>=2 unlocked PDFs).
- Status filters, stats counters, dark/light theme toggle, toasts.
- Tested end-to-end (backend 100%, frontend 100%, iteration_1).

## Backlog / Remaining
- P1: Encrypted Excel (.xlsx) round-trip not verified with a real encrypted file (code path implemented).
- P2: Per-file custom/manual password retry input in the UI.
- P2: Export match report (CSV/JSON).
- P2: Direct "save to folder" via File System Access API (Chrome/Edge).
- P2: Drag-to-reorder PDFs before merge.

## Next Tasks
- Verify encrypted .xlsx flow with a sample file.
- Add manual per-file password field.
