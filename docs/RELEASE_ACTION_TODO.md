# Release Action TODO (Staging -> Production)

Bu dosya, konuşmada netleştirdiğimiz 3 kritik operasyon adımını unutmamak için oluşturuldu.

## P0 - Zorunlu Adımlar
- [ ] GitHub repo `vars/secrets` değerlerini `cicd/README.md` ile birebir doldur.
- [ ] Staging ortamını `cd-staging.yml` ile deploy et (monitor mod).
- [ ] Jüri sonrası production ortamını `cd-prod.yml` ile deploy et (`AuthEnforcement=on`, `RateLimitEnforcement=on`).

## 1) Vars / Secrets Kurulumu
Kaynak: `cicd/README.md`

- [ ] `Settings -> Secrets and variables -> Actions -> Variables` altına gerekli anahtarları ekle.
- [ ] `Settings -> Secrets and variables -> Actions -> Secrets` altına gerekli gizli değerleri ekle.
- [ ] `STAGING_API_KEYS_SECRET_VALUE_FROM` ve `PROD_API_KEYS_SECRET_VALUE_FROM` değerlerini AWS Secrets Manager/SSM `valueFrom` formatında ver.

## 2) Staging Deploy (Monitor)
- [ ] GitHub Actions içinde `CD Staging` workflow'unu çalıştır.
- [ ] Deploy sonrası `AlbDnsName` üzerinden health kontrolü yap:
  - [ ] `GET /health/live`
  - [ ] `GET /health/ready`
- [ ] API cevabında kontrol header'larını doğrula:
  - [ ] `X-Auth-Mode=monitor`
  - [ ] `X-RateLimit-Mode=monitor`

## 3) Production Deploy (Jüri Sonrası)
- [ ] `PROD_ALLOWED_ORIGINS` değerinin `*` olmadığını doğrula.
- [ ] `CD Production` workflow'unu çalıştır.
- [ ] Auth doğrulaması yap:
  - [ ] API key olmadan `401`
  - [ ] API key ile `200`
- [ ] API cevabında kontrol header'larını doğrula:
  - [ ] `X-Auth-Mode=on`
  - [ ] `X-RateLimit-Mode=on`

## Not
- Workflow dosyalarında modlar zaten tanımlı:
  - Staging: `.github/workflows/cd-staging.yml` -> `AuthEnforcement=monitor`, `RateLimitEnforcement=monitor`
  - Production: `.github/workflows/cd-prod.yml` -> `AuthEnforcement=on`, `RateLimitEnforcement=on`
