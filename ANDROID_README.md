# 📱 Supreme Court of India Case Monitor — Android Edition

Convert your Supreme Court case monitoring system into a standalone mobile application that runs continuously on your Android phone, solves CAPTCHAs on-device, and triggers native Android push notifications whenever a new order PDF is uploaded.

---

## 🌟 Choose Your Method

You have two convenient ways to run this on your Android device:

| Feature | Method 1: Native APK (Kotlin / Jetpack Compose) | Method 2: Termux Mobile App (Zero-Compile) |
|---|---|---|
| **Interface** | Native Android Material 3 GUI with Cards & Dropdowns | Rich Mobile Terminal Dashboard |
| **Setup Time** | 2 minutes (via GitHub Actions or Android Studio) | 1 minute (directly on phone) |
| **Background Execution** | Android Foreground Service + WakeLock | Termux Background Service + WakeLock |
| **OCR / CAPTCHA** | Google ML Kit On-Device Text Recognition (Offline) | ddddocr ONNX Neural Network |
| **Notifications** | High-Priority Android Heads-up Alerts with PDF Tap Action | Native Android Notification Shade via Termux:API |
| **Phone Screen Off** | Yes, runs 24/7 | Yes, runs 24/7 |

---

## 🚀 Method 1: Native Android App (.APK)

The complete native Android project is located in the [`android/`](./android) folder.

### Key Architecture:
- **UI:** Jetpack Compose + Material 3 ([`MainActivity.kt`](./android/app/src/main/java/in/gov/sci/monitor/MainActivity.kt)).
- **Background Engine:** Android Foreground Service ([`MonitorService.kt`](./android/app/src/main/java/in/gov/sci/monitor/MonitorService.kt)) running a 120-second coroutine loop with a partial `WakeLock`.
- **Scraper & API:** OkHttp + Jsoup ([`SciScraper.kt`](./android/app/src/main/java/in/gov/sci/monitor/SciScraper.kt)) executing the two-step Supreme Court API lookup (`get_case_status_case_no` -> `get_case_details?tab_name=judgement_orders`).
- **CAPTCHA OCR:** Google ML Kit on-device Text Recognition ([`CaptchaSolver.kt`](./android/app/src/main/java/in/gov/sci/monitor/CaptchaSolver.kt)) solving arithmetic equations (`10 + 2`, `7 - 5`, etc.) with zero external dependencies.
- **Alerts:** Android `NotificationManager` ([`NotificationHelper.kt`](./android/app/src/main/java/in/gov/sci/monitor/NotificationHelper.kt)) posting heads-up alerts with an action to immediately open the order PDF in your browser or PDF viewer.

### How to Build & Install the APK:

#### Option A: 1-Click Cloud Build (No Android Studio required)
We have included a GitHub Actions workflow in [`.github/workflows/build-apk.yml`](./.github/workflows/build-apk.yml).
1. Push this repository to your GitHub account (public or private).
2. Go to the **Actions** tab on GitHub -> click **Build Android APK** -> **Run workflow**.
3. In under 2 minutes, download the generated **`SCICaseMonitor-Debug-APK`** artifact directly to your phone and install it!

#### Option B: Open in Android Studio
1. Open **Android Studio**.
2. Select **Open** and choose the `android/` directory inside this project.
3. Click **Build** > **Build Bundle(s) / APK(s)** > **Build APK(s)**.
4. Transfer the resulting `.apk` to your phone and tap to install.

---

## ⚡ Method 2: Instant Mobile App via Termux (Zero Compilation)

If you want the monitor running on your phone **right now** without compiling an APK:

1. Install **Termux** and **Termux:API** on your phone (download free from [F-Droid](https://f-droid.org/packages/com.termux/)).
2. Open Termux and copy this project folder or run:
   ```bash
   git clone <your-repo-or-transfer-folder>
   cd sci-monitor
   bash android_termux_setup.sh
   ```
3. Run the monitor:
   ```bash
   python sci_monitor_cli.py
   ```
4. **Result:** The monitor will run in the background (even when your screen is locked) and will send real Android system notifications with sound and vibration whenever a new order is detected!
