# Cosmetic Scanner app (Omar)

One Expo + TypeScript codebase for Android, iOS and the web. The user scans a
barcode (phone camera), uploads or takes a photo, or types the number. The app
sends one request to the n8n workflow, waits for the answer, and shows the report
(`app/report/schemas.py: Report`, version 1.0).

## Run

```powershell
cd frontend
npm install
copy .env.example .env      # then fill in the n8n URL and key
npm run web                 # browser
npm start                   # phone: scan the QR code with Expo Go (same Wi-Fi)
```

From a phone, `localhost` is the phone itself: use your computer's LAN IP in `.env`.
For a local test, start the backend first (`docker compose up -d --build` in the repo root).

Checks: `npm run typecheck`, `npm run lint`, `npm test`.

## Screens

| Route | What it does |
|---|---|
| `/` | Barcode camera (phones), photo upload or capture, manual number with check-digit validation |
| `/progress` | The workflow's steps while the scan runs; the label-photo request and error states |
| `/report` | Ingredient list as printed on the product (tap a name for details), check results, overview, details per ingredient (EU rule, conditions, hazards, what is unknown), animal testing, sources with their text, limitations |

## What the app sends and receives

The full contract is in `docs/N8N_SETUP.md`. In short:

- **Request:** `POST EXPO_PUBLIC_SCAN_URL`, header `X-API-Key: EXPO_PUBLIC_WEBHOOK_KEY`, body
  `{ barcode, barcode_image_ref, label_image_ref }`. A photo is sent inline as a `data:image/...;base64,` URI in
  both image fields: the API tries to read a barcode from it first, then reads the ingredient list (OCR).
- **Answer:** one JSON object with `status`:
  `completed` or `needs_review` → `report` is shown (needs review shows the failed checks);
  `needs_input` → the app asks for a photo of the ingredient list; anything else → `error.message`.
- n8n answers only when the whole pipeline has run (usually 10 to 30 seconds; a sleeping Render service adds
  up to a minute). The app waits up to 3 minutes. n8n does not report steps as it goes, so the step list shows
  what will happen rather than a live position.

The webhook key is bundled into the app, so it only protects this project's webhook, nothing else.

`tests/fixtures/report-balea.json` is a real report from the API, used to check that the app reads the
API's format. Regenerate it if `app/report/schemas.py` changes.
