package in.gov.sci.monitor

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.PowerManager
import android.provider.Settings
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {

    private lateinit var prefsManager: PreferencesManager

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        prefsManager = PreferencesManager(this)
        NotificationHelper.createChannels(this)

        setContent {
            MaterialTheme(
                colorScheme = lightColorScheme(
                    primary = Color(0xFF1A237E),
                    secondary = Color(0xFF0D47A1),
                    background = Color(0xFFF5F5F5)
                )
            ) {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background
                ) {
                    MainScreen(prefsManager = prefsManager)
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MainScreen(prefsManager: PreferencesManager) {
    val context = LocalContext.current
    val coroutineScope = rememberCoroutineScope()

    val isRunning by MonitorService.isRunningFlow.collectAsState()
    val countdown by MonitorService.countdownFlow.collectAsState()

    var cases by remember { mutableStateOf(prefsManager.loadCases()) }
    val logs = remember { mutableStateListOf<String>() }

    val listState = rememberLazyListState()

    // Collect service logs
    LaunchedEffect(Unit) {
        MonitorService.logsFlow.collect { log ->
            logs.add(log)
            if (logs.size > 100) logs.removeAt(0)
            coroutineScope.launch {
                if (logs.isNotEmpty()) listState.animateScrollToItem(logs.size - 1)
            }
        }
    }

    // Collect case updates
    LaunchedEffect(Unit) {
        MonitorService.caseUpdatesFlow.collect { updatedCase ->
            cases = cases.map { if (it.id == updatedCase.id) updatedCase else it }
        }
    }

    // Notification permission launcher for Android 13+
    val notificationPermissionLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestPermission()
    ) { isGranted ->
        if (!isGranted) {
            Toast.makeText(context, "Notification permission is required for order alerts", Toast.LENGTH_LONG).show()
        }
    }

    fun requestPermissionsAndStart() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
                notificationPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
            }
        }

        // Start service
        val intent = Intent(context, MonitorService::class.java).apply {
            action = MonitorService.ACTION_START
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            context.startForegroundService(intent)
        } else {
            context.startService(intent)
        }
    }

    fun stopMonitoringService() {
        val intent = Intent(context, MonitorService::class.java).apply {
            action = MonitorService.ACTION_STOP
        }
        context.startService(intent)
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("🏛️ SCI Case Monitor", fontWeight = FontWeight.Bold, color = Color.White)
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = Color(0xFF1A237E)
                )
            )
        }
    ) { paddingValues ->
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            // ── TOP CONTROL CARD ───────────────────────────────────────────────
            item {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(12.dp),
                    colors = CardDefaults.cardColors(containerColor = Color.White),
                    elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
                ) {
                    Column(modifier = Modifier.padding(16.dp)) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Column {
                                Text(
                                    text = if (isRunning) "● MONITORING ACTIVE" else "○ MONITORING IDLE",
                                    fontWeight = FontWeight.Bold,
                                    color = if (isRunning) Color(0xFF2E7D32) else Color(0xFF757575)
                                )
                                Text(
                                    text = if (isRunning) "Next check in: ${countdown}s (120s interval)" else "Interval: 120s per cycle",
                                    fontSize = 12.sp,
                                    color = Color.Gray
                                )
                            }

                            Button(
                                onClick = {
                                    if (isRunning) stopMonitoringService() else requestPermissionsAndStart()
                                },
                                colors = ButtonDefaults.buttonColors(
                                    containerColor = if (isRunning) Color(0xFFC62828) else Color(0xFF2E7D32)
                                )
                            ) {
                                Icon(
                                    imageVector = if (isRunning) Icons.Default.Stop else Icons.Default.PlayArrow,
                                    contentDescription = null
                                )
                                Spacer(modifier = Modifier.width(6.dp))
                                Text(if (isRunning) "Stop" else "Start")
                            }
                        }

                        // Battery optimization note
                        Spacer(modifier = Modifier.height(10.dp))
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Text(
                                "⚡ For 24/7 background alerts, disable battery optimization:",
                                fontSize = 11.sp,
                                color = Color.DarkGray,
                                modifier = Modifier.weight(1f)
                            )
                            TextButton(onClick = {
                                val pm = context.getSystemService(Context.POWER_SERVICE) as PowerManager
                                if (!pm.isIgnoringBatteryOptimizations(context.packageName)) {
                                    val intent = Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS).apply {
                                        data = Uri.parse("package:${context.packageName}")
                                    }
                                    context.startActivity(intent)
                                } else {
                                    Toast.makeText(context, "Battery optimization is already disabled!", Toast.LENGTH_SHORT).show()
                                }
                            }) {
                                Text("Disable", fontSize = 11.sp)
                            }
                        }
                    }
                }
            }

            // ── 3 CASE MANAGEMENT CARDS ─────────────────────────────────────────
            items(cases) { caseItem ->
                CaseCard(
                    caseItem = caseItem,
                    onSave = { updated ->
                        cases = cases.map { if (it.id == updated.id) updated else it }
                        prefsManager.saveCases(cases)
                    }
                )
            }

            // ── LIVE ACTIVITY LOGS CARD ─────────────────────────────────────────
            item {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(12.dp),
                    colors = CardDefaults.cardColors(containerColor = Color(0xFF1E1E1E)),
                    elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
                ) {
                    Column(modifier = Modifier.padding(14.dp)) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text(
                                "📋 Live Activity Log",
                                color = Color.White,
                                fontWeight = FontWeight.Bold,
                                fontSize = 14.sp
                            )
                            TextButton(onClick = { logs.clear() }) {
                                Text("Clear", color = Color.LightGray, fontSize = 12.sp)
                            }
                        }

                        Box(
                            modifier = Modifier
                                .fillMaxWidth()
                                .height(220.dp)
                                .background(Color(0xFF121212), RoundedCornerShape(8.dp))
                                .padding(8.dp)
                        ) {
                            if (logs.isEmpty()) {
                                Text(
                                    "No logs yet. Tap 'Start' above to begin monitoring.",
                                    color = Color.Gray,
                                    fontSize = 12.sp,
                                    fontFamily = FontFamily.Monospace
                                )
                            } else {
                                LazyColumn(
                                    state = listState,
                                    modifier = Modifier.fillMaxSize()
                                ) {
                                    items(logs) { line ->
                                        Text(
                                            text = line,
                                            color = when {
                                                line.contains("🚨") -> Color(0xFFFF5252)
                                                line.contains("✓") -> Color(0xFF81C784)
                                                line.contains("⚠️") -> Color(0xFFFFD54F)
                                                else -> Color(0xFFE0E0E0)
                                            },
                                            fontSize = 11.sp,
                                            fontFamily = FontFamily.Monospace
                                        )
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CaseCard(
    caseItem: CaseItem,
    onSave: (CaseItem) -> Unit
) {
    var expanded by remember { mutableStateOf(false) }
    var caseType by remember { mutableStateOf(caseItem.caseType) }
    var caseNo by remember { mutableStateOf(caseItem.caseNo) }
    var year by remember { mutableStateOf(caseItem.year) }

    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = Color.White),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            // Header Row
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "Case Slot ${caseItem.id}",
                    fontWeight = FontWeight.Bold,
                    fontSize = 16.sp,
                    color = Color(0xFF1A237E)
                )

                Surface(
                    shape = RoundedCornerShape(16.dp),
                    color = Color(caseItem.statusColor).copy(alpha = 0.15f)
                ) {
                    Text(
                        text = caseItem.status,
                        color = Color(caseItem.statusColor),
                        fontSize = 11.sp,
                        fontWeight = FontWeight.SemiBold,
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                    )
                }
            }

            Spacer(modifier = Modifier.height(10.dp))

            // Case Type Dropdown
            ExposedDropdownMenuBox(
                expanded = expanded,
                onExpandedChange = { expanded = !expanded }
            ) {
                val selectedLabel = CASE_TYPES[caseType] ?: "Select Case Type..."
                OutlinedTextField(
                    value = selectedLabel,
                    onValueChange = {},
                    readOnly = true,
                    label = { Text("Case Type") },
                    trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = expanded) },
                    modifier = Modifier
                        .fillMaxWidth()
                        .menuAnchor()
                )
                ExposedDropdownMenu(
                    expanded = expanded,
                    onDismissRequest = { expanded = false }
                ) {
                    CASE_TYPES.forEach { (code, label) ->
                        val fullName = CASE_TYPE_NAMES[code] ?: label
                        DropdownMenuItem(
                            text = { Text("$label - $fullName") },
                            onClick = {
                                caseType = code
                                expanded = false
                                caseItem.caseType = code
                                onSave(caseItem)
                            }
                        )
                    }
                }
            }

            Spacer(modifier = Modifier.height(8.dp))

            // Case Number & Year Row
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                OutlinedTextField(
                    value = caseNo,
                    onValueChange = {
                        caseNo = it
                        caseItem.caseNo = it
                        onSave(caseItem)
                    },
                    label = { Text("Case No.") },
                    placeholder = { Text("e.g. 21774") },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    modifier = Modifier.weight(1f)
                )

                OutlinedTextField(
                    value = year,
                    onValueChange = {
                        year = it
                        caseItem.year = it
                        onSave(caseItem)
                    },
                    label = { Text("Year") },
                    placeholder = { Text("2025") },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    modifier = Modifier.weight(1f)
                )
            }

            // Case stats
            if (caseItem.isValid()) {
                Spacer(modifier = Modifier.height(8.dp))
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Text(
                        text = "Orders recorded: ${caseItem.ordersCount}",
                        fontSize = 11.sp,
                        color = Color.DarkGray
                    )
                    Text(
                        text = "Last checked: ${caseItem.lastChecked}",
                        fontSize = 11.sp,
                        color = Color.DarkGray
                    )
                }
            }
        }
    }
}
