"""Fixed, human-reviewable action library keyed by the highest known band.

The language model never writes actions. Code picks them from here, so every
instruction a coordinator receives was written and reviewed in advance.
Wording follows general public flood-preparedness guidance and MUST be
reviewed by the deploying agency (JKM / NADMA / district office) before use.
"""

from __future__ import annotations

from .models import Band

ACTIONS: dict[Band, list[tuple[str, str]]] = {
    Band.UNKNOWN: [
        ("Data tolok tidak lengkap. Semak keadaan sungai secara fizikal jika selamat, dan ikut arahan pihak berkuasa.",
         "Gauge data is incomplete. Check the river in person only if it is safe, and follow official instructions."),
    ],
    Band.NORMAL: [
        ("Pantau ramalan cuaca dan bacaan sungai.",
         "Keep watching the weather forecast and river readings."),
        ("Pastikan telefon dicas dan nombor kecemasan ada.",
         "Keep phones charged and emergency numbers ready."),
    ],
    Band.WASPADA: [
        ("Sediakan beg kecemasan: dokumen, ubat, lampu suluh, makanan kering.",
         "Prepare an emergency bag: documents, medicine, torch, dry food."),
        ("Kenal pasti warga emas, OKU dan kanak-kanak yang perlu dibantu berpindah.",
         "Identify elderly, disabled people and children who will need help to move."),
        ("Alihkan barang berharga ke tempat tinggi.",
         "Move valuables to higher ground."),
    ],
    Band.AMARAN: [
        ("Bersedia untuk berpindah. Bawa warga emas, OKU dan kanak-kanak ke tempat tinggi dahulu.",
         "Be ready to evacuate. Move elderly, disabled people and children to high ground first."),
        ("Jangan menyeberang sungai atau jalan yang dinaiki air.",
         "Do not cross rivers or flooded roads."),
        ("Hubungi pegawai daerah / JKM untuk status PPS dan pengangkutan.",
         "Contact the district office / JKM for relief-centre status and transport."),
    ],
    Band.BAHAYA: [
        ("Ikut arahan pemindahan pihak berkuasa SEKARANG. Pergi ke PPS yang dibuka.",
         "Follow official evacuation instructions NOW. Go to an open relief centre."),
        ("Jangan menyeberang air yang mengalir. Matikan suis utama elektrik jika selamat.",
         "Do not cross moving water. Switch off the mains electricity if it is safe."),
        ("Kecemasan: hubungi 999.",
         "Emergency: call 999."),
    ],
}


def actions_for(band: Band) -> list[tuple[str, str]]:
    return ACTIONS[band]


# Phrases the brief may never contain, in either language, whoever wrote it.
FORBIDDEN_PHRASES = [
    # false reassurance
    "selamat untuk tinggal", "tidak perlu berpindah", "tak perlu berpindah", "tiada bahaya",
    "tidak akan banjir", "tak akan banjir", "tiada risiko", "boleh abaikan",
    "safe to stay", "no need to evacuate", "no need to move", "no danger", "will not flood",
    "won't flood", "no risk", "you can ignore", "nothing to worry",
    # impersonating an authority
    "amaran rasmi", "arahan rasmi", "official warning", "official alert", "official order",
    "jps mengarahkan", "nadma mengarahkan", "jps orders", "nadma orders",
    # not our call to make
    "do not evacuate", "jangan berpindah",
]

DISCLAIMER_MS = "Ringkasan JagaSungai berdasarkan bacaan tolok JPS awam. Bukan amaran rasmi; ikut arahan pihak berkuasa."
DISCLAIMER_EN = "JagaSungai summary of public JPS gauge readings. Not an official warning; follow the authorities."
