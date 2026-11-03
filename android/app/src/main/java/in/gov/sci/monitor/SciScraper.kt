package in.gov.sci.monitor

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.*
import org.json.JSONObject
import org.jsoup.Jsoup
import java.io.IOException
import java.util.concurrent.TimeUnit
import java.util.regex.Pattern

object SciScraper {
    private const val BASE_URL = "https://www.sci.gov.in"
    private const val FORM_URL = "$BASE_URL/case-status-case-no/"
    private const val AJAX_URL = "$BASE_URL/wp-admin/admin-ajax.php"
    private const val CAPTCHA_URL_TEMPLATE = "$BASE_URL/?_siwp_captcha&id="
    private const val USER_AGENT = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Mobile Safari/537.36"

    private const val MAX_RETRIES = 6

    suspend fun checkCase(
        caseType: String,
        caseNo: String,
        year: String,
        onLog: (String) -> Unit
    ): List<Order> = withContext(Dispatchers.IO) {
        for (attempt in 1..MAX_RETRIES) {
            onLog("[attempt $attempt] Connecting to Supreme Court portal...")

            // Fresh cookie session per attempt
            val cookieJar = InMemoryCookieJar()
            val client = OkHttpClient.Builder()
                .cookieJar(cookieJar)
                .connectTimeout(25, TimeUnit.SECONDS)
                .readTimeout(25, TimeUnit.SECONDS)
                .writeTimeout(25, TimeUnit.SECONDS)
                .build()

            try {
                // 1. GET case-status page
                val getRequest = Request.Builder()
                    .url(FORM_URL)
                    .header("User-Agent", USER_AGENT)
                    .header("Accept-Language", "en-US,en;q=0.9")
                    .build()

                val html = client.newCall(getRequest).execute().use { response ->
                    if (!response.isSuccessful) throw IOException("Unexpected code $response")
                    response.body?.string() ?: ""
                }

                val doc = Jsoup.parse(html)
                val formFields = mutableMapOf<String, String>()
                for (input in doc.select("input[type=hidden]")) {
                    val name = input.attr("name")
                    val value = input.attr("value")
                    if (name.isNotBlank()) {
                        formFields[name] = value
                    }
                }

                var captchaScid = ""
                val captchaMatcher = Pattern.compile("""\?_siwp_captcha(?:&amp;|&)id=([a-f0-9]+)""").matcher(html)
                if (captchaMatcher.find()) {
                    captchaScid = captchaMatcher.group(1) ?: ""
                }

                if (captchaScid.isBlank()) {
                    onLog("⚠️ Could not locate CAPTCHA ID. Retrying...")
                    continue
                }

                // 2. Download CAPTCHA image
                val capUrl = CAPTCHA_URL_TEMPLATE + captchaScid
                val capRequest = Request.Builder()
                    .url(capUrl)
                    .header("User-Agent", USER_AGENT)
                    .header("Referer", FORM_URL)
                    .build()

                val capBytes = client.newCall(capRequest).execute().use { response ->
                    if (!response.isSuccessful) throw IOException("Failed to download captcha $response")
                    response.body?.bytes() ?: byteArrayOf()
                }

                // 3. Solve CAPTCHA via on-device ML Kit
                val solution = CaptchaSolver.solve(capBytes)
                if (solution.isBlank()) {
                    onLog("⚠️ OCR could not solve CAPTCHA on attempt $attempt. Retrying...")
                    continue
                }
                onLog("OCR solved: '$solution'")

                // 4. POST search form
                val formBodyBuilder = FormBody.Builder()
                for ((k, v) in formFields) {
                    if (!k.startsWith("_captcha_")) {
                        formBodyBuilder.add(k, v)
                    }
                }
                formBodyBuilder.add("case_type", caseType)
                formBodyBuilder.add("case_no", caseNo)
                formBodyBuilder.add("year", year)
                formBodyBuilder.add("siwp_captcha_value", solution)
                formBodyBuilder.add("es_ajax_request", "1")
                formBodyBuilder.add("action", "get_case_status_case_no")

                val postRequest = Request.Builder()
                    .url(AJAX_URL)
                    .post(formBodyBuilder.build())
                    .header("User-Agent", USER_AGENT)
                    .header("Referer", FORM_URL)
                    .header("X-Requested-With", "XMLHttpRequest")
                    .build()

                val postResponseText = client.newCall(postRequest).execute().use { response ->
                    if (!response.isSuccessful) throw IOException("POST failed $response")
                    response.body?.string() ?: ""
                }

                // 5. Check if rejected
                if (isCaptchaRejected(postResponseText)) {
                    onLog("⚠️ CAPTCHA rejected on attempt $attempt. Retrying...")
                    continue
                }

                // 6. Parse search results
                val orders = parseSearchResults(client, postResponseText, onLog)
                onLog("✓ Search accepted. Found ${orders.size} order(s).")
                return@withContext orders

            } catch (e: Exception) {
                onLog("⚠️ Network/parsing error: ${e.message}")
            }
        }

        onLog("❌ Failed to retrieve case details after $MAX_RETRIES attempts.")
        emptyList()
    }

    private fun isCaptchaRejected(text: String): Boolean {
        try {
            val json = JSONObject(text)
            if (json.optBoolean("success", true)) {
                return false
            }
            val dataStr = json.optString("data", "")
            if (dataStr.contains("captcha", ignoreCase = true)) return true
            return true
        } catch (e: Exception) {
            // Not json, check plain string
        }
        val lower = text.lowercase()
        return lower.contains("incorrect captcha") ||
                lower.contains("invalid captcha") ||
                lower.contains("captcha mismatch") ||
                lower.contains("wrong captcha")
    }

    private fun parseSearchResults(
        client: OkHttpClient,
        responseText: String,
        onLog: (String) -> Unit
    ): List<Order> {
        var resultsHtml = ""
        try {
            val json = JSONObject(responseText)
            val dataObj = json.optJSONObject("data")
            if (dataObj != null) {
                resultsHtml = dataObj.optString("resultsHtml", "")
            }
            if (resultsHtml.isBlank()) {
                resultsHtml = json.optString("data", "")
            }
        } catch (e: Exception) {
            resultsHtml = responseText
        }

        val doc = Jsoup.parse(resultsHtml)
        var diaryNo = ""
        var diaryYear = ""

        val tr = doc.selectFirst("tr[data-diary-no]")
        if (tr != null) {
            diaryNo = tr.attr("data-diary-no")
            diaryYear = tr.attr("data-diary-year")
        }

        if (diaryNo.isBlank()) {
            val m = Pattern.compile("""data-diary-no=["'](\d+)["']\s+data-diary-year=["'](\d+)["']""")
                .matcher(resultsHtml)
            if (m.find()) {
                diaryNo = m.group(1) ?: ""
                diaryYear = m.group(2) ?: ""
            }
        }

        if (diaryNo.isBlank()) {
            return emptyList()
        }

        return fetchCaseOrders(client, diaryNo, diaryYear, onLog)
    }

    private fun fetchCaseOrders(
        client: OkHttpClient,
        diaryNo: String,
        diaryYear: String,
        onLog: (String) -> Unit
    ): List<Order> {
        val orders = mutableListOf<Order>()

        // 1. Initial request to prime session
        try {
            val primeUrl = HttpUrl.parse(AJAX_URL)!!.newBuilder()
                .addQueryParameter("action", "get_case_details")
                .addQueryParameter("diary_no", diaryNo)
                .addQueryParameter("diary_year", diaryYear)
                .addQueryParameter("tab_name", "")
                .addQueryParameter("es_ajax_request", "1")
                .build()

            val primeReq = Request.Builder()
                .url(primeUrl)
                .header("User-Agent", USER_AGENT)
                .header("Referer", FORM_URL)
                .header("X-Requested-With", "XMLHttpRequest")
                .build()

            client.newCall(primeReq).execute().close()
        } catch (e: Exception) {
            // ignore
        }

        // 2. Fetch judgement_orders tab
        try {
            val ordersUrl = HttpUrl.parse(AJAX_URL)!!.newBuilder()
                .addQueryParameter("action", "get_case_details")
                .addQueryParameter("diary_no", diaryNo)
                .addQueryParameter("diary_year", diaryYear)
                .addQueryParameter("tab_name", "judgement_orders")
                .addQueryParameter("es_ajax_request", "1")
                .build()

            val ordersReq = Request.Builder()
                .url(ordersUrl)
                .header("User-Agent", USER_AGENT)
                .header("Referer", FORM_URL)
                .header("X-Requested-With", "XMLHttpRequest")
                .build()

            val ordersHtml = client.newCall(ordersReq).execute().use { it.body?.string() ?: "" }
            val doc = Jsoup.parse(ordersHtml)

            for (a in doc.select("a[href]")) {
                val href = a.attr("href").trim()
                if (href.lowercase().contains(".pdf")) {
                    val fullUrl = if (href.startsWith("http")) href else BASE_URL + href
                    val text = a.text().trim()
                    val parentText = a.parent()?.text()?.trim() ?: ""

                    // Extract date e.g. 05-01-2024
                    var date = ""
                    val dateMatcher = Pattern.compile("""\b(\d{2}[-/]\d{2}[-/]\d{4})\b""").matcher(parentText)
                    if (dateMatcher.find()) {
                        date = dateMatcher.group(1) ?: ""
                    }

                    val label = when {
                        parentText.isNotBlank() -> parentText
                        text.isNotBlank() -> text
                        else -> "Order dated ${if (date.isNotBlank()) date else "Unknown"}"
                    }

                    orders.add(Order(date = date, url = fullUrl, label = label))
                }
            }
        } catch (e: Exception) {
            onLog("⚠️ Error fetching order details: ${e.message}")
        }

        return orders
    }

    private class InMemoryCookieJar : CookieJar {
        private val cookieStore = mutableListOf<Cookie>()

        override fun saveFromResponse(url: HttpUrl, cookies: List<Cookie>) {
            cookieStore.addAll(cookies)
        }

        override fun loadForRequest(url: HttpUrl): List<Cookie> {
            val valid = mutableListOf<Cookie>()
            for (c in cookieStore) {
                if (c.matches(url)) {
                    valid.add(c)
                }
            }
            return valid
        }
    }
}
