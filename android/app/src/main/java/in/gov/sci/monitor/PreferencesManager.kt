package in.gov.sci.monitor

import android.content.Context
import android.content.SharedPreferences
import org.json.JSONArray
import org.json.JSONObject

class PreferencesManager(context: Context) {
    private val prefs: SharedPreferences =
        context.getSharedPreferences("sci_monitor_prefs", Context.MODE_PRIVATE)

    fun saveCases(cases: List<CaseItem>) {
        val array = JSONArray()
        for (c in cases) {
            val obj = JSONObject()
            obj.put("id", c.id)
            obj.put("caseType", c.caseType)
            obj.put("caseNo", c.caseNo)
            obj.put("year", c.year)
            array.put(obj)
        }
        prefs.edit().putString("cases_json", array.toString()).apply()
    }

    fun loadCases(): List<CaseItem> {
        val raw = prefs.getString("cases_json", null)
        if (raw.isNullOrBlank()) {
            return listOf(
                CaseItem(id = 1),
                CaseItem(id = 2),
                CaseItem(id = 3)
            )
        }

        val result = mutableListOf<CaseItem>()
        try {
            val array = JSONArray(raw)
            for (i in 0 until array.length()) {
                val obj = array.getJSONObject(i)
                result.add(
                    CaseItem(
                        id = obj.optInt("id", i + 1),
                        caseType = obj.optString("caseType", ""),
                        caseNo = obj.optString("caseNo", ""),
                        year = obj.optString("year", "")
                    )
                )
            }
        } catch (e: Exception) {
            result.clear()
            result.addAll(listOf(CaseItem(1), CaseItem(2), CaseItem(3)))
        }

        while (result.size < 3) {
            result.add(CaseItem(id = result.size + 1))
        }
        return result.take(3)
    }

    fun loadSeenOrders(): MutableMap<String, MutableSet<String>> {
        val raw = prefs.getString("seen_orders_json", null)
        val map = mutableMapOf<String, MutableSet<String>>()
        if (raw.isNullOrBlank()) return map

        try {
            val obj = JSONObject(raw)
            val keys = obj.keys()
            while (keys.hasNext()) {
                val k = keys.next()
                val arr = obj.getJSONArray(k)
                val set = mutableSetOf<String>()
                for (i in 0 until arr.length()) {
                    set.add(arr.getString(i))
                }
                map[k] = set
            }
        } catch (e: Exception) {
            // ignore
        }
        return map
    }

    fun saveSeenOrders(map: Map<String, Set<String>>) {
        val obj = JSONObject()
        for ((k, set) in map) {
            val arr = JSONArray()
            set.forEach { arr.put(it) }
            obj.put(k, arr)
        }
        prefs.edit().putString("seen_orders_json", obj.toString()).apply()
    }

    fun isMonitoring(): Boolean {
        return prefs.getBoolean("is_monitoring", false)
    }

    fun setMonitoring(active: Boolean) {
        prefs.edit().putBoolean("is_monitoring", active).apply()
    }
}
