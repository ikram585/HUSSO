# HUSSO — Cihaz Teşhis Modülü (ADB/USB, yalnızca okuma)

Teknik servis için, USB ile bilgisayara bağlı **Android** cihazlardan
**yalnızca okuma** amaçlı teşhis bilgisi toplayan bir araç.

> ⚠️ **Kapsam ve etik:** Bu araç kilit atlatma, FRP bypass, iCloud/Activation
> Lock bypass veya herhangi bir güvenlik zafiyeti sömürüsü **yapmaz** ve bunu
> amaçlamaz. Yalnızca cihazın açıkça sunduğu bilgileri okur. İşlemler cihaz
> sahibinin bilgisi ve onayı ile yapılmalıdır.

## Ne okur?
- Üretici, marka, model, kod adı
- Android sürümü, SDK, güvenlik yaması, yapı (build) numarası
- IMEI (mümkünse; modern Android'de genelde `*#06#` gerekir)
- Pil: şarj yüzdesi, durum, sağlık, sıcaklık, voltaj, teknoloji
- Depolama (`/data`): toplam / kullanılan / boş
- Güvenlik göstergeleri: verified boot, bootloader kilit durumu, ekran kilidi
  var/yok, Google hesabı var/yok (yalnızca bilgi amaçlı)

## Gereksinimler
- Python 3.9+
- Android **platform-tools** (`adb`) kurulu ve PATH'te
- Cihazda **USB hata ayıklama** açık ve bilgisayar yetkilendirilmiş olmalı

## Kurulum
```bash
# platform-tools yoksa: https://developer.android.com/tools/releases/platform-tools
git clone <repo-url>
cd HUSSO
pip install -e .        # opsiyonel; komut olarak `husso` sağlar
```

## Kullanım (komut satırı)
```bash
python -m husso list                # bağlı cihazları listele
python -m husso info                # teşhis raporu (metin)
python -m husso info --serial ABC1  # belirli cihaz
python -m husso info --json         # JSON çıktı (fiş/kayıt sistemine aktarım için)
```

## Kullanım (yerel web arayüzü)
```bash
python -m husso.webapp              # http://127.0.0.1:8765
```
Tarayıcıdan cihazı seçip "Teşhis Et"e basın. Sunucu yalnızca `localhost`
üzerinde çalışır, dışarıya açılmaz.

## Testler
```bash
pip install -e ".[dev]"
pytest
```
Testler sahte bir `adb` çalıştırıcısı kullanır; gerçek cihaz gerektirmez.

## Notlar
- IMEI birçok modern Android sürümünde ADB ile okunamaz; bu durumda araç
  bunu belirtir ve cihazda `*#06#` çevrilmesini önerir.
- Ekran kilitliyken bazı bilgiler (hesap, kilit durumu) sınırlı okunur.
