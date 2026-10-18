# EV Smart Diagnostic

Այս նախագիծը ներառում է հայկական/անգլերեն ցուցադրական վեբ UI և FastAPI backend։ Թարմացված տարբերակում ավելացված է Linux SocketCAN/PCAN կապի շերտ և միայն ընդհանուր, read-only SAE J1979 OBD-II հարցումներ։

## Իրական հնարավորություններ

- VIN-ի 17 նիշանոց ձևաչափի ստուգում։ Հյուսիսամերիկյան check digit-ը ցուցադրվում է առանձին և չի օգտագործվում այլ շուկաների VIN-ը մերժելու համար։
- Ընդհանուր OBD-II-ի VIN (Mode 09), ECU պատասխանող մոդուլներ, stored/pending DTC (Modes 03/07), որոշ live PID-ներ և Mode 02 freeze-frame հարցում։ Մեքենայի աջակցությունը դեռ չի հաստատվել։
- Դեմո ռեժիմի բոլոր թվերը նշվում են որպես սիմուլյացիա։ `vcan*`-ով սիմուլացված կապը չի կարող միանալ ֆիզիկական CAN միջերեսին։
- Բարձր լարման BMS տվյալները, բջիջների լարումները/ջերմաստիճանները, SOH-ը, լիցքավորիչը և արտադրողի հատուկ DTC-ները հասանելի չեն առանց լիազորված Deepal տվյալների։

**2025 Deepal S06 PHEV-ի հետ իրական կապը ստուգված չէ։** Ծրագրային թեստերն անցել են միայն սիմուլացված CAN շրջանակներով, ոչ մեքենայի կամ VCI սարքի վրա։

## Արագ գործարկում

```bash
cd backend
uv venv --python 3.12
source .venv/bin/activate
uv pip install -r requirements.txt
export JWT_SECRET="$(openssl rand -hex 32)"
export BOOTSTRAP_ADMIN_TOKEN="$(openssl rand -hex 32)"
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

UI՝ `http://127.0.0.1:8000/`, API փաստաթուղթ՝ `/docs`։ Առաջին admin-ը ստեղծեք մեկ անգամ `POST /auth/bootstrap`-ով՝ `X-Bootstrap-Token` վերնագրով։ Սովորական գրանցումը ստեղծում է միայն viewer օգտատեր։

Մանրամասն PCAN, Docker, vcan սիմուլյատորի և Deepal փորձարկման քայլերը՝ [README.md](README.md)։
