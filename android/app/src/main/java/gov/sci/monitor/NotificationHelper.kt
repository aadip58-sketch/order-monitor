package gov.sci.monitor

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import androidx.core.app.NotificationCompat
import gov.sci.monitor.R

object NotificationHelper {
    const val SERVICE_CHANNEL_ID = "sci_monitor_service_channel"
    const val ALERT_CHANNEL_ID = "sci_monitor_alert_channel"
    const val SERVICE_NOTIFICATION_ID = 1001

    fun createChannels(context: Context) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val manager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

            // 1. Service channel (persistent notification while running)
            val serviceChannel = NotificationChannel(
                SERVICE_CHANNEL_ID,
                "Case Monitor Service",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Shows that SCI Case Monitor is actively running in background"
                setShowBadge(false)
            }
            manager.createNotificationChannel(serviceChannel)

            // 2. Alert channel (heads-up notification when new order PDF is uploaded)
            val alertChannel = NotificationChannel(
                ALERT_CHANNEL_ID,
                "New Order Alerts",
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "Notifies when a new order PDF is published by Supreme Court of India"
                enableVibration(true)
                vibrationPattern = longArrayOf(0, 400, 200, 400)
                setShowBadge(true)
                lockscreenVisibility = Notification.VISIBILITY_PUBLIC
            }
            manager.createNotificationChannel(alertChannel)
        }
    }

    fun buildForegroundNotification(context: Context, statusText: String): Notification {
        val launchIntent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_SINGLE_TOP
        }
        val pendingIntent = PendingIntent.getActivity(
            context,
            0,
            launchIntent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )

        return NotificationCompat.Builder(context, SERVICE_CHANNEL_ID)
            .setContentTitle("🏛️ SCI Case Monitor")
            .setContentText(statusText)
            .setSmallIcon(R.drawable.ic_notification)
            .setOngoing(true)
            .setContentIntent(pendingIntent)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build()
    }

    fun sendOrderAlert(context: Context, caseLabel: String, order: Order) {
        val manager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

        // Intent to open the PDF URL directly when notification is clicked
        val viewIntent = Intent(Intent.ACTION_VIEW, Uri.parse(order.url)).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK
        }
        val pendingIntent = PendingIntent.getActivity(
            context,
            System.currentTimeMillis().toInt(),
            viewIntent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )

        val notification = NotificationCompat.Builder(context, ALERT_CHANNEL_ID)
            .setContentTitle("🚨 New Supreme Court Order!")
            .setContentText("$caseLabel: ${order.label}")
            .setStyle(
                NotificationCompat.BigTextStyle()
                    .bigText("$caseLabel\n\nDate: ${order.date}\n${order.label}\n\nTap to open PDF document directly.")
            )
            .setSmallIcon(R.drawable.ic_notification)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .setContentIntent(pendingIntent)
            .addAction(android.R.drawable.ic_menu_view, "Open Order PDF", pendingIntent)
            .build()

        manager.notify(System.currentTimeMillis().toInt(), notification)
    }
}
