# MotionForge Pro - v2.8 (Mobile Integration Update) 🚀

MotionForge v2.8 "Multi-Camera" güncellemesine hoş geldiniz! Bu sürüm, sistemi sıradan bir webcam prototipinden çıkartıp profesyonel bir mobil mocap stüdyosuna çevirmiştir.

## v0.1 Alpha'dan (v2.7) Ne Değişti? (Yenilikler)

### 📱 1. Kablosuz ve Mobil Kamera Desteği (YENİ!)
- **WiFi IP Kamera**: Artık doğrudan cep telefonunuzun devasa çözünürlüklü kamerasını kablosuz olarak (ör: IP Webcam uygulaması ile) kullanabilirsiniz! Uygulama açılışında sizden IP adresini ister ve saniyeler içinde bağlanır.
- **USB Sanal Kamera**: Iriun, DroidCam veya EpocCam gibi USB üzerinden bağladığınız mobil kameraları anında tanır.
- *Fayda*: Artık bilgisayara bağlı kalmak zorunda değilsiniz. Büyük alanlarda telefonu tripod'a koyarak hareketlerinizi kusursuz kaydedebilirsiniz!

### 🛡️ 2. Motor Güvenliği ve Kalkanlar (YENİ!)
- **Confidence Matrix (Güvenilirlik Filtresi)**: Vücudunuz veya bir uzvunuz ışıktan/açıdan dolayı tam görünmüyorsa motor artık sapıtmıyor! Anında durumu tespik edip yumuşatıcıları (smoothing) agresif moda çekerek titremeyi durduruyor.
- **Frame Drop Compensator (Kare Düşüş Koruyucu)**: Mobil Wi-Fi bağlantınızda veri paketleri kaybolursa animasyonunuz yırtılmaz. Sistem son 5 karenin ivmesini hesaplayarak boşluğu otomatik doldurur.
- **Bone Clamping (Kemik Kilidi)**: İskeletinizin ölçüleri asla bozulmaz, uzuvlarınızın esnemesi veya boyunuzun anormal değişmesi engellendi.

### 🎥 3. "Cinematic Viewer" İyileştirmeleri
- **Ghost Trail (Hareket İzi)**: Animasyonları analiz etmek artık çok daha kolay! Elleriniz ve ayaklarınız arkalarında neon *Cyan* renkli akıcı bir iz bırakır (3D vizördeki 'Ghost Trail' tuşu ile açabilirsiniz).
- **RESET CAM**: Kamera açısını kaybettiğinizde tek tuşla başlangıç izometrik açısına dönebilirsiniz.
- **Auto-Exposure (Otomatik Parlaklık)**: Artık karanlık bir odaya girseniz bile (veya ışık arkada kalsa bile) motor yüzünüzü zifiri karanlık yapmaz, Frame-Rate (FPS) kaybetmeden anında ışığı (Gamma LUT) dengeler.

### 🤖 4. Offline Bake Güçlendirmesi
- Artık `.bake` işlemlerinde derinlik (Z ekseni - kameraya ileri/geri gitme) üzerine yapışan **Jitter (Yapay Titreme)** engelleniyor. Offline işlem sonrası model *ayağı yere çok daha sağlam basıyor*.

---

## Kurulum ve Çalıştırma
Hiçbir kütüphane kurmanıza gerek yoktur, yazılım Standalone (Kendi Başına) çalışır:

1. `MotionForge_v2.8_PRO.exe` dosyasına tıklayın.
2. Karşınıza çıkan **Source Selection (Kamera Seçim)** ekranından:
   - *Webcam* 
   - *Mobil WiFi* (IP Webcam IP'si gerektirir)
   - *Mobil USB* (DroidCam gerektirir)
   seçeneklerinden birini işaretleyin.
3. Live Capture ekranında `R` tuşu ile kayda girin, `S` tuşu ile kaydedin. `Q` ile çıkış yapın.
4. Kaydettiğiniz ham dosyaları **Offline Bake** yaparak profesyonel standartlara çekin.

Bol Mocap'li, Titremesiz günler dileriz! 🦾💎
