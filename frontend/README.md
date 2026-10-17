# Cosmetic Scanner app (Omar)

One Expo + TypeScript codebase for Android, iOS and the web. The user scans a
barcode (phone camera), uploads or takes a photo, or types the number. The app
starts the n8n pipeline, shows each step as n8n reports it, then shows the
report built by `POST /report/build` (see `docs/report.md`).

## Run

```powershell
cd frontend
npm install
copy .env.example .env      # then fill in the n8n URLs and key
npm run web                 # browser
npm start                   # phone: scan the QR code with Expo Go (same Wi-Fi)
```

From a phone, `localhost` is the phone itself: use your computer's LAN IP in `.env`.

Checks: `npm run typecheck`, `npm run lint`, `npm test`.

## Screens

| Route | What it does |
|---|---|
| `/` | Barcode camera (phones), photo upload or capture, manual number with check-digit validation |
| `/progress` | The 8 pipeline steps, ticked as n8n reports them; label-photo request, held-back and error states |
| `/report` | Ingredient list as printed on the product (tap a name for details), validation result, overview, details per ingredient, animal testing, sources, limitations |

## What the app needs from n8n (Lyna)

1. **Scan webhook** (`EXPO_PUBLIC_SCAN_URL`, POST, header `X-API-Key`). Body:
   `{ barcode, label_image_base64, label_image_mime, market: "EU", assessment_date }`.
   The label photo is sent inline as base64, so no separate upload service is needed.
2. **Progress.** To show real steps, answer straight away with
   `{ request_id, status: "running", stage }` and expose a **status webhook**
   (`EXPO_PUBLIC_STATUS_URL`, GET `?request_id=`) that returns the same shape until the run ends.
   `stage` is one of `product, ingredients, normalize, evidence, regulatory, toxicology, ethics, validation`.
   If the scan webhook answers only at the end, the app still works but shows no step-by-step progress.
3. **Final answer** (either webhook): the public result with `status` of
   `completed` (with `report` = output of `/report/build`), `needs_input` (with `next_action.message`),
   `needs_review` (with `validation`), or anything else with `error.message`.
4. **CORS** on both webhooks for the web app: allow the app's origin and the `Content-Type, X-API-Key` headers.

The API key is bundled into the app, so use a key that only protects this project's webhook.
