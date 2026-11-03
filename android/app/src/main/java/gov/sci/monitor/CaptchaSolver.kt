package gov.sci.monitor

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.latin.TextRecognizerOptions
import kotlinx.coroutines.tasks.await

object CaptchaSolver {
    private val recognizer = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)

    suspend fun solve(imageBytes: ByteArray): String {
        if (imageBytes.isEmpty()) return ""
        val bitmap = BitmapFactory.decodeByteArray(imageBytes, 0, imageBytes.size) ?: return ""
        return solveBitmap(bitmap)
    }

    suspend fun solveBitmap(bitmap: Bitmap): String {
        return try {
            val inputImage = InputImage.fromBitmap(bitmap, 0)
            val visionText = recognizer.process(inputImage).await()
            val raw = visionText.text
            evaluateExpression(raw) ?: ""
        } catch (e: Exception) {
            ""
        }
    }

    fun cleanText(raw: String): String {
        var s = raw.trim()
        s = s.replace(Regex("[oOD]"), "0")
        s = s.replace(Regex("[lI|i]"), "1")
        s = s.replace(Regex("[zZ]"), "2")
        s = s.replace(Regex("[sS]"), "5")
        s = s.replace(Regex("[bB]"), "6")
        s = s.replace(Regex("[>]"), "7")
        s = s.replace(Regex("[,_—–~.]"), "-")
        s = s.replace(Regex("[tTxX×*]"), "+")
        s = s.replace(Regex("[=?].*$"), "").trim()
        return s
    }

    fun evaluateExpression(rawText: String): String? {
        val s = cleanText(rawText)
        val regex = Regex("""(\d+)\s*([+\-])\s*(\d+)""")
        val match = regex.find(s)
        if (match != null) {
            val n1 = match.groupValues[1].toIntOrNull() ?: return null
            val op = match.groupValues[2]
            val n2 = match.groupValues[3].toIntOrNull() ?: return null
            val ans = if (op == "+") n1 + n2 else n1 - n2
            return ans.toString()
        }

        // Secondary fallback if operator was missed or stuck
        val cleaned = s.replace(Regex("""[^\d+\-]"""), "")
        if (cleaned.contains("+") || cleaned.contains("-")) {
            val parts = cleaned.split(Regex("(?<=[+-])|(?=[+-])"))
            if (parts.size >= 3) {
                val n1 = parts[0].toIntOrNull()
                val op = parts[1]
                val n2 = parts[2].toIntOrNull()
                if (n1 != null && n2 != null) {
                    return if (op == "+") (n1 + n2).toString() else (n1 - n2).toString()
                }
            }
        }
        return null
    }
}
