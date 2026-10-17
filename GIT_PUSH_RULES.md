# Git Push & Commit Kuralları

Bu belge, Mnemosyne deposuna yapılacak commit ve push işlemleri için geçerli standartları tanımlar.

## 1. Tekil Dosya İşleme (Atomic Commits & Pushes)
- Değişiklikler toplu halde tek bir commit/push olarak gönderilmez.
- Her güncellenen veya yeni eklenen dosya bağımsız, tekil bir commit olarak hazırlanır ve ayrı ayrı push edilir.

## 2. Karakter Farkı Denetimi
- Dosyanın `origin/<branch>` ile yerel kopyası arasındaki karakter/bayt farkı hesaplanır.
- **Karakter farkı yoksa (0 net fark / yalnızca anlamsız boşluk):** Dosya commit/push edilmez, atlanır.
- **Ciddi fark varsa (büyük kod silinmesi veya eklenmesi):** İşleme geçilmeden önce kullanıcıya bildirim verilir.

## 3. Dosyaya Özel Commit Mesajı Formatı
Commit açıklaması yalnızca o dosyaya özgü olmalıdır. Yapılan değişiklikler dosyanın önceki haliyle karşılaştırılır (diff) ve commit gövdesine detaylı maddeler olarak yazılır.

### Standart Format (Conventional Commits)
```gitcommit
<type>(<scope>): <kısa özet başlık>

- <yapılan teknik değişiklik 1>
- <yapılan teknik değişiklik 2>
```

### Tipler ve Kapsamlar
- `fix`: Hata ve güvenlik açığı düzeltmeleri
- `test`: Test ekleme, düzenleme veya budama
- `feat`: Yeni özellik veya launcher geliştirmesi
- `docs`: Dokümantasyon ve metin güncellemeleri
- `ci`: GitHub Actions / CI iş akışı güncellemeleri
