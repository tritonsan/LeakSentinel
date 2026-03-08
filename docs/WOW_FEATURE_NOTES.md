# LeakSentinel - Wow Factor ve Kritik İyileştirme Notları

## 1) Kritik Öncelik (Önce Bunlar)
1. `real_challenge` etiketleme varsayımını doğrula.
- Şu an `class 1 = normal, diğerleri = leak` varsayımı agresif.
- Önce GPLA sınıf semantiğini doğrula, sonra binary mapping'i netleştir.
- Dosyalar: `scripts/download_gpla12.py`, `docs/DATASETS.md`

2. Benchmark raporunu iki lane olarak koru.
- `Core KPI` (ana başarı metriği)
- `Real Challenge` (zorlayıcı stres testi)
- Amaç: düşük real_challenge skorunun core değerlendirmeyi gömmesini engellemek.
- Dosya: `leaksentinel/eval/benchmark.py`

3. Demo/video iddiasını doğru çerçevele.
- "Gerçek saha doğrulaması" yerine:
- "Public scientific acoustic benchmark track (hybrid evaluation)"
- Dosyalar: `ABOUT.md`, `README.md`, video script

## 2) Yeni Fikirler (Wow Factor)
1. Ask-for-More-Evidence Agent
- Kararsız vakada otomatik "next best evidence" önerisi üret.
- Örnek: "Thermal zayıf, audio güçlü -> +10 dk thermal frame iste."
- Değer: Agentic kabiliyeti net gösterir.

2. Counterfactual Panel
- "Planned ops olmasaydı karar ne olurdu?" karşılaştırması.
- Değer: Jüri için açıklanabilirlik etkisi yüksek.

3. Impact Meter
- Karar başına operasyonel etki:
- Tahmini yanlış dispatch maliyeti
- Potansiyel kaçak kaybı önleme
- Değer: Teknik çıktıyı iş etkisine çevirir.

4. Reliability Card
- Son N koşuda:
- `bedrock_used` oranı
- fallback oranı
- feedback trendi
- Değer: "prototype" algısını azaltır.

## 3) Eleştirel "Bunu Böyle Yapalım" Önerileri
1. `real_challenge` için ayrı confidence calibration uygula.
2. `planned_ops` suppress kararında guardrail gerekçesini UI'da belirginleştir.
3. `investigate` sınıfını büyüt (operasyonel gerçeklikte çok kritik).

## 4) 72 Saatlik Uygulama Planı
1. Gün 1
- GPLA class mapping doğrulama
- Dataset rebalance
- Benchmark rerun (`core` + `real_challenge`)

2. Gün 2
- Ask-for-More-Evidence Agent
- Counterfactual panel

3. Gün 3
- Impact meter
- Reliability card
- Video script'i bu üç sahne etrafında sabitleme

## 5) Hızlı Done Kriteri
1. Core ve real_challenge metrikleri raporda ayrı görünmeli.
2. `real_challenge` için etiketleme mantığı dokümante ve tekrar üretilebilir olmalı.
3. Demo sırasında en az bir "kararsız vaka -> ek kanıt isteği" canlı gösterilmeli.
4. Video iddiaları, çalışan özelliklerle birebir uyumlu olmalı.

## 6) Uygulama Durumu (12 Şubat 2026)
- [Done] `core` ve `real_challenge` track ayrımı benchmark raporunda ayrı tablolarla üretiliyor.
- [Done] GPLA-12 indirme/etiketleme akışı (`data_v3` -> `data_v1` fallback) dokümante ve tekrarlanabilir.
- [Done] Ask-for-More-Evidence çıktısı karar objesine eklendi (`next_evidence_request`).
- [Done] Counterfactual panel çıktısı eklendi (`counterfactual`: no planned ops varsayımı).
- [Done] Impact meter çıktısı eklendi (`impact_estimate`).
- [Done] UI tarafında reliability card + planned ops guardrail görünürlüğü artırıldı.
- [Done] Track bazlı kalibrasyon (özellikle `real_challenge` için daha esnek policy eşikleri) aktif.
- [Done] Holdout değerlendirme paketi eklendi: `data/scenarios/scenario_pack_holdout.json`
- [Done] Benchmark CLI artık dışarıdan senaryo paketi alıyor: `--scenario-pack`
- [Done] İkinci bağımsız holdout paketi eklendi: `data/scenarios/scenario_pack_holdout_v2.json`
- [Done] Feedback kayıtları root-cause ve evidence-gap alanlarıyla zenginleştirildi.
- [Done] Karar çıktısına historical root-cause özeti eklendi.
- [Done] Karar çıktısına investigate güvenlik alanları eklendi (`decision_safety_flags`, `investigate_reason_code`).
- [Done] Benchmark raporuna investigate yanlış leak metriği eklendi (`Inv->Leak %`).
- [Done] Hardening operasyon rehberi eklendi (`docs/HARDENING_PLAYBOOK.md`).
