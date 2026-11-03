package gov.sci.monitor

import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.IBinder
import android.os.PowerManager
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import java.text.SimpleDateFormat
import java.util.*

class MonitorService : Service() {

    companion object {
        const val ACTION_START = "gov.sci.monitor.ACTION_START"
        const val ACTION_STOP = "gov.sci.monitor.ACTION_STOP"
        const val CHECK_INTERVAL_MS = 120_000L // 120 seconds

        val isRunningFlow = MutableStateFlow(false)
        val logsFlow = MutableSharedFlow<String>(replay = 50)
        val caseUpdatesFlow = MutableSharedFlow<CaseItem>(replay = 10)
        val countdownFlow = MutableStateFlow(120)

        fun log(message: String) {
            val time = SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(Date())
            val formatted = "[$time] $message"
            logsFlow.tryEmit(formatted)
        }
    }

    private val serviceScope = CoroutineScope(Dispatchers.Default + SupervisorJob())
    private var monitorJob: Job? = null
    private var wakeLock: PowerManager.WakeLock? = null
    private lateinit var prefsManager: PreferencesManager

    override fun onCreate() {
        super.onCreate()
        prefsManager = PreferencesManager(this)
        NotificationHelper.createChannels(this)

        val powerManager = getSystemService(Context.POWER_SERVICE) as PowerManager
        wakeLock = powerManager.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "SCICaseMonitor::WakeLock")
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> stopMonitoring()
            ACTION_START, null -> startMonitoring()
        }
        return START_STICKY
    }

    private fun startMonitoring() {
        if (monitorJob?.isActive == true) return

        val initialNotif = NotificationHelper.buildForegroundNotification(
            this,
            "Monitoring active (every 120s)..."
        )
        startForeground(NotificationHelper.SERVICE_NOTIFICATION_ID, initialNotif)

        isRunningFlow.value = true
        prefsManager.setMonitoring(true)
        log("Monitoring started. Cycle interval: 120 seconds.")

        monitorJob = serviceScope.launch {
            var cycleCount = 0
            while (isActive) {
                cycleCount++
                log("--- Cycle #$cycleCount Starting ---")

                try {
                    wakeLock?.acquire(60_000L) // Hold wake lock for up to 60s during network work
                    performCheckCycle()
                } catch (e: Exception) {
                    log("⚠️ Error in check cycle: ${e.message}")
                } finally {
                    try {
                        if (wakeLock?.isHeld == true) wakeLock?.release()
                    } catch (e: Exception) {
                        // ignore
                    }
                }

                log("Cycle #$cycleCount complete. Next check in 120s.")

                // 120-second countdown
                for (remaining in 120 downTo 1) {
                    countdownFlow.value = remaining
                    delay(1000L)
                    if (!isActive) break
                }
            }
        }
    }

    private suspend fun performCheckCycle() {
        val cases = prefsManager.loadCases()
        val seenOrdersMap = prefsManager.loadSeenOrders()

        for (case in cases) {
            if (!case.isValid()) continue

            val caseLabel = case.getDisplayName()
            val caseKey = case.makeKey()

            case.status = "Checking..."
            case.statusColor = 0xFFF57F17 // Yellow
            caseUpdatesFlow.emit(case)

            log("Checking $caseLabel...")

            val scrapedOrders = SciScraper.checkCase(
                caseType = case.caseType,
                caseNo = case.caseNo,
                year = case.year,
                onLog = { msg -> log("  $msg") }
            )

            val timeStr = SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(Date())
            case.lastChecked = timeStr

            val existingUids = seenOrdersMap[caseKey]

            if (existingUids == null) {
                // First run for this case: establish baseline silently
                val newSet = scrapedOrders.map { it.uid() }.toMutableSet()
                seenOrdersMap[caseKey] = newSet
                prefsManager.saveSeenOrders(seenOrdersMap)

                case.ordersCount = scrapedOrders.size
                case.status = "Active (Baseline established: ${scrapedOrders.size} orders)"
                case.statusColor = 0xFF2E7D32 // Green
                caseUpdatesFlow.emit(case)

                log("✓ Baselined $caseLabel: ${scrapedOrders.size} order(s) recorded.")
            } else {
                // Subsequent run: delta-check for new orders
                var newOrdersFound = 0
                for (order in scrapedOrders) {
                    val uid = order.uid()
                    if (!existingUids.contains(uid)) {
                        newOrdersFound++
                        existingUids.add(uid)
                        log("🚨 NEW ORDER DETECTED for $caseLabel: ${order.label}")
                        NotificationHelper.sendOrderAlert(this@MonitorService, caseLabel, order)
                    }
                }

                if (newOrdersFound > 0) {
                    prefsManager.saveSeenOrders(seenOrdersMap)
                    case.ordersCount = existingUids.size
                    case.status = "🚨 $newOrdersFound NEW ORDER(S)!"
                    case.statusColor = 0xFFC62828 // Red alert
                } else {
                    case.ordersCount = existingUids.size
                    case.status = "✓ No new orders (Total: ${existingUids.size})"
                    case.statusColor = 0xFF2E7D32 // Green
                }
                caseUpdatesFlow.emit(case)
            }
        }
    }

    private fun stopMonitoring() {
        monitorJob?.cancel()
        monitorJob = null
        isRunningFlow.value = false
        prefsManager.setMonitoring(false)
        countdownFlow.value = 0
        log("Monitoring stopped by user.")
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    override fun onDestroy() {
        stopMonitoring()
        try {
            if (wakeLock?.isHeld == true) wakeLock?.release()
        } catch (e: Exception) {
            // ignore
        }
        serviceScope.cancel()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null
}
