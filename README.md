# Visual Engine 2 — Isolated Prototype (branch: `visual-engine-2-prototype`)

هذا الفرع معزول بالكامل عن `main` ولا يمسّ Meko Core أو Manager إطلاقاً.
يحتوي محرك الرسم الأنيميشن الحتمي (Deterministic Visual Engine) لإنتاج فيديو
«كيف تُصنع الشوكولاتة من الصفر» (1080×1920، 30 FPS، ~60 ثانية، عربي RTL).

> **سجل الاستعادة (Recovery Note)** — الكوميت المحلي الأصلي `8dcc9f4`
> ضاع مع إعادة تدوير بيئة العمل قبل رفعه إلى GitHub. أُعيد بناء هذا الفرع
> من لقطة المصدر الناجية `download/ve2-engine-source/` (11 ملفاً، حالة
> Phase 1.1 / v2). نتيجة الفحص البصري للفيديو الناتج `ve2-phase1-fixed-v2.mp4`
> موثقة في تقرير التحقق داخل مشروع العمل.

## البنية

| المسار | الغرض |
| --- | --- |
| `prototype/` | نسخة العمل القابلة للتشغيل (11 ملفاً، بنية مسطحة) |
| `prototype-sources/phase1-v2/` | نسخة احتياطية دائمة مطابقة للنسخة العاملة |

الملفات: `scene.html`، `timeline.js`، `engine-world.js`، `engine-captions.js`،
`engine-anim.js`، `render_frames.py`، `encode_chunks.py`، `build_timeline.py`،
`smoke.py`، وخط `Tajawal` (Regular/Bold — أساسي لعربية RTL).

## التشغيل

```bash
cd prototype/
python smoke.py            # فحص سريع للمشهد
python render_frames.py    # ينتج frames/*.png (Puppeteer + Chromium)
python encode_chunks.py    # يدمج عبر FFmpeg -> output/ve2-phase1-fixed-v2.mp4
```

- `scene.html` يحمّل السكربتات الأربعة من نفس المجلد (بنية مسطحة إلزامية).
- الخطوط تُحمّل محلياً من `Tajawal-*.ttf` عبر `@font-face`.

## قواعد السلامة

- كل التعديلات تتم حصرياً على هذا الفرع.
- لا تُرفع أبداً: `.env`، ملفات `*.mp4`، مجلدات المخرجات، أي مفاتيح
  أو credentials — فقط الكود المصدري وخطوط Tajawal.
