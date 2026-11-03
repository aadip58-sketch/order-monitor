package in.gov.sci.monitor

data class CaseItem(
    val id: Int,
    var caseType: String = "",
    var caseNo: String = "",
    var year: String = "",
    var status: String = "Idle",
    var statusColor: Long = 0xFF757575,
    var ordersCount: Int = 0,
    var lastChecked: String = "Never"
) {
    fun isValid(): Boolean {
        return caseType.isNotBlank() && caseNo.isNotBlank() && year.isNotBlank()
    }

    fun getDisplayName(): String {
        if (!isValid()) return "Case Slot $id (Empty)"
        val typeLabel = CASE_TYPES[caseType] ?: "Type $caseType"
        return "$typeLabel $caseNo/$year"
    }

    fun makeKey(): String = "$caseType::$caseNo::$year"
}

data class Order(
    val date: String,
    val url: String,
    val label: String
) {
    fun uid(): String = "$date::$url"
}

val CASE_TYPES = mapOf(
    "1" to "SLP(C)",
    "2" to "SLP(Crl.)",
    "3" to "CA",
    "4" to "CrA",
    "5" to "WP(C)",
    "6" to "WP(Crl.)",
    "7" to "TP(C)",
    "8" to "TP(Crl.)",
    "9" to "RP(C)",
    "10" to "RP(Crl.)",
    "11" to "EP",
    "12" to "SMA",
    "13" to "MA",
    "14" to "Contempt",
    "15" to "ARB.P.",
    "16" to "OA",
    "17" to "LPA",
    "18" to "FA",
    "19" to "SA",
    "20" to "Suo Motu"
)

val CASE_TYPE_NAMES = mapOf(
    "1" to "SPECIAL LEAVE PETITION (CIVIL)",
    "2" to "SPECIAL LEAVE PETITION (CRIMINAL)",
    "3" to "CIVIL APPEAL",
    "4" to "CRIMINAL APPEAL",
    "5" to "WRIT PETITION (CIVIL)",
    "6" to "WRIT PETITION (CRIMINAL)",
    "7" to "TRANSFER PETITION (CIVIL)",
    "8" to "TRANSFER PETITION (CRIMINAL)",
    "9" to "REVIEW PETITION (CIVIL)",
    "10" to "REVIEW PETITION (CRIMINAL)",
    "11" to "ELECTION PETITION",
    "12" to "SPECIAL MISCELLANEOUS APPLICATION",
    "13" to "MISCELLANEOUS APPLICATION",
    "14" to "CONTEMPT PETITION",
    "15" to "ARBITRATION PETITION",
    "16" to "ORIGINAL APPLICATION",
    "17" to "LETTER PATENT APPEAL",
    "18" to "FIRST APPEAL",
    "19" to "SECOND APPEAL",
    "20" to "SUO MOTU"
)
