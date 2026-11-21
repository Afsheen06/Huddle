# Huddle — AI Treasurer for Indian Clubs and Academies

Huddle is an AI treasurer for Indian sports clubs and academies that collect monthly fees from parents. It keeps a player roster and fee totals in rupees, prepares UPI payment links and QR codes, and gives the treasurer one place to review collections and follow-ups. For the hackathon demo, Gemini helps understand requests and PayPal Sandbox demonstrates invoice workflows. PayPal's current published currency list does not include INR, so PayPal invoices use USD as **test amounts only**; those dollars are not rupee conversions and are not real club collections. [PayPal supported currency codes](https://developer.paypal.com/api/codes/currency/)

## Features

- Import a pasted roster, let Gemini parse it, review the extracted players, and save it.
- Show the roster, monthly fees, manual collection totals, and invoice status on a responsive board.
- Generate an INR UPI intent link and QR code for each player's fee.
- Chat in everyday language to ask for fee summaries, prepare invoice drafts, and draft overdue reminders.
- View PayPal Sandbox invoices separately from the rupee club fee.
- Review sensitive PayPal actions in the Referee queue before anything is sent, reminded, or cancelled.
- Load a fictional Indian demo team or reset Huddle's local demo state for a fresh judge run.

## How payments are represented

### UPI fees in India

The player roster and Huddle scoreboard use INR (₹). Clicking a player displays their fee, a UPI QR, and a `upi://pay` link using `CLUB_UPI_ID` and `CLUB_NAME`. The payer completes the payment in their UPI app. Huddle does not get an automatic bank or UPI confirmation. After checking their own payment records, a treasurer may click **Mark as paid (UPI)**. The board labels this as a manual record, not a verified transaction.

The default UPI ID `yourclub@upi` is intentionally fake. Configure the club's actual UPI ID privately in the backend environment. Never put a real UPI ID in the repository.

### PayPal Sandbox invoices

Huddle calls PayPal's Invoicing REST API to create and manage mock invoices. The published supported-currency list currently omits INR, so Huddle keeps the club fee in INR but sends USD to PayPal Sandbox. The UI and invoice descriptions identify the USD value as a **Sandbox test amount only**; it is not converted from INR or evidence that the family paid the club. Sandbox invoices and UPI collections are separate demonstrations.

## AI and safety

Huddle uses Google's Gemini API through the official `google-genai` Python SDK. Gemini function calling can select backend tools such as reading the fee summary, listing invoices, or preparing draft invoices. Gemini structured output parses messy roster text into reviewable player fields. Its tone-aware chasing flow drafts friendly, polite-but-firm, or formal reminders based on how overdue a linked Sandbox invoice is; reminders include the rupee club fee and UPI link.

Creating a draft is allowed directly. Sending an invoice, sending a reminder, or cancelling an invoice is a sensitive action: Huddle places it in the **Referee queue**. A human must approve it before the backend calls PayPal. Rejecting a proposal does not call PayPal. A PayPal Sandbox payment never counts as a manual UPI collection.

## Known limitations

- UPI links and QR codes only start a payment in the payer's UPI app. Huddle does not verify or receive payment notifications.
- Manual **Mark as paid** entries rely on the treasurer checking an external bank/UPI record.
- PayPal invoices are USD Sandbox test invoices because INR is absent from PayPal's published supported currency list. Sandbox invoices do not process real money.
- Only the first three demo players use `TEST_CLIENT_EMAIL`; their address should be a Sandbox Personal email. Other demo parent emails use `example.com` placeholders and are skipped during bulk invoice creation.
- The public demo has no user login. Anyone who can reach it may use public demo endpoints, including resetting local demo data. Do not use real family data or production payment credentials.
- Runtime roster, invoice mapping, queue, and manual payment data live in local JSON files. Render Free storage is temporary and can reset after a restart or redeploy. PayPal Sandbox keeps its invoices separately.
- Gemini can misunderstand a request. Review the generated roster, draft, and every Referee proposal before continuing.
- The simple per-IP limiter on `/chat` and `/roster/parse` is in-memory and process-local, not production-grade abuse protection.

## Run locally (Windows PowerShell)

Use two PowerShell windows from the project folder. Install Python 3.11+ and Node.js first.

### 1. Create the private backend settings file

```powershell
Copy-Item .env.example .env
notepad .env
```

If `.env` already exists, do not overwrite it. Add PayPal Sandbox and Gemini credentials. For a local UPI QR demo, you can leave the deliberately fake `CLUB_UPI_ID=yourclub@upi`; it will not collect money. Set `CLUB_NAME` to the demo club name.

### 2. Install backend dependencies

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

If `.venv` already exists, skip its creation.

### 3. Start FastAPI (PowerShell window 1)

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Keep this window open. Check `http://localhost:8000/health`; it should return `{"status":"ok"}`.

### 4. Install frontend dependencies (PowerShell window 2)

```powershell
cd frontend
Copy-Item .env.example .env
npm install
```

If `frontend/.env` already exists, keep it. Its `VITE_API_URL` should be `http://localhost:8000`. Never put backend secrets in the frontend environment file.

### 5. Start the Vite website

```powershell
npm run dev
```

Open the local address printed in the terminal, usually `http://localhost:5173`. Both terminals must stay open. Use **Load demo roster** to seed players or **Reset demo** to clear Huddle's local queue, invoice links, and manual marks and reload the sample roster. Reset does not delete PayPal Sandbox invoices.

## Deploy on Render

The root `render.yaml` Blueprint defines `huddle-backend` (FastAPI/Uvicorn) and `huddle-frontend` (Vite static site, published from `frontend/dist`).

1. Push the project to GitHub. Do not commit `.env`, frontend secrets, virtual environments, or runtime JSON files.
2. In Render, choose **New → Blueprint**, connect this repository, and deploy the Blueprint.
3. In the backend service's **Environment** settings, provide your PayPal Sandbox and Gemini values. Keep secrets there only.
4. Set `CORS_ORIGINS` to the exact deployed frontend origin, such as `https://your-huddle-frontend.onrender.com`.
5. Set `CLUB_NAME` for the demo and set `TEST_CLIENT_EMAIL` to the Sandbox Personal email for the first three demo players. Remaining `example.com` placeholders are skipped by bulk billing. Keep the fake UPI ID for a QR-only demonstration, or configure the real club UPI ID privately if appropriate.
6. Wait for both services to deploy. Open the backend `/health` URL, then open the frontend and click **Reset demo** to prepare a clean local Huddle demo.

Render Free uses temporary local files. Reset or redeploy may be needed to restore the fictional roster; PayPal Sandbox invoices are not cleared by Huddle's reset.

## Environment variables

| Variable | Used by | Purpose |
| --- | --- | --- |
| `PAYPAL_CLIENT_ID` | Backend secret | PayPal Sandbox REST app client ID. |
| `PAYPAL_SECRET` | Backend secret | PayPal Sandbox REST app secret. |
| `PAYPAL_BASE_URL` | Backend | Sandbox API base URL: `https://api-m.sandbox.paypal.com`. |
| `GEMINI_API_KEY` | Backend secret | Google Gemini API key. |
| `GEMINI_MODEL` | Backend | Gemini model enabled for the API key. |
| `TEST_CLIENT_EMAIL` | Backend, optional | Sandbox Personal email assigned to the first three demo players and used by `scripts/test_invoice.py`; all other demo addresses remain placeholders. |
| `CORS_ORIGINS` | Backend | Comma-separated allowed frontend origins. |
| `DEFAULT_CURRENCY` | Backend | Club fee currency; defaults to `INR`. |
| `CURRENCY_SYMBOL` | Backend | Display symbol; defaults to `₹`. |
| `CLUB_UPI_ID` | Backend | UPI payee ID for the link and QR; fake default is `yourclub@upi`. |
| `CLUB_NAME` | Backend | Name shown in UPI payment instructions. |
| `VITE_API_URL` | Frontend build | Public backend URL; contains no secrets. |

PayPal Sandbox invoice currency is deliberately fixed to USD and does not follow `DEFAULT_CURRENCY`.

## Architecture

1. The **React** page calls the **FastAPI** backend at `VITE_API_URL`.
2. The backend reads private settings, stores demo data in JSON, creates UPI links/QR codes, and calls Gemini or PayPal when needed.
3. **Gemini** interprets chat requests and roster text. The backend executes approved tool calls; Gemini never receives PayPal credentials.
4. **PayPal Sandbox** stores mock USD invoices. The separate UPI flow gives parents a payment intent link/QR and does not report payments back to Huddle.
5. The **Referee queue** holds send, reminder, and cancel requests until a human approves them.

## Routes for judges

| Method and route | Purpose |
| --- | --- |
| `GET /health` | Backend health check. |
| `GET /config` | Public display settings; no secrets. |
| `GET /summary`, `GET /board` | INR club fee totals and player statuses. |
| `GET /roster` | Read roster. |
| `POST /roster/parse`, `POST /roster/save` | Parse and save a reviewed roster. |
| `GET /roster/{player_key}/payment` | Return a player's UPI link and QR. |
| `POST /roster/mark-paid` | Manually mark a UPI fee as paid. |
| `POST /demo/seed` | Load the fictional demo roster. |
| `POST /demo/reset` | Clear local queue, invoice mapping and manual marks; reload demo roster. Does not delete PayPal invoices. |
| `GET /invoices` | List PayPal Sandbox invoices. |
| `POST /chat` | Chat with the Gemini agent. |
| `GET /queue` | List Referee proposals. |
| `POST /queue/{id}/approve`, `POST /queue/{id}/reject` | Approve and execute, or reject a proposal. |

## Credits

- **Google Gemini API and `google-genai`** — chat function calling and structured roster parsing.
- **PayPal Developer Invoicing REST API (Sandbox)** — mock USD invoice workflow.
- **FastAPI**, **Uvicorn**, **Pydantic**, **Requests**, and **python-dotenv** — Python backend and configuration.
- **React** and **Vite** — frontend framework and build tool.
- **AG Grid Community** — filterable, sortable invoice ledger.
- **qrcode** — UPI QR image generation.

See [LICENSE](LICENSE) for the MIT license.
