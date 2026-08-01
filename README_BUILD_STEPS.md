# P2P Offline TikTok — Android App Build လမ်းညွှန်

ဒီ project ဟာ သင့် `new6_f22_1.py` (Flask server) ကို Android app တစ်ခုအထဲ
Chaquopy ကနေတစ်ဆင့် တိုက်ရိုက် run ထားပြီး WebView နဲ့ GUI ပြပေးတဲ့ project ပါ။
Browser ဖွင့်စရာ၊ link နှိပ်စရာ မလိုတော့ဘဲ App icon နှိပ်တာနဲ့ တန်းအလုပ်လုပ်ပါလိမ့်မယ်။

## လိုအပ်တာများ (PC ပေါ်မှာ)
1. **Android Studio** (နောက်ဆုံးဗားရှင်း) — https://developer.android.com/studio
2. **Internet connection** — ပထမဆုံးအကြိမ် Gradle sync/build မှာ Android SDK,
   Chaquopy Python interpreter, pip packages (flask, requests) တွေကို
   download လုပ်ရပါမယ်
3. Chaquopy က **အခမဲ့မဟုတ်ပါဘူး** — commercial app အနေနဲ့ ထုတ်ဝေမယ်ဆိုရင်
   license လိုအပ်နိုင်ပါတယ် (https://chaquo.com/chaquopy/ ကြည့်ပါ)။
   ကိုယ်ပိုင်သုံး/testing အတွက်ဆိုရင် free trial နဲ့ စတင်လို့ရပါတယ်။

## Build လုပ်နည်း
1. ဒီ `.zip` ကို extract လုပ်ပါ
2. Android Studio ဖွင့်ပြီး **Open** → extract လုပ်ထားတဲ့ `P2PTikTokApp` folder ကို ရွေးပါ
3. Gradle sync ကို စောင့်ပါ (ပထမဆုံးအကြိမ် download များတာကြောင့် အချိန်ယူနိုင်ပါတယ်)
4. ဖုန်းကို USB Debugging ဖွင့်ပြီး ချိတ်ဆက် (ဒါမှမဟုတ် Emulator သုံး)
5. **Run ▶** နှိပ်ပါ — App က ဖုန်းပေါ် install ဖြစ်သွားပါလိမ့်မယ်

APK file တစ်ခုတည်း ထုတ်ချင်ရင်: **Build → Build Bundle(s)/APK(s) → Build APK(s)**

## ဘာတွေ ပြင်ထားလဲ (မူရင်း script ကနေ)
- `psutil` ကို ဖယ်ပြီး `shutil.disk_usage` နဲ့ အစားထိုးထား (psutil က Android အတွက်
  build ရခက်တဲ့ C-extension ဖြစ်လို့)
- Database/uploads/thumbnails folder တွေကို app ရဲ့ private storage
  (`/data/data/com.p2p.offlinetiktok/files/p2p_data/`) ထဲကို ညွှန်းထား —
  ဒါကြောင့် app ကို uninstall မလုပ်သရွေ့ data မပျောက်ပါဘူး
  (Termux ထဲက `p2p_offline.db` ဖိုင်ဟောင်းကို ကူးထည့်ချင်ရင် ဒီ folder ထဲကို
  push လုပ်ပေးလို့ရပါတယ်)
- Script ကိုယ်တိုင် ပြန်ရေးတဲ့ "self-embed DB into script" logic ကို Android
  ပေါ်မှာ disable ထားတယ် — data က app storage ထဲမှာ တိုက်ရိုက် persist ဖြစ်နေပြီး
  ဖြစ်တာကြောင့် မလိုအပ်တော့ဘူး
- `main()` ဆိုတဲ့ function အသစ်ထည့်ထား — `MainActivity.kt` က ဒီ function ကို
  background thread ထဲမှာ ခေါ်ပြီး Flask server ကို စတင်ပါတယ်
- `MainActivity.kt` က server အသင့်ဖြစ်တဲ့အထိ (localhost:5000 ကို poll လုပ်ပြီး)
  စောင့်ပြီးမှ WebView ထဲကို load လုပ်ပေးတယ် — address bar လုံးဝ မပါတဲ့
  full-screen app GUI အနေနဲ့ ပေါ်ပါလိမ့်မယ်

## သတိထားရမည့်အချက်များ
- **LAN P2P sync feature** (peer discovery, UDP broadcast) ကတော့ ဖုန်းအချင်းချင်း
  တစ်ခုတည်းသော Wi-Fi/LAN ပေါ်ရှိမှသာ အလုပ်လုပ်ပါမယ် — ယခင် Termux mode အတိုင်းပါပဲ
- Video upload အတွက် `READ_MEDIA_VIDEO` / `CAMERA` permission တွေကို runtime မှာ
  တောင်းရန် လိုအပ်နိုင်ပါတယ် (Android 13+) — အခုထည့်ထားတာက manifest declaration
  ပါပဲ၊ runtime permission request logic ကို လိုအပ်ရင် ထပ်ထည့်ပေးနိုင်ပါတယ်
- `abiFilters` ကို `armeabi-v7a` / `arm64-v8a` ပဲ ထည့်ထားတယ် — emulator (x86_64)
  ပေါ်မှာ စမ်းချင်ရင် `app/build.gradle` ထဲက abiFilters list ထဲ `"x86_64"` ထပ်ထည့်ပါ
