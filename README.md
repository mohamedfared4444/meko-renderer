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

## Phase 5 — مواصفة المنتج المعتمدة بالبيانات (Step 1)

منذ Phase 5 Step 1 أصبح المنتج موصوفًا في ملف spec واحد
(`tools/products/*.json`) يُدقَّق مقابل JSON Schema، وتقرأ منه أدوات
البناء نصوص السرد والمشاهد وسياسة الصوت — لا يوجد أي نص منتج داخل الكود.

| المسار | الغرض |
| --- | --- |
| `tools/products/chocolate.json` | البريسِت المعتمد (الشوكولاتة) مع خط أساس الانحدار (frozen md5s) |
| `tools/products/coffee.json` / `soap.json` | منتجان نموذجيان (عربي مصري) |
| `tools/schemas/ve2-product-spec.schema.json` | JSON Schema للتنسيق |
| `tools/ve2_product_spec.py` | اللودر/المدقق + اشتقاق سياسة الصوت + `check-chocolate` |

```bash
python3 tools/ve2_product_spec.py validate tools/products/coffee.json
python3 tools/ve2_product_spec.py check-chocolate   # حارس انحدار البناء المعتمد
python3 tools/ve2_build_audio_phase4.py --spec tools/products/<id>.json
```

التفاصيل الكاملة وإثبات عدم الانحدار (md5s طابقة بايت-ببايت) في
`tools/products/README.md`.
