"""What the 3D kit offers, readable without Blender: the names a scene.json may use.

The lists must match the builders in bpy_kit/ (a test parses those files and compares), so the
validator can say exactly which names exist before anything renders.
"""

from __future__ import annotations

SETS = {
    "room": "Oda (yatak, pencere, masa, laptop)",
    "bedroom_night": "Oda, gece (tavan lambası)",
    "bathroom": "Banyo (fayans, klozet, lavabo, ayna)",
    "classroom": "Sınıf (yeşil tahta: set_opts.text tahtaya yazılır, sıralar, saat)",
    "kitchen": "Mutfak (tezgâh, ocak, buzdolabı)",
    "office": "Ofis (masalar, laptoplar, pencere)",
    "gym": "Spor salonu (bench, halter, ayna; set_opts.text afiş yazısı)",
    "cutaway": "Kesit: pasta gibi kesilmiş bahçe bloğu (çim, toprak katmanları), arkada iki katlı ev; pit ile kazılır, layer ile doldurulur (set_opts.season: summer | autumn | winter)",
    "elevator": "Asansör kabini (kapı, kat levhası: set_opts.floor, düğme paneli, tutamak; set_opts: open, ceiling=false tepeden çekim için, shaft kuyuyu açar, emergency kırmızı ışık)",
    "street": "Şehir sokağı (dükkânlar ve tabelaları, ağaçlar, lambalar, arabalar; set_opts.shops tabela adları, night)",
    "city": "Şehir, yukarıdan (bina blokları, yollar, parklar): geniş ve havadan planlar",
    "park": "Park (çimen, ağaçlar, bank, yol)",
    "space": "Uzay (yıldızlar, aşağıda Dünya, uzakta Ay)",
    "studio": "Renkli sonsuz fon (set_opts.color): anlatım, eşya yakın planı, liste",
    "world": "Dünya kadrajda, uzaydan (herkes/dünya çapında anlar)",
}

PROPS = {
    "bed": "yatak", "toilet": "klozet", "sink": "lavabo", "desk": "masa", "school_desk": "okul sırası",
    "chair": "sandalye", "sofa": "kanepe", "tv": "televizyon (text)", "laptop": "laptop", "phone": "telefon",
    "fridge": "buzdolabı", "stove": "ocak", "counter": "tezgâh", "car": "araba (color)", "bus": "otobüs",
    "tree": "ağaç (h)", "pine": "çam", "bench": "bank", "lamp_post": "sokak lambası", "box": "kutu (size, color)",
    "ball": "top (d, color)", "barbell": "halter", "weight_bench": "bench sehpası", "door": "kapı (text: kapıdaki levha)",
    "window": "pencere", "plant": "saksı bitkisi", "cup": "bardak", "burger": "hamburger", "money": "para destesi (n)",
    "rocket": "roket", "house": "ev", "building": "bina (w, d, h, text: tabela)", "shop": "dükkân (text: tabela, awning)",
    "sign": "tabela/levha (text, size)", "newspaper": "gazete (masthead, text: manşet)", "screen": "ekran / güvenlik monitörü (text)",
    "calendar": "takvim (month, text: gün)", "clock": "duvar saati (hours: 10.25 = 10:15)", "arrow": "büyük ok (bir şeyi gösterir)",
    "globe": "Dünya küresi (r)", "moon": "Ay (r)", "cloud": "bulut (z)", "water_jet": "ışın/fışkırma (len, color)",
    "crowd_person": "kalabalık için basit insan (color)",
    "wanted": "ARANIYOR afişi (text: isim, reward: ödül)", "map": "duvar haritası (text: yer, pins: [[x, y], ...] -1..1)",
    "phone_big": "büyük telefon ekranı: sosyal medya gönderisi (text: #etiket, likes, user)",
    "pit": "kesitte çukur (shape: bowl | box | shelf | trench | tunnel, size [en, derinlik, derinlik m], id)",
    "layer": "çukuru dolduran katman (pit: id, material: water | green_water | sand | gravel | concrete | asphalt | liner | ice..., from/to: m)",
    "pipe": "boru / kablo (path [[x, y, z], ...], r, color)", "fish": "balık (size, color)",
    "lily_pad": "nilüfer yaprağı (flower: true)", "tank": "kutu / tank / filtre (size, shape: box | drum, text)",
    "hand_pump": "el pompası (color)",
    # gerçek modeller (3B dünya kütüphanesi; yoksa basit karşılığı çizilir)
    "taxi": "taksi", "police_car": "polis arabası", "sports_car": "spor araba", "suv": "SUV",
    "big_tree": "dev ağaç (16 m)", "bush": "çalı", "flowers": "çiçek öbeği", "grass": "uzun çimen", "rock": "kaya",
    "fern": "eğrelti", "shrub": "süs bitkisi", "armchair": "koltuk", "coffee_table": "sehpa", "dining_table": "yemek masası",
    "fire_hydrant": "yangın musluğu", "trash_can": "çöp konteyneri", "bookshelf": "kitaplık", "desk_lamp": "masa lambası",
    "cctv_camera": "güvenlik kamerası (z: yükseklik)", "bollard": "bariyer direği", "ac_unit": "klima dış ünitesi",
    "planter": "büyük saksı", "manhole": "rögar kapağı",
}  # fmt: skip

ACTIONS = {
    "idle": "durur, nefes alır", "walk": "yürür (path)", "run": "koşar (path)", "sneak": "sinsice yürür (path)",
    "jump": "zıplar", "wave": "el sallar", "fall": "sırtüstü düşer", "shake": "titrer (korku, soğuk)",
    "nod": "başını sallar", "spin": "kendi etrafında döner", "shock": "şok (kollar yanda)", "arms_up": "kollar havada",
    "point": "önünü gösterir", "point_up": "yukarıyı gösterir", "think": "düşünür", "facepalm": "eliyle yüzünü kapatır",
    "shrug": "omuz silker", "cheer": "sevinir (zıplayarak)", "hands_hips": "eller belde", "scared": "korkar, büzülür",
    "sit": "oturur", "lie": "yatar", "crouch": "çömelir", "flex": "kas gösterir", "hold": "önünde bir şey tutar",
    "phone": "telefona bakar", "sad": "üzgün, omuzlar düşük", "run_reach": "uzanarak koşar",
    # gerçekçi karakterlerde hareket kaydı kalitesinde kütüphane animasyonları
    "talk": "konuşurken el kol hareketleri", "jog": "hafif koşar (path)", "walk_formal": "resmi yürür (path)",
    "dance": "dans eder", "hit": "göğsüne darbe alır", "hit_head": "kafasına darbe alır", "pickup": "masadan bir şey alır",
    "push": "bir şeyi iter", "roll": "takla atar", "punch": "yumruk atar", "swim": "yüzer", "float": "suda durur",
    "drive": "araba sürer (otururken)", "interact": "bir şeye dokunur / düğmeye basar", "fix": "diz çöküp tamir eder",
    "present": "eliyle bir şeyi sunar", "sit_talk": "otururken konuşur", "stand_up": "oturduğu yerden kalkar",
    "fly": "uçar / havalanır (path: [[x, y, z], ...])", "give": "elindekini öne uzatır (verir)",
    "dodge": "geri çekilir, kaçınır",
}  # fmt: skip

FACES = (
    "neutral",
    "happy",
    "grin",
    "shock",
    "surprised",
    "angry",
    "sad",
    "scared",
    "smug",
    "confused",
    "talk",
)
FRAMES = {
    "face": "yüz",
    "close": "omuzlardan yukarı",
    "medium": "belden yukarı",
    "full": "boydan",
    "wide": "geniş: kişi ve çevresi",
    "far": "uzak",
    "aerial": "havadan",
    "top": "tepeden",
    "low": "alttan (kişiyi büyük gösterir)",
    "hands": "eller / masa üstü",
}
MOVES = {
    "static": "sabit", "push": "yavaşça yaklaşır (varsayılan)", "pull": "uzaklaşır", "orbit": "etrafında döner",
    "pan": "yana kayar", "rise": "yükselir (vinç)", "fall": "alçalır", "zoom_out": "ölçek açılışı: yakından çok uzağa",
    "dolly": "ileri yürür", "follow": "hareket eden kişiyi izler", "shake": "sarsıntı",
}  # fmt: skip
BODIES = ("adult", "kid", "big", "old", "tall")
HAIR = ("short", "parted", "long", "bun", "buns", "buzzed", "curly", "bald", "hood", "cap")
TOPS = ("tshirt", "longsleeve", "hoodie", "tank", "coat", "suit")
BOTTOMS = ("jeans", "trousers", "shorts", "skirt")
OUTFITS = ("casual", "suit", "chef", "doctor", "lab")
SFX = ("whoosh", "pop", "impact", "riser", "ding", "boom")

# Effects: things that happen in the shot at a moment (`at`: a word of the line or a fraction).
# `pos` [x, y, z] or `on` (an actor or a prop id); `size` scales; `dur` seconds.
FX = {
    "crack": "zemin (ya da wall: true ile duvar) çatlar, çatlak büyür",
    "debris": "parçalar fırlar, düşer, seker (n, color)",
    "shatter": "cam kırılır, kırıklar saçılır",
    "explosion": "patlama: ateş topu, ışık, duman, parçalar",
    "smoke": "duman yükselir (color)",
    "fire": "alev yanar (dur boyunca)",
    "sparks": "kıvılcım saçılır",
    "flood": "su seviyesi yükselir (level: m)",
    "pour": "akan sıvı ve büyüyen birikinti (color)",
    "rain": "yukarıdan yağar (item: money | confetti | water | snow, area: [x0, y0, x1, y1])",
    "flash": "ışık patlaması (color)",
    "shake": "kamera sarsılır (amount)",
    "beam": "ışın: pos'tan to'ya (color)",
    "split": "bir eşyayı ikiye böler, parçalar ayrılır (target: eşya id'si)",
    "pop": "bir eşya 'pat' diye belirir (target)",
    "vanish": "bir eşya küçülüp kaybolur (target)",
}
# Looks: how a shot is shown (drawn over its frames, after the render).
LOOKS = {
    "security": "güvenlik kamerası: siyah-beyaz, kumlu, REC ve saat (text: KAMERA 03)",
    "news": "canlı yayın: SON DAKİKA bandı, manşet, alt yazı kayan bant (text, ticker, channel)",
    "phone": "telefon ekranında video: kullanıcı, beğeni sayacı, #etiket (text, user, likes)",
    "old": "eski film: sepya, gren, titreme (tarih sahneleri)",
    "nightvision": "gece görüşü: yeşil, kumlu",
}
CROWD_DO = ("idle", "cheer", "jump", "walk", "run", "panic", "dance", "talk", "shock", "point_up")
