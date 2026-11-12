# Huddle: the AI treasurer for sports clubs

Huddle is a small web app that helps a sports club treasurer keep a player roster, prepare PayPal Sandbox bills for parents, and see which invoices are paid or overdue. The React screen talks to a FastAPI service; the service uses Gemini to understand chat requests and PayPal Sandbox to manage invoices. Sending, reminding, or cancelling an invoice waits in a human-reviewed Referee queue.

## Live demo

**Frontend:** `https://YOUR-HUDDLE-FRONTEND.onrender.com`  
**Backend health check:** `https://YOUR-HUDDLE-BACKEND.onrender.com/health`

Replace these placeholders with the addresses Render gives you after deployment.

## Run locally in 5 steps

Use Windows PowerShell. You need Python 3.11 or newer and Node.js installed.

### 1. Add your local settings

If you do not already have a `.env` file, copy the example:

```powershell
Copy-Item .env.example .env
```

Open `.env` in a text editor and enter your **PayPal Sandbox** app details and Gemini API key. Keep `.env` private; never upload it to GitHub. The PayPal base URL for Sandbox is `https://api-m.sandbox.paypal.com`.

### 2. Install the Python packages

Run these commands from the project folder:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

If `.venv` already exists, you can skip the first command.

### 3. Start the backend

In PowerShell window 1, from the project folder:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Leave this window open. The API is at `http://localhost:8000`; its health check is `http://localhost:8000/health`.

### 4. Install the frontend packages

Open PowerShell window 2 and go to the frontend folder:

```powershell
cd frontend
npm install
```

### 5. Start the frontend

In the same second window:

```powershell
npm run dev
```

Open the Vite address printed in PowerShell, usually `http://localhost:5173`. Keep both windows open while using Huddle. Press **Ctrl+C** in a window to stop that server.

## Deploy on Render

The root `render.yaml` defines two Render services: a Python web service for the backend and a static site for the frontend. Render runs the backend on its assigned `PORT`; the frontend gets the backend's public Render URL at build time. Render's Blueprint `sync: false` entries ask for secret values in the dashboard rather than storing them in this file.

### Beginner deployment steps

1. **Make sure private files stay private.** The root `.gitignore` excludes `.env`, frontend environment files, and runtime JSON data. `data/demo_roster.json` is the only data file allowed into Git. Never use `git add -f` on `.env` or runtime data.
2. **Create a GitHub repository.** On GitHub, create an empty repository for Huddle. Do not upload `.env` or `data/roster.json`.
3. **Upload the project from PowerShell.** Open PowerShell in the project folder and run the following. Replace the GitHub address with the one shown for your new repository. Check that `.env`, `.venv`, `frontend/node_modules`, and `data/roster.json` do **not** appear in `git status --short` before committing.

   ```powershell
   git init
   git add .
   git status --short
   git commit -m "Prepare Huddle for Render"
   git branch -M main
   git remote add origin https://github.com/YOUR-USERNAME/YOUR-REPOSITORY.git
   git push -u origin main
   ```

   If Git asks who you are, set your Git name and email with `git config --global user.name "Your Name"` and `git config --global user.email "you@example.com"`. Do not put passwords or API keys in these commands.
4. **Create the Render Blueprint.** Sign in to Render, choose **New → Blueprint**, connect the GitHub repository, and deploy the Blueprint. Render reads `render.yaml` and creates both services.
5. **Enter the requested settings in Render.** For `PAYPAL_CLIENT_ID`, `PAYPAL_SECRET`, `GEMINI_API_KEY`, and `GEMINI_MODEL`, enter the values for your own accounts. Set `PAYPAL_BASE_URL` to `https://api-m.sandbox.paypal.com` so the demo uses Sandbox. For the initial `CORS_ORIGINS` prompt, enter `http://localhost:5173` temporarily; you will replace it in the next step. Do not paste these values into GitHub, this README, or chat.
6. **Wait for both deploys to finish.** Open each service in Render. Copy the frontend's `onrender.com` address. In the **backend** service, open **Environment**, change `CORS_ORIGINS` to that exact frontend address (no trailing slash), then save and deploy. This lets the browser frontend call your API.
7. **Open the live frontend.** Visit the frontend address. `VITE_API_URL` is wired to the backend URL by the Blueprint. Check the backend by opening its address plus `/health`; it should return `{"status":"ok"}`.
8. **Start a demo roster.** On the live page, click **Load demo roster** and confirm. It creates 12 fictional players with blank parent emails; this is safe for a fresh demo and avoids billing made-up email addresses.

Render's free service filesystem is temporary. Huddle creates `data/roster.json`, `data/invoice_map.json`, and `data/queue.json` if they are missing, so a fresh service starts successfully. The files can still disappear after a restart or redeploy; the demo roster button can reload players. Use a database or persistent storage before relying on Huddle for real club records.

## Environment variables

| Variable | Used by | What to enter |
| --- | --- | --- |
| `PAYPAL_CLIENT_ID` | Backend | PayPal Sandbox REST app client ID. Secret in Render. |
| `PAYPAL_SECRET` | Backend | PayPal Sandbox REST app secret. Secret in Render. |
| `PAYPAL_BASE_URL` | Backend | `https://api-m.sandbox.paypal.com` for Sandbox. |
| `GEMINI_API_KEY` | Backend | Your Google AI Studio key. Secret in Render. |
| `GEMINI_MODEL` | Backend | A Gemini model enabled for your key. |
| `CORS_ORIGINS` | Backend | Comma-separated allowed website origins. Locally defaults to `http://localhost:5173,http://127.0.0.1:5173`; in Render set it to the frontend URL. |
| `VITE_API_URL` | Frontend build | The backend URL. Render fills it from the backend service; locally defaults to `http://localhost:8000`. No API keys belong in frontend variables. |

## Short architecture explanation

- **Frontend:** Vite serves the React dashboard. The browser sends HTTP requests to the backend URL in `VITE_API_URL`.
- **Backend:** FastAPI provides `/chat`, `/roster`, `/board`, `/queue`, `/invoices`, `/summary`, and related endpoints. It binds to Render's `PORT` on `0.0.0.0`.
- **PayPal Sandbox:** The backend creates and reads test invoices using credentials stored only in backend environment variables.
- **Gemini:** The backend asks Gemini to understand natural-language requests and choose approved tools. The API key is never sent to the browser.
- **Referee queue:** Sending, reminding, or cancelling is queued for human approval before the backend calls PayPal.
- **Local JSON storage:** Roster, invoice links, and queue entries live under `data/`. This is convenient for a demo, but not durable storage on Render Free.

## How PayPal and AI are used

Gemini interprets what a treasurer types, such as “prepare drafts for U10” or “show my summary.” Python code decides which tool to run and makes the actual PayPal API request. Gemini never receives PayPal credentials. Creating invoices creates drafts; the Referee queue is the only path to sending invoices, reminders, or cancellations.

## Safety notes for a public demo

- Use **Sandbox** credentials only. Do not use a live PayPal client ID or secret.
- `/chat` and `/roster/parse` are limited to 20 requests per IP per minute. Chat messages are limited to 2,000 characters; pasted rosters are limited to 20,000 characters. This in-memory limit is a basic demo guard, not a complete abuse-prevention system.
- The API has no user login. Queue approval endpoints are publicly reachable on the demo, so someone who finds the site could approve a Sandbox action. Sandbox prevents real money movement, but public users could clutter the test account or use Gemini quota. Add authentication and stronger shared rate limiting before using real accounts or real data.
- There is no Git history in the project folder yet, so existing history cannot be audited. The local `.env` contains your credentials and is ignored by `.gitignore`; it must stay out of GitHub. The source/example files use placeholders rather than credentials.
