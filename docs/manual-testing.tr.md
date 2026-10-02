# Yayın öncesi test listesi

Kurulu Windows uygulaması için elle kabul testleri ve kaynak kontrolleri. Her senaryoyu geçti/kaldı/denenmedi olarak kaydedin. Hata raporlarında gerçek e-posta, giriş bilgisi ve özel konuşma içeriği paylaşmayın.

## Kurulum ve güncelleme kabul matrisi

| Akış | Kontrol | Beklenen sonuç |
| --- | --- | --- |
| Eksik CLI | Temiz Windows kullanıcısında ilk açılış; kurulumu önce reddet, sonra onayla. | Onaysız indirme/çalıştırma yok; onay sonrası CLI sürümü doğrulanır; model görevi başlamaz. |
| Mevcut CLI | Çalışan CLI ile sihirbazı aç. | Mevcut kurulum korunur; yalnızca sürüm okunur. |
| Tercihler/tur | Tercihleri kaydet, turu bitir/atla, uygulamayı tekrar aç. | Tercihler korunur; tur bir hesap işlemi başlatmaz. |
| Ağ kesintisi | Güncelleme kontrolünde ve indirme sırasında bağlantıyı kes. | Uygulama çalışmaya devam eder; bozuk paket çalıştırılmaz; yeniden deneme mümkündür. |
| Güncelleme bütünlüğü | Test sunucusu yerine izole otomatik testlerde eksik/bozuk içerik ve yanlış SHA-256 uygula. | Kurulum başlamaz; kısmi dosya temizlenir. |
| İşlem çakışması | Hesap işlemi veya bekleyen devam varken güncelle. | Hesap işlemi korunur; kurulum ertelenir. |
| Gerçek yayın | Ayrı test cihazında daha eski kurulu sürümle kararlı GitHub sürümünü denetle. | Bildirim görünür; kullanıcı tıklamasıyla yüklenir; yalnızca QuotaCrew yeniden açılır. |
| Veri ve boyut | Ardışık yükseltmelerde hesapları ve kurulum klasörünü karşılaştır. | Hesaplar korunur; eski bağımlılıklar/indirmeler birikmez; en fazla iki güncelleme yedeği tutulur. |
| GitHub desteği | Yardım sayfasındaki dört bağlantıyı aç. | Yalnızca genel proje/profil sayfaları açılır; rapor veya özel veri otomatik gönderilmez. |
| Codex kapalı | Desktop kapalıyken kayıtlı hesapların kullanımını yenile. | CLI üzerinden hesaplar bağımsız kontrol edilir; okunamayan ortak kimlik diğer okumaları engellemez; belirsiz kimlikte zorunlu token yenilemesi yapılmaz. |
| Sohbetlerin korunması | Kurulumdan önce/sonra Yerel konuşmalar listesini karşılaştır; Takibi temizle işlemini dene. | Codex konuşmaları silinmez; yalnızca QuotaCrew uygulamasının gözlem ve bekleyen devam kayıtları temizlenir. |
| RAM | Aynı iş yükü ve tercihlerle güncelleme öncesi/sonrası boşta ve etkin izleme örnekleri al. | Eski uygulama süreci kalmaz; RSS/alt süreç ölçümleri ayrı kaydedilir; kısa boşta ölçüm uzun vadeli sızıntı kanıtı sayılmaz. |

Tanılama geçmişi son 10.000 olayla sınırlıdır. Günlükler dosya başına 2 MB ve beş eski dosyayla döndürülür. Bu sınırlar konuşma dosyalarını, kurtarma kayıtlarını veya ayrı Codex CLI kurulumunu temizlemez.

## Test ortamı hazırlığı

- Uygulama, Windows, Codex CLI, Desktop, editör ve eklenti sürümlerini kaydedin.
- A ve B olarak size ait iki hesap kullanın. Geçişte B'nin kotası güncel ve kullanılabilir olmalı.
- Ayrı bir test projesi/konuşması açın. Diğer işleri kaydedip durdurun; hesap geçişi Desktop'ı yeniden başlatabilir.
- Temiz kurulum, kaldırma ve kurtarma testlerinde ayrı Windows kullanıcısı veya sanal makine kullanın. Kişisel veri klasörünü veya `~/.codex` içeriğini test için silmeyin.
- Gerçek kapatma testi dışında Otomatik Kapatma kapalı kalsın. Sahte kota hatası veya değiştirilmiş giriş dosyası canlı kabul testi değildir.

## Açılış, ayarlar ve tepsi

| Test | Adım | Beklenen sonuç |
| --- | --- | --- |
| İlk açılış | Ayrı kullanıcıda hesap eklemeden sayfaları gezin. | Anlaşılır boş durumlar; hata/kilitlenme yok; varsayılan izleme tercihi görünür. |
| Tek örnek | Uygulamayı ikinci kez başlatın. | İkinci bağımsız izleme süreci oluşmaz; mevcut pencere öne gelir. |
| Tercihler | Dil, tema, izleme, politika ve devam tercihlerini değiştirip yeniden açın. | Kaydedilen tercihler korunur; ekrandaki denetimler gerçek değerleri gösterir. |
| Tepsi | Tepside çalışmayı açın; pencereyi kapatıp tepsiden açın. | Uygulama çalışır; üst çubuk ve tepsi tutarlıdır. |
| Çıkış | Tepsi modunu kapatıp pencereyi kapatın; ayrıca tepsiden Çıkış'ı deneyin. | Uygulama çıkar; kendi devam çalışanı durur, kapatma planı iptal olur. |
| Windows başlangıcı | Açık/Kapalı seçimini değiştirip test kullanıcısında oturumu yeniden açın. | Açıkken başlar, kapalıyken başlamaz; seçim doğru yüklenir. |

## Tasarım ve erişim

Tüm sayfaları Türkçe/İngilizce, açık/koyu tema ve yaklaşık 1040 × 700 / 1480 × 960 boyutlarında kontrol edin. Windows ölçeklendirmesinde %100, %125, %150, %200 deneyin; gerekirse uygulamayı yeniden açın.

| Test | Adım | Beklenen sonuç |
| --- | --- | --- |
| Aynı hesap tablosu | Aynı hesap ve sıralamayla Genel Bakış/Hesaplarım'a geçin. | Başlık, avatar, plan, kota, yenilenme, durum ve menü görünümü aynı. Sayfa filtreleri/menü seçenekleri farklı olabilir. |
| Diğer tablolar | İşler, geçmiş, Etkinlik, Yerel Hedef Notları ve Sistem Kontrolü'nü açın. | Ortak renk/yazı/seçili satır/boş durum/kaydırma görünümü; sütunlar içerik türüne göre değişebilir. |
| Alan ve hizalama | Pencereyi büyütüp küçültün; uzun listeyi kaydırın. | Liste kalan yüksekliği kullanır; ilk/son satırlar erişilir; başlık/hücre hizası bozulmaz. |
| Uzun metin | Uzun hesap adı, Türkçe karakter ve proje yolu kullanın. | Satır taşmaz; kısaltılmış metnin tamamı ipucu/ayrıntıdan okunur. |
| Arama/filtre | Sonuç veren/vermeyen arama, filtre ve sıralamayı birlikte deneyin. | Doğru kayıtlar görünür; seçim ve menü doğru kayda işlem yapar. |
| Klavye | Tab, Shift+Tab, Enter, oklar, Ctrl+F ve Ctrl+R deneyin. | Görünür odak; desteklenen arama/yenileme doğru sayfada çalışır; menü ve diyaloglar erişilir. |
| İşlem sırasında gezinme | Yenileme/giriş sürerken başka sayfaya geçin; düğmeye tekrar basın. | Durum anlaşılır; çakışan kopya işlem oluşmaz. |

## Hesaplar ve bağlantı

| Test | Adım | Beklenen sonuç |
| --- | --- | --- |
| Otomatik giriş | Hesap ekleyip adını onaylayın. | İlk giriş akışı kendiliğinden açılır; ayrıca menüye basmak gerekmez. |
| İptal/yeniden deneme | Girişi iptal edip menüden yeniden başlatın. | Hesap yanlışlıkla kullanılabilir gösterilmez; tekrar giriş çalışır. |
| Tekrarlı gönderim | Ekleme/giriş/geçiş/yenilemeye hızlıca iki kez basın. | Çift hesap veya çakışan giriş/geçiş oluşmaz. |
| Kimlik uyuşmazlığı | Ayrı ortamda beklenen hesap yerine başka hesapla giriş yapın. | Uyuşmazlık görünür; yanlış kimlik sessizce hedefe bağlanmaz. |
| Kota | İki hesabı yenileyip yüzdeleri ve yenilenmeleri kontrol edin. | Başarısız/eksik yanıt %100 kullanılabilir sayılmaz; eski veri ve hata anlaşılır. |
| Ortak oturum yok | Ayrı test kullanıcısında kayıtlı profilleri koruyup Codex'ten çıkış yapın; kullanımı yenileyin. | Codex açıkça oturum olmadığını bildirdiğinde kayıtlı profiller bağımsız kontrol edilir; hiçbiri etkin gösterilmez. Geçersiz profil kendi giriş hatasını gösterir. |
| Manuel geçiş | A'dan B'ye ve geri geçin. | Etkin kimlik doğru; Desktop yeniden açılır; hesaplar/geçmiş korunur. Geçiş tek başına model işi başlatmaz. |
| İnternet kesintisi | Bağlantıyı kesin, yenileyin; bağlantıyı açıp tekrar deneyin. | Arayüz yanıt verir; bağlantı hatası kota dolu veya giriş silindi sayılmaz; toparlanır. |
| Uyku/uyanma | Bilgisayarı uyutup uyandırın, yenileyin. | Kontroller tekrar çalışır; eski veri canlı doğrulama sayılmaz. |
| Yönetim | İsim değiştirin, e-posta gizlemeyi deneyin; test hesabını kaldırın. | Doğru hesaba uygulanır; ortak Codex konuşmaları silinmez. |

## İşler ve hayalet kayıtlar

| Test | Adım | Beklenen sonuç |
| --- | --- | --- |
| Çalışan iş | En az bir izleme turu sürecek test işi başlatın. | Doğrulanmış iş üst çubuk/İşler/tepside tutarlı görünür. Çok kısa işler yoklamalar arasında kaçabilir. |
| Bitirme/durdurma | İşi bitirin; başka işte Codex'in Durdur düğmesini kullanın. | Sonraki başarılı kontrolde sayı güncellenir; kullanıcı durdurduğu işi uygulama devam ettirmez. |
| Canlı durum yok | Codex/editör bağlantısını kapatıp yenileyin. | Doğrulanamayan kayıt çalışan sayısına eklenmez; belirsizlik gösterilir. |
| Silinmiş konuşma | Test konuşmasını Codex'te silip başarılı tam tarama yaptırın. | Takip gözlemi temizlenir; başarısız/kısmi tarama silinme kanıtı sayılmaz. |
| Takibi temizle | Yenileme sürerken takip kayıtlarını temizleyin. | İzleme/devam duraklar; eski kontrol kayıtları geri getirmez; hesaplar/konuşmalar korunur. |
| Yeniden izleme | İzlemeyi başlatıp yeni iş çalıştırın. | Yeni doğrulanmış gözlemler oluşabilir; temizleme kalıcı izleme yasağı değildir. |
| Duraklatma | Duraklatılmışken isteğe bağlı yenileme yapın. | Okuma yapılabilir; otomatik hesap geçişi başlamaz. |

## Konuşmalar ve hedefler

- Geçmişi yenileyin; proje/kaynak/alt ajan filtreleri beklenen yerel kayıtları göstermeli. Geçmişte görünmek çalışıyor veya devam adayı olmak demek değildir.
- Devam desteğini kontrol et yalnızca kaynak/bağlantı sonucu göstermeli; mesaj göndermemeli. Kaynak etiketi tek başına canlı sahiplik kanıtı değildir.
- Projeyi editörde açmak yalnızca doğru klasörü açmalı; hesap değiştirmemeli veya model çalıştırmamalı.
- Codex hedefini okumak mevcut amaç/bütçe/durumu değiştirmemeli.
- Yerel hedef notu kaydetmek iş başlatmamalı; notu temizlemek Codex hedefini silmemeli.
- Duraklatılmış/engellenmiş/tamamlanmış/bütçesi bitmiş hedefler kendiliğinden yeniden etkinleşmemeli; bütçe sıfırlanmamalı.

## Gerçek Desktop limit sonrası devam

Gerçek kota kesintisinde deneyin; kota harcamak için gereksiz iş üretmeyin. Hata metninde “limit” olması yetmez: aynı tur önceden çalışırken gözlemlenmeli ve yapılandırılmış kesinti doğrulanmalı.

1. A'da test konuşmasını açın; B kullanılabilir olsun. Otomatik geçiş, izleme ve Desktop devamını açın.
2. Test turu en az bir başarılı kontrolde çalışırken görünsün; gerçek kesintide B'ye geçişi izleyin.
3. **Başarı:** aynı konuşmaya tek devam girdisi ulaşır; model, izinler, amaç ve bütçe korunur; yeni tur B altında izlenir. Desktop aracı gerekiyorsa aynı konuşmada çalışır; ayrı CLI konuşması oluşmaz.
4. Kullanıcı Durdur uyguladığında otomatik devam olmamalı.
5. Desktop devamı kapalıyken politika izin veriyorsa hesap değişebilir, ama devam girdisi gitmemeli.
6. Onay/kullanıcı girdisi bekleyen test işinde izinler otomatik onaylanmamalı; müdahale istenmeli.
7. Belirsiz teslimat bildirilirse konuşmayı kontrol edip uygulamayı yeniden açın: kör tekrar gönderim olmamalı. Canlı üretilemeyen senaryoyu otomatik test geçti diye canlı geçti işaretlemeyin.
8. Manuel politikada kendiliğinden geçiş; onaylı politikada öneri reddedildiğinde geçiş olmamalı.

## IDE: VS Code, Cursor, Windsurf

Kullandığınız her editörde ayrı deneyin. IDE devamı varsayılan kapalı ve deneysel. WSL, remote SSH ve bulut ortamları bu yerel Windows yolunun doğrulanmış kapsamı değildir.

1. Yerel test projesini açın; eklentide A hesabını doğrulayın. B kullanılabilir olsun.
2. IDE devamı kapalıyken iş çalıştırın: tercih üst çubuk/tepside kapalı görünmeli; otomatik devam girdisi gitmemeli.
3. Ayarlardan IDE devamını açın: üst çubuk/tepsi tercihi göstermeli. Rozet bağlantının çalıştığı veya editör hesabının doğrulandığı anlamına gelmez.
4. İşler'den devam desteğini kontrol edin: destek/bağlantı sonucu görünmeli; destek yoksa açık hata ve gönderim yok.
5. Aynı tur çalışırken gözlemlensin. Gerçek kota kesintisinden sonra B'ye geçişi ve IDE konuşmasını izleyin.
6. **Başarı:** aynı IDE konuşmasına tam bir devam girdisi ulaşır; iş editörde sonuç verir; model/izin/hedef/bütçe korunur. Başka Desktop/CLI konuşmasına aktarılmaz.
7. VS Code'da **Geçişten sonra VS Code’u yenile** seçeneğini açarak tek yerel pencereyle deneyin. Doğrulanmış devam öncesinde pencere normal kapanıp aynı sohbetin klasörüyle açılmalı; yeni sahip ve kesilen tur tekrar doğrulanmalı. Bağlantı açma onayı görünürse onaylayın ve bunu manuel adım olarak kaydedin. **Yeni hesabı editörde ayrıca doğrulayın:** uygulama eklentinin önbellekteki kimliğini bağımsız okuyamıyor.
8. IDE kapalı/meşgul/onay bekliyor durumlarında otomatik gönderim yapılmamalı; belirsiz gönderim tekrarlanmamalı.
9. Uzun konuşma desteklenen okuma sınırını aşarsa görünür hata olmalı; sınırsız okuma, kilitlenme veya alternatif gizli CLI çalıştırma olmamalı.
10. IDE devamını kapatıp yeniden açın: tercih korunmalı; kullanıcı tarafından durdurulan eski işler başlamamalı. Aynı anda süren bağımsız Desktop/CLI devam işlemleri yalnızca IDE seçeneği kapatıldığı için durmamalı.

Bu zincir canlı doğrulanmadan IDE özelliğini kararlı diye tanıtmayın. Eklentinin manuel yenilenmesi gerekiyorsa bu bir sınırlama olarak yazılmalı.

VS Code yenilemesinin ek kontrolleri:

| Test | Adım | Beklenen sonuç |
| --- | --- | --- |
| Kaydetme onayı | Kaydetme sorusu çıkaran yerel belgeyle yenilemeyi deneyin. | Onay kapatılmaz, zorla sonlandırma yapılmaz; süre dolunca müdahale gerekir. |
| Diğer iş/onay | Başka IDE konuşması çalışırken veya onay beklerken deneyin. | Yenileme ve gönderim yapılmaz. Desktop devam kanalı değişmez. |
| Birden çok pencere | İki VS Code penceresiyle deneyin. | Hangi pencerenin kapanacağı tahmin edilmez; yenileme durur. |
| Hızlı kota hatası | İzlemenin IDE'de bir başlangıç turu okumasından sonra yeni tur iki kontrol arasında başlayıp doğrulanmış kota hatası versin. | Hesap/hedef değişmediyse yeni tur seçilebilir; uygulama açılmadan önceki eski hata kendiliğinden başlamaz. |
| Geciken bağlantı | Yeniden açılışta bağlantı onayını kısa süre bekletin. | Gönderilmemiş istek sonraki kontrolde yeniden doğrulanır; süre sınırı 10 dakika, tekrarlı gönderim yok. |

## Otomatik Kapatma

Gerçek kapatmayı yalnızca son senaryoda, ayrı test oturumunda, diğer çalışmalar kaydedilince deneyin. Otomatik testler kapatma fonksiyonunu taklit eder; bilgisayarı kapatmaz.

| Test | Adım | Beklenen sonuç |
| --- | --- | --- |
| Süre | Süreli modu seçip 1/10/120/180/1440 girin; 0/1441 deneyin. | Sınır 1–1440, dakika birimi ve saat örnekleri görünür; süre değiştirmek plan başlatmaz. |
| Toplam süre | Süreli modda 1 dakika planlayıp uyarıyı inceleyin ve iptal edin. | Uyarı hemen başlar; ek 2 dakika eklenmez. Hesap bağlantısı ve izleme ayarı süreyi değiştirmez. |
| Koşul süresi | İş ve limit modlarına geçin. | Süre alanı gizlidir; doğrulama sonrası sabit 2 dakika sayılır. |
| Onay/iptal | Onayı reddedin; sonraki denemede kabul edip pencere/tepsiden iptal edin. | Ret kapalı bırakır; kabul görünür plan oluşturur; iki yerden iptal çalışır. |
| Tüm limitler | Gerçek sınırlı hesaplarla koşulu deneyin. | Kullanılabilir/bilinmeyen/eski kota, kullanılabilir sıfırlama hakkı veya çalışan iş geri sayımı engeller. |
| Seçilen iş | Kapatma sayfasından çalışan bir sohbet seçin; iş menüsündeki kısayolu da deneyin. | Aynı tur/hedef beklenir; başka çalışan Codex işi varken kapanmaz; değişen hedef tamamlanma sayılmaz. |
| Tazelik | İş veya limit modunda geri sayım sırasında doğrulama bağlantısını kesin. | Kanıt kaybolunca geri sayım sıfırlanır; eski kanıtla kapatılmaz. |
| Oturum | Her modda izlemeyi duraklatmayı ve uygulamadan çıkmayı deneyin. | İzlemeyi duraklatmak koşullu planları iptal eder, süreli planı etkilemez. Uygulamadan çıkmak tüm planları iptal eder; yeniden açılışta kapalıdır. Tepsi modunda pencereyi gizlemek çıkış değildir. |
| Gerçek yürütme | Ayrı oturumda koşulu sağlayıp kısa süreyle bekleyin. | Son kontrol sonrası Windows kapatma ister; uygulamalar zorla kapanmaz. Windows kaydedilmemiş iş için kapatmayı engelleyebilir. |

120/180 dakikayı tamamen beklemek gerekmez: uzun süre sınırları otomatik testlerde var. Elle giriş/gösterim/iptali doğrulayın; gerçek yürütmeyi kısa süreyle deneyin. Bu özellik diğer uygulamalardaki kaydedilmemiş işi algılamaz.

## Gizlilik ve yayın dosyaları

- Sistem Kontrolü sonuçları ve tam açıklamaları okunmalı; CLI yoksa açık sonuç verilmeli.
- Tanılama arşivini yerelde açın: gerçek ad/e-posta, yol, ham hata, konuşma, token, giriş dosyası ve veritabanı olmamalı. İzin verilen durumlar, doğrulanmış CLI sürümü ve hesap sayısı kalabilir.
- Yayın görselleri örnek hesaplarla hazırlanmalı; gerçek özel bilgi içermemeli.
- README, lisans, güvenlik, katkı, değişiklik ve bağımlılık bildirimlerini kontrol edin; deneysel IDE ve imzasız paketler doğru açıklanmalı.
- `git status --short` ile yayınlanacak dosyaları tek tek inceleyin. Şu an değişiklikler commit edilmedi; yeni kaynaklar ve `site/` untracked. Site dosyaları yayın kapsamına bilinçli dahil edilmeli veya dışarıda bırakılmalı.
- `.venv`, cache, build, dist, gerçek hesap verisi, yedek ve günlükler kaynak yayınına girmemeli. Tüm çalışma klasörünü ZIP yapmayın. `HEAD` arşivi henüz commit edilmemiş yeni sürümü içermez.
- Gizli bilgi taramasını güncel yayın kaynağına ve tüm Git geçmişine uygulayın. Yalnızca geçmiş taraması uncommitted dosyaları kontrol etmez. Görseller ve kişisel bilgiler ayrıca gözle incelenmeli.

## Kurulum, güncelleme, kaldırma

Ayrı Windows kullanıcısı/sanal makinede:

1. Python kurulu olmadan yükleyin; GUI ve CLI yardımını açın.
2. Masaüstü/Başlat kısayolları doğru EXE'yi açmalı; başlangıç seçimi çalışmalı.
3. Eski sürümde test profili/ayar oluşturup güncelleyin: hesaplar, tercihler ve Codex geçmişi korunmalı.
4. Kaldırın: uygulama dosyaları/kısayolları/kendi başlangıç girdisi kalkmalı; hesap verileri ve Codex geçmişi korunmalı.
5. Tekrar kurup verilerin okunabildiğini kontrol edin.
6. Portable paketi tamamen çıkarıp başka klasörden açın. Yalnızca EXE'yi taşımak geçerli test değildir; `_internal` gereklidir.
7. Sürüm, hash ve bağımlılık lisanslarını doğrulayın; yeni sürüm için GitHub Windows/Linux matrisi ve paket/installer işleri geçmeli.

`scripts/verify_windows_installer.py` kişisel bilgisayarda genel kabul testi olarak çalıştırılmaz; disposable GitHub-hosted runner dışında çalışmayı reddeder.

## Otomatik komutlar

Geliştirme ortamı hazırken depo kökünde:

```powershell
.venv\Scripts\python -m ruff check src tests scripts
.venv\Scripts\python -m ruff format --check src tests scripts
.venv\Scripts\python -m mypy --platform win32 src
.venv\Scripts\python -m mypy --platform linux src
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m pip check
git diff --check
```

Odaklı tekrarlar:

```powershell
.venv\Scripts\python -m pytest -q tests/unit/test_gui.py
.venv\Scripts\python -m pytest -q tests/unit/test_native_ide.py tests/unit/test_editors.py
.venv\Scripts\python -m pytest -q tests/integration/test_limit_continuation.py tests/integration/test_work_tracking.py
.venv\Scripts\python -m pytest -q tests/unit/test_power.py
```

CI güvenlik/build araçları ortamda yoksa kurup çalıştırın:

```powershell
.venv\Scripts\python -m pip install pip-audit bandit build
.venv\Scripts\python -m pip_audit --local --skip-editable
.venv\Scripts\python -m bandit -r src -ll
.venv\Scripts\python -m build
```

GUI testleri offscreen, hesap/protokol testleri izole sahte adaptörlerle çalışır. Linux Mypy hedefi Linux runtime testi değildir. Bağımlılık taramasında ağ erişim hatası temiz sonuç sayılmaz. Secret scan ve paket testleri için [CI](../.github/workflows/ci.yml), derleme için [paketleme rehberi](../packaging/README.md).

## Sonuç kaydı

### İki Desktop ve bir VS Code konuşmasıyla ortak limit testi

QuotaCrew uygulamasını Windows Başlat menüsü kısayolundan açın. Codex'in terminalinden başlatılmış bir QuotaCrew, onu çalıştıran Desktop sürecini kapatmayı reddeder. Geçiş boyunca QuotaCrew uygulamasının açık kaldığını ve yalnızca Desktop'ın yeniden başladığını ayrıca doğrulayın. VS Code'da “ChatGPT hit a snag” görünürse test başarısızdır; gönderim kaydı bunu başarılı saydırmaz.

1. Desktop ve VS Code'daki OpenAI Codex eklentisinde toplam üç yerel konuşma açın. İzleme, Desktop devamı ve IDE devamı açık olmalı. VS Code'un başka sağlayıcıya bağlı sohbeti bu teste dahil değildir; uygulama eklenti kurmaz.
2. Üç konuşmanın da çalışan turlarının İşler'de gözlendiğini doğrulayın. Yalnızca sohbeti açmış olmak yeterli değildir. Uygun ikinci hesabın güncel ve kullanılabilir olduğunu kontrol edin.
3. Gerçek limit kesintisinden sonra hesap değişimini bekleyin. Her konuşmada yalnızca bir devam girdisi ve yeni tur oluşmalı; bir konuşmanın hatası diğerlerini durdurmamalı. Test sırasında elle yeni mesaj göndermeyin.
4. İşler satır menüsündeki **Otomatik devam ayrıntıları** bölümünü her konuşma için inceleyin. Hazırlık, bağlantı, hesap doğrulaması, meşgul durum, gönderim ve gözlem aşamalarını ayrı kaydedin. “Gönderildi” sonucu tek başına görevin tamamlandığını göstermez.
5. VS Code'da aktif hesabı ayrıca doğrulayın; pencereyi yeniden yüklemek gerekti mi kaydedin. Bu sürüm eklentinin bellekteki hesabını bağımsız doğrulamaz. Manuel yükleme gerekiyorsa kesintisiz IDE kabul testi geçmiş sayılmaz.
6. Aynı kesintiyi yeniden kontrol ettirin; ikinci devam girdisi oluşmamalı. Onay bekleyen, kullanıcı tarafından durdurulmuş veya hedefi değişmiş konuşmaya otomatik girdi gönderilmemeli.

```text
Uygulama / Windows / Codex CLI / Desktop sürümü:
Editör ve Codex eklenti sürümü:
Senaryo ve sonucu: geçti / kaldı / denenmedi
Adımlar ve beklenen-gerçek sonuç:
IDE hesabı ayrıca doğrulandı mı? Manuel reload gerekti mi?
Tekrar mesaj, veri kaybı veya yanlış hesap gözlendi mi?
```

Başarısız/denenmemiş senaryoları yayın notlarında belirtin. Canlı IDE zinciri doğrulanmazsa deneysel etiketini koruyun. Veri kaybı, yanlış kimlik veya yinelenen devam girdisi bulgularını yayınlamadan giderin.
