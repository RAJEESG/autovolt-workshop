# 🚀⚡ AutoVolt Pro & Cloud HQ — Deployment Guide
## (Supabase Cloud Database & Render.com Web Service Deployment)

നിങ്ങളുടെ **AutoVolt Pro (Workshop Client App)**-ഉം **AutoVolt Cloud HQ (SaaS Master Vendor App)**-ഉം **Supabase-ലും Render.com-ലും** സൗജന്യമായി (Free Tier) ലൈവ് ആയി ഹോസ്റ്റ് ചെയ്യാനുള്ള സമ്പൂർണ്ണ മലയാളം ഗൈഡ് താഴെ നൽകുന്നു.

---

```
                       ┌──────────────────────────────────────────────┐
                       │          1. SUPABASE CLOUD (DATABASE)        │
                       │   • PostgreSQL Database                      │
                       │   • Central Multi-Tenant Storage             │
                       └──────────────────────┬───────────────────────┘
                                              │ Connection (SUPABASE_URL & KEY)
                        ┌─────────────────────┴─────────────────────┐
                        ▼                                           ▼
┌───────────────────────────────────────────┐ ┌───────────────────────────────────────────┐
│     2. RENDER: WORKSHOP CLIENT APP        │ │      3. RENDER: SAAS MASTER VENDOR HQ     │
│   https://autovolt-pro.onrender.com       │ │    https://autovolt-cloud-hq.onrender.com │
│ • For Workshops (Job Book, POS, Billing)  │ │ • For You (Manage Garages, Invoices, CA)  │
│ • Start: uvicorn main:app                 │ │ • Start: uvicorn saas_admin_app:app       │
└───────────────────────────────────────────┘ └───────────────────────────────────────────┘
```

---

## 🌟 PART 1: Supabase-ൽ Database ഉണ്ടാക്കുന്ന വിധം (Supabase Setup)

### Step 1: Supabase അക്കൗണ്ട് തുറക്കുക
1. [supabase.com](https://supabase.com) എന്ന വെബ്സൈറ്റിൽ കയറി നിങ്ങളുടെ GitHub അക്കൗണ്ട് അല്ലെങ്കിൽ Email ഉപയോഗിച്ച് **Sign In / Sign Up** ചെയ്യുക.
2. **"New Project"** ക്ലിക്ക് ചെയ്യുക:
   - **Organization:** നിങ്ങളുടെ പേര് തിരഞ്ഞെടുക്കുക.
   - **Project Name:** `autovolt-saas-db` എന്ന് നൽകുക.
   - **Database Password:** ഓർമ്മയിൽ നിൽക്കുന്ന ഒരു ശക്തമായ പാസ്‌വേർഡ് നൽകുക (ഉദാ: `AutoVolt@2026DbPass`).
   - **Region:** `Singapore (ap-southeast-1)` അല്ലെങ്കിൽ `India / Mumbai` തിരഞ്ഞെടുക്കുക (വേഗത കൂടും).
3. **"Create new project"** ക്ലിക്ക് ചെയ്ത് 1-2 മിനിറ്റ് പ്രൊജക്റ്റ് തയാറാകാൻ കാത്തിരിക്കുക.

---

### Step 2: Database Schema & Tables റൺ ചെയ്യുക
1. ഇടത് വശത്തെ മെനുവിൽ നിന്ന് **"SQL Editor"** (Terminal ഐക്കൺ 📟) ക്ലിക്ക് ചെയ്യുക.
2. **"+ New Query"** ക്ലിക്ക് ചെയ്യുക.
3. ഈ പ്രൊജക്റ്റിലെ [`supabase_schema.sql`](supabase_schema.sql) ഫയലിലെ മുഴുവൻ കോഡും കോപ്പി ചെയ്ത് SQL Editor ബോക്സിൽ പേസ്റ്റ് ചെയ്യുക.
4. താഴെ വലത് ഭാഗത്തുള്ള പച്ച **"Run"** ബട്ടൺ (അല്ലെങ്കിൽ `Ctrl + Enter`) അമർത്തുക.
5. `Success. No rows returned` എന്ന് കാണിച്ചാൽ നിങ്ങളുടെ എല്ലാ 25 ടേബിളുകളും (Users, Tenants, Job Cards, Invoices, Inventory, etc.) സജ്ജമായി കഴിഞ്ഞു!

---

### Step 3: API Keys & URL കോപ്പി ചെയ്യുക
1. ഇടത് മെനുവിലെ ഏറ്റവും താഴെയുള്ള **Project Settings** (ഗിയർ ഐക്കൺ ⚙️) ക്ലിക്ക് ചെയ്യുക.
2. അവിടെ **"Data API"** അല്ലെങ്കിൽ **"API"** ക്ലിക്ക് ചെയ്യുക.
3. താഴെ പറയുന്ന രണ്ട് കാര്യങ്ങൾ കോപ്പി ചെയ്ത് സൂക്ഷിക്കുക:
   - **Project URL:** `https://xxxxxxxxxxxx.supabase.co`
   - **service_role (secret) API Key** (അല്ലെങ്കിൽ `anon public` key)

---

## 🌟 PART 2: GitHub-ലേക്ക് കോഡ് അപ്‌ലോഡ് ചെയ്യുക (GitHub Push)

നിങ്ങളുടെ കമ്പ്യൂട്ടറിലെ പ്രൊജക്റ്റ് ഫോൾഡറിൽ നിന്ന് കോഡ് GitHub-ലേക്ക് മാറ്റുക:

```powershell
# 1. പ്രൊജക്റ്റ് ഫോൾഡറിലേക്ക് മാറുക
cd C:\Users\Administrator\.gemini\antigravity\scratch\auto_electric_workshop_manager

# 2. Git initialize ചെയ്യുക
git init
git add .
git commit -m "AutoVolt Pro & Cloud HQ Enterprise SaaS Release"

# 3. നിങ്ങളുടെ GitHub Repo-ലേക്ക് push ചെയ്യുക (ഉദാഹരണം):
git branch -M main
git remote add origin https://github.com/<your-username>/autovolt-pro.git
git push -u origin main
```

---

## 🌟 PART 3: Render.com-ൽ സൗജന്യമായി Host ചെയ്യുന്ന വിധം (Render Cloud Deployment)

Render.com-ൽ നമുക്ക് 2 വെബ് സർവീസുകൾ സൗജന്യമായി ഉണ്ടാക്കാം:
1. **Service 1:** വർക്ക്‌ഷോപ്പുകാർക്കുള്ള ആപ്പ് (**AutoVolt Pro**)
2. **Service 2:** നിങ്ങൾക്ക് വേണ്ടിയുള്ള SaaS Master Admin (**AutoVolt Cloud HQ**)

---

### 🚗 A. Service 1: AutoVolt Pro (Client Workshop App) ഹോസ്റ്റ് ചെയ്യാൻ

1. [render.com](https://render.com)-ൽ കയറി GitHub വഴി ലോഗിൻ ചെയ്യുക.
2. Dashboard-ൽ **"New +"** ബട്ടൺ അമർത്തി **"Web Service"** തിരഞ്ഞെടുക്കുക.
3. **"Build and deploy from a Git repository"** തിരഞ്ഞെടുത്ത് **Next** കൊടുക്കുക.
4. നിങ്ങളുടെ `autovolt-pro` റിപോസിറ്ററി സെലക്ട് ചെയ്യുക.
5. താഴെ നൽകിയിട്ടുള്ള വിവരങ്ങൾ നൽകുക:
   - **Name:** `autovolt-workshop-app` (നിങ്ങൾക്ക് ഇഷ്ടമുള്ള പേര് നൽകാം)
   - **Language / Environment:** `Python 3`
   - **Region:** `Singapore` (ഏഷ്യൻ രാജ്യങ്ങൾക്ക് നല്ല സ്പീഡ് ലഭിക്കും)
   - **Branch:** `main`
   - **Build Command:**
     ```bash
     pip install -r requirements.txt
     ```
   - **Start Command:**
     ```bash
     uvicorn main:app --host 0.0.0.0 --port $PORT
     ```
   - **Instance Type:** `Free` (₹0 / Free tier)

6. **Environment Variables** (രഹസ്യ വിവരങ്ങൾ നൽകാൻ):
   - താഴെയുള്ള **"Add Environment Variable"** ക്ലിക്ക് ചെയ്ത് ഇവ ചേർക്കുക:
     | Key | Value |
     |---|---|
     | `PYTHON_VERSION` | `3.12.10` |
     | `SUPABASE_URL` | `https://xxxxxxxxxxxx.supabase.co` (നിങ്ങളുടെ Supabase Project URL) |
     | `SUPABASE_SERVICE_ROLE_KEY` | (നിങ്ങളുടെ Supabase Secret Key) |
     | `APP_BASE_URL` | `https://autovolt-workshop-app.onrender.com` (Render തരുന്ന ലൈവ് ലിങ്ക്) |

7. **"Deploy Web Service"** ക്ലിക്ക് ചെയ്യുക!
   - 2-3 മിനിറ്റിനുള്ളിൽ ബിൽഡ് പൂർത്തിയായി **Live URL** (e.g. `https://autovolt-workshop-app.onrender.com`) ലഭിക്കും!
   - ആ ലിങ്കിൽ ക്ലിക്ക് ചെയ്താൽ **AutoVolt Pro ലോഗിൻ പേജ്** തുറന്നുവരും.

---

### 🏢 B. Service 2: AutoVolt Cloud HQ (SaaS Master Admin App) ഹോസ്റ്റ് ചെയ്യാൻ

1. Render Dashboard-ൽ വീണ്ടും **"New +"** ➜ **"Web Service"** ക്ലിക്ക് ചെയ്യുക.
2. ഇതേ GitHub Repo വീണ്ടും തിരഞ്ഞെടുക്കുക.
3. വിവരങ്ങൾ നൽകുക:
   - **Name:** `autovolt-cloud-hq`
   - **Language / Environment:** `Python 3`
   - **Region:** `Singapore`
   - **Build Command:**
     ```bash
     pip install -r requirements.txt
     ```
   - **Start Command (പ്രത്യേകം ശ്രദ്ധിക്കുക):**
     ```bash
     uvicorn saas_admin_app:app --host 0.0.0.0 --port $PORT
     ```
   - **Instance Type:** `Free`

4. **Environment Variables:**
   - `PYTHON_VERSION` = `3.12.10`
   - `SUPABASE_URL` = (Supabase URL)
   - `SUPABASE_SERVICE_ROLE_KEY` = (Supabase Secret Key)

5. **"Deploy Web Service"** ക്ലിക്ക് ചെയ്യുക!
   - ഏതാനും നിമിഷങ്ങൾക്കുള്ളിൽ നിങ്ങളുടെ Master Admin പോർട്ടൽ ലൈവ് ആകും (e.g. `https://autovolt-cloud-hq.onrender.com`).
   - ഇതിൽ ലോഗിൻ ചെയ്ത് നിങ്ങൾക്ക് പുതിയ വർക്ക്‌ഷോപ്പുകൾ ചേർക്കാനും, UPI/GST കോൺഫിഗർ ചെയ്യാനും, പണം സ്വീകരിക്കാനും സാധിക്കും!

---

## 📱 PART 4: WhatsApp OTP & UPI തത്സമയം പരിശോധിക്കാൻ

1. **AutoVolt Pro ലിങ്കിൽ (`https://autovolt-workshop-app.onrender.com`) കയറുക.**
2. **Forgot Password ക്ലിക്ക് ചെയ്യുക:**
   - മൊബൈൽ നമ്പറോ `admin` എന്ന് നൽകുക.
   - ഉടനടി **"Open WhatsApp to Receive OTP"** ബട്ടൺ വരും.
   - അതിൽ ക്ലിക്ക് ചെയ്താൽ WhatsApp വഴി 6-അക്ക OTP ലഭിക്കുകയും, അത് എന്റർ ചെയ്ത് പാസ്‌വേർഡ് റീസെറ്റ് ചെയ്യാനും സാധിക്കും.
3. **ബില്ലിംഗ് & UPI:**
   - ബാർകോഡ് സ്കാൻ ചെയ്തോ പാർട്സുകൾ ചേർത്തോ ബിൽ ഉണ്ടാക്കുക.
   - WhatsApp ഷെയർ ക്ലിക്ക് ചെയ്താൽ കസ്റ്റമറുടെ WhatsApp-ലേക്ക് **Dynamic UPI Pay Link** സഹിതം ബിൽ എത്തും.

---

## 💡 ശ്രദ്ധിക്കേണ്ട ചില കാര്യങ്ങൾ (Troubleshooting Tips):

1. **Render Free Tier Spin-down:**
   - Render-ന്റെ Free tier-ൽ 15 മിനിറ്റ് ആരും ഉപയോഗിച്ചില്ലെങ്കിൽ ആപ്പ് ഉറങ്ങും (sleep mode). ആരെങ്കിലും ലിങ്ക് തുറക്കുമ്പോൾ 20-30 സെക്കൻഡ് എടുത്താണ് ആദ്യം ലോഡ് ആവുക. ഇത് ഒഴിവാക്കാൻ [cron-job.org](https://cron-job.org) അല്ലെങ്കിൽ [UptimeRobot](https://uptimerobot.com) വഴി 10 മിനിറ്റിൽ ഒരു Ping നൽകിയാൽ സൈറ്റ് എപ്പോഴും 24/7 വേഗതയിൽ ഉണർന്നിരിക്കും.
2. **Supabase Free Tier Connection:**
   - Supabase PostgreSQL-ൽ ഡാറ്റ സ്റ്റോർ ആകുന്നതിനാൽ Render റീസ്റ്റാർട്ട് ആയാലും നിങ്ങളുടെ ഇൻവോയ്സുകളും കസ്റ്റമർ ഡാറ്റയും സുരക്ഷിതമായി നിലനിൽക്കും!
