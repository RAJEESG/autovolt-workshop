# 🚗⚡ AutoVolt Pro — Deployment & Setup Guide
## (മലയാളത്തിലും English-ലും ഉള്ള വിശദമായ ഗൈഡ്)

---

### 🌟 1. Local-ൽ എങ്ങനെ പ്രവർത്തിപ്പിക്കാം (Local Run)

1. Command Prompt / PowerShell തുറക്കുക:
```powershell
cd C:\Users\Administrator\.gemini\antigravity\scratch\auto_electric_workshop_manager
```

2. Python Server സ്റ്റാർട്ട് ചെയ്യുക:
```powershell
python main.py
# അല്ലെങ്കിൽ
uvicorn main:app --reload --port 8000
```

3. Browser-ൽ തുറക്കുക:
👉 **`http://localhost:8000`**

---

### ☁️ 2. Supabase Cloud Database കണക്റ്റ് ചെയ്യാൻ (Supabase Setup)

1. [supabase.com](https://supabase.com) തുറന്ന് നിങ്ങളുടെ Free Account-ലേക്ക് ലോഗിൻ ചെയ്യുക.
2. പുതിയ പ്രൊജക്റ്റ് ഉണ്ടാക്കുക (Project Name: `autovolt-workshop`).
3. ഇടത് മെനുവിലെ **SQL Editor** തുറക്കുക ➜ `New Query` ക്ലിക്ക് ചെയ്യുക.
4. ഈ പ്രൊജക്റ്റിലെ [`supabase_schema.sql`](file:///C:/Users/Administrator/.gemini/antigravity/scratch/auto_electric_workshop_manager/supabase_schema.sql) ഫയലിലെ കോഡ് കോപ്പി ചെയ്ത് പേസ്റ്റ് ചെയ്ത് **Run** ക്ലിക്ക് ചെയ്യുക.
5. **Project Settings** ➜ **API**-ൽ പോയി `Project URL`-ഉം `anon / service_role API Key`-ഉം കോപ്പി ചെയ്യുക.
6. നിങ്ങളുടെ `.env` ഫയലിൽ പേസ്റ്റ് ചെയ്യുക:
```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-supabase-service-role-or-anon-key
```

---

### 🚀 3. Render.com-ൽ സൗജന്യമായി Host ചെയ്യാൻ (Render Cloud Hosting)

1. നിങ്ങളുടെ കോഡ് GitHub Repository-ലേക്ക് push ചെയ്യുക (Private അല്ലെങ്കിൽ Public).
2. [render.com](https://render.com)-ൽ ലോഗിൻ ചെയ്ത് **New +** ➜ **Web Service** ക്ലിക്ക് ചെയ്യുക.
3. നിങ്ങളുടെ GitHub Repo തിരഞ്ഞെടുക്കുക:
   - **Environment:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. **Environment Variables**-ൽ താഴെ പറയുന്നവ ചേർക്കുക:
   - `SUPABASE_URL` = (നിങ്ങളുടെ Supabase URL)
   - `SUPABASE_KEY` = (നിങ്ങളുടെ Supabase Key)
   - `WORKSHOP_NAME` = SPARK AUTO ELECTRICALS
   - `WORKSHOP_UPI_ID` = yourworkshop@okaxis
5. **Deploy Web Service** ക്ലിക്ക് ചെയ്യുക. ഏതാനും നിമിഷങ്ങൾക്കുള്ളിൽ നിങ്ങളുടെ വർക്ക്‌ഷോപ്പ് സോഫ്റ്റ്‌വെയർ ലൈവ് ആയി ലഭ്യമാകും!

---

### 🏷️ 4. Barcode Scanner ഉപയോഗിക്കുന്ന വിധം (USB / Bluetooth / Camera)
- ബില്ലിംഗ് അല്ലെങ്കിൽ ജോബ് കാർഡ് സ്ക്രീൻ തുറന്ന് ഇരിക്കുമ്പോൾ നിങ്ങളുടെ USB/Bluetooth Gun Scanner ഉപയോഗിച്ച് സ്പെയർ പാർട്സ് ബോക്സിലെ ബാർകോഡ് സ്കാൻ ചെയ്താൽ ഐറ്റം തനിയെ ബില്ലിലേക്ക് കയറും.
- ബാർകോഡ് സ്കാൻ ചെയ്യുമ്പോൾ സോഫ്റ്റ്‌വെയറിൽ നിന്ന് ഒരു pleasant 'beep' സൗണ്ട് കേൾക്കാം.
- ഇൻവെന്ററി ബോക്സുകളിൽ ഒട്ടിക്കാനുള്ള ബാർകോഡ് സ്റ്റിക്കറുകൾ പ്രിന്റ് ചെയ്യാൻ മെനുവിലെ **Barcode Generator** ക്ലിക്ക് ചെയ്ത് പ്രിന്റ് ചെയ്യുക.

---

### 📱 5. WhatsApp & UPI Payment Link പങ്കിടുന്ന വിധം
- ബിൽ ഉണ്ടാക്കിയ ശേഷം **WhatsApp** ഐക്കണിൽ ക്ലിക്ക് ചെയ്താൽ കസ്റ്റമർക്ക് ബിൽ വിവരങ്ങളും, **Direct PDF Download Link**-ഉം, **Instant UPI Payment Link (GPay/PhonePe)**-ഉം അടങ്ങിയ മെസ്സേജ് WhatsApp-ൽ തനിയെ ഫിൽ ആകും.
- കസ്റ്റമർ ആ ലിങ്കിൽ ടാപ്പ് ചെയ്യുമ്പോൾ അവരുടെ ഫോണിലെ GPay/PhonePe തുറന്ന് കൃത്യമായ ബിൽ തുക ഉടൻ ട്രാൻസ്ഫർ ചെയ്യാൻ കഴിയും.
- ബില്ലിൽ Dynamic UPI QR Code ഉള്ളതിനാൽ പ്രിന്റ് ചെയ്ത ബില്ലിൽ നിന്നും കസ്റ്റമർക്ക് സ്കാൻ ചെയ്യാം!

---

### 📊 6. CA Audit & GSTR-1 ടാക്സ് റിപ്പോർട്ടുകൾ
- മെനുവിലെ **CA Audit & GSTR-1** പേജ് തുറക്കുക.
- **Download GSTR-1 Excel for CA** ബട്ടൺ അമർത്തിയാൽ നിങ്ങളുടെ ചാർട്ടേഡ് അക്കൗണ്ടന്റിന് (CA) നേരിട്ട് സമർപ്പിക്കാനുള്ള Excel Spreadsheet (.xlsx) ഇൻസ്റ്റന്റ് ആയി ഡൗൺലോഡ് ആകും!
gPphSAJqoZZacv44
