# VE2 Product Specs — تنسيق مواصفة المنتج (Phase 5 Step 1)

ملف مواصفة واحد = منتج كامل: المشاهد، السرد، سياسة الصوت، الأصول، والمخرجات.
لا يوجد أي نص منتج أو اسم مشهد داخل كود المحرك — كل شيء يقرأ من الـ spec.

A product spec is a single JSON file that fully describes ONE product video.
The engine (audio build, TTS generator, timeline builder) reads it — nothing
about a product is hardcoded in code any more.

## الملفات

| الملف | الغرض |
| --- | --- |
| `chocolate.json` | البريسِت المعتمد (فrozen baseline) — الشوكولاتة، مخرجات Phase-4.4 المعتمدة مع md5s |
| `coffee.json` | منتج نموذجي جديد (قهوة) — عربي مصري، نفس القالب السباعي |
| `soap.json` | منتج نموذجي جديد (صابون) — عربي مصري، بدون caption groups |
| `fridge.json` | منتج نموذجي جديد (ثلاجة) — عربي مصري، نفس القالب السباعي؛ مترجم من `fridge.raw.json` (طلب العميل الخام، محفوظ حرفيًا) — غير مدفوع TTS، جاهز للبناء المعزول |
| `fridge.raw.json` | الطلب الخام للعميل كما وصل حرفيًا — مرجع فقط، لا يقرأه المدقق ولا أي Automation |
| `../schemas/ve2-product-spec.schema.json` | JSON Schema (draft 2020-12) للتنسيق |
| `../ve2_product_spec.py` | اللودر/المدقّق + اشتقاق سياسة الصوت + فحص الانحدار |

## بنية الـ spec (الملخص)

- `product` — الهوية: `id`, `title_ar`, `pill_ar`, `title_en`, `language`
- `voice` — مزوّد TTS: `model`, `name`, `directive`
- `video` — الكانفس: `width/height/fps/frames/duration_s`
- `scenes[]` — `id` (scene1..N), `num`, `label`, `start/end` (نوافذ مقطعة متلاصقة)
- `narration[]` — `id` (seg1..N), `scene` (ربط القالب), `text` (نص TTS حرفي),
  `caption_groups` (اختياري — إيقاع كابشن صريح، مثلاً كارت النهاية)
- `audio_policy` — `lead_s`, `gap_seg1_seg2_s`, `anchors_s`, `post_cut_offset_s`,
  `pause_keep_s`, `min_precut_buffer_s`, `min_postcut_resume_s`
- `banners[]` — شرائح المشاهد على الشاشة (`num`, `label_ar`, `t0/t1`) — تُقرأ في
  المحرك من Phase 5 step 2 (stage chips)
- `end_card` — كارت النهاية (`line1_ar`, `line2_ar`, `sub1_ar`, `sub2_ar`)
- `world` — لفافات الآلات داخل المشهد (`layer_banners[]` = `key` + `label_ar`)؛
  المواضع تظل في هندسة القالب بالمحرك، والنصوص من الـ spec
- `assets` — مجلد الـ TTS الناتج + `segments_report` + نمط ملفات الفلاك
- `outputs` — مسارات `ve2-audio-timeline.json` و `timeline.js`
- `frozen` (اختياري) — خط أساس الانحدار للبناء المعتمد: placements/ends_at + md5s

عقد القالب الحالي (Phase 5 step 1): 7 مشاهد × 7 مقاطع سرد؛
`seg1,seg2 → scene1` وكل `segN (N≥3) → scene(N-1)`؛ لازم anchor لـ `seg5`
وموضع ما-بعد-القطع لـ `seg7`. (تعميم عدد المشاهد/المقاطع خطوة لاحقة في Phase 5.)

## إضافة منتج جديد — الخطوات

1. **اكتب الـ spec**: انسخ `coffee.json` كبداية وعدّل: `product`, نصوص السرد
   السبعة (عامية مصرية بدون تشكيل فصحى)، نوافذ المشاهد، `audio_policy`،
   `banners`، و `assets.narration_dir` (مجلد جديد لكل منتج).
2. **دقّق**: `python3 tools/ve2_product_spec.py validate tools/products/<id>.json`
   — يفحص الـ schema + العقد القالبية (نوافذ متلاصقة، frames = duration×fps،
   ربط المقاطع بالمشاهد، الـ anchor داخل scene4، النص عربي فعلًا...).
3. **ولّد السرد** (TTS مدفوع — فقط عند الجاهزية):
   `VE2_PRODUCT_SPEC=tools/products/<id>.json VE2_VOICE_OUT=visual-engine-2/download/ve2-narration-<id> python3 tools/gemini_tts_segments.py`
4. **ابنِ الصوت + التايم لاين**:
   `python3 tools/ve2_build_audio_phase4.py --spec tools/products/<id>.json`
   — يقرأ فلاكات المنتج من `assets`، يطبّق سياسة الصوت من الـ spec، يكتب
   `ve2-audio-timeline.json` ويعيد توليد `scene/timeline.js` تلقائيًا.
5. **ولّد بيانات الرندر** (بدون أي مصاريف):
   `python3 tools/ve2_product_spec.py render-data tools/products/<id>.json --out <scene dir>`
   — يكتب `product-data.js` (`window.VE2_PRODUCT`) بجوار `scene.html`.
   المحرك يقرأ منه العنوان والـ pill والـ chips (`banners[]`) وكارت النهاية
   (`end_card`) ولفافات الآلات (`world.layer_banners`) — لا يوجد أي نص منتج
   داخل `engine-world.js`. مفتاح آلة غير معروف أو block ناقص => خطأ فوري واضح.
6. **الرندر** (محرك 2.5D الحالي): `smoke.py` → `render_frames.py` → `encode_chunks.py`
   — بيانات الـ visuals كلها الآن من الـ spec.
7. **جمّد خط الأساس**: بعد اعتماد البناء، أضف `frozen` (placements + md5s)
   إلى الـ spec ليصبح فحص الانحدار تلقائيًا.

## أوامر الفحص

```bash
python3 tools/ve2_product_spec.py validate tools/products/chocolate.json
python3 tools/ve2_product_spec.py show      tools/products/coffee.json
python3 tools/ve2_product_spec.py policy    tools/products/soap.json     # ما يستهلكه بناء الصوت حرفيًا
python3 tools/ve2_product_spec.py skeleton  tools/products/coffee.json   # هيكل التايم لاين قبل الصوت
python3 tools/ve2_product_spec.py render-data tools/products/coffee.json --out /tmp/preview   # بيانات الرندر (مجاني)
python3 tools/ve2_product_spec.py check-chocolate                        # حارس انحدار الشوكولاتة
```

## إثبات عدم الانحدار (Phase 5 step 1)

بناء معزول بالـ spec (افتراضيًا chocolate) أعاد إنتاج البناء المعتمد
بايت-ببايت على كل المخرجات الأربعة:

| المخرج | md5 |
| --- | --- |
| `ve2-audio-timeline.json` | `46df7fe817e08aa30a093b113acfa9e1` |
| `narration_mix_phase4.m4a` | `785989aaf9982571039764d183a2606c` |
| `ve2-phase4-audio-verify.json` | `994bd9c433c74e8393527960f68da9ef` |
| `scene/timeline.js` | `275e319aa254052287528f995d7a0e74` |

فيديو Phase-4.4 (1819 إطار / 60.633s / 1080×1920@30) لم يُلمس إطلاقًا.

## إثبات عدم الانحدار البصري (Phase 5 step 2 — ربط الـ banners بالـ spec)

نصوص المنتج في `engine-world.js` (العنوان، الـ pill، الـ chips `banners[]`،
كارت النهاية `end_card`، لفافات الآلات `world.layer_banners`) صارت تُقرأ من
`scene/product-data.js` المولّد من الـ spec — ولا يوجد أي نص منتج في الكود.

- A/B بعشرة لقطات (t=1.0→59.0) بين المحرك القديم (نصوص مضمّنة) والمحرك
  الجديد (spec-driven، chocolate): **10/10 متطابقة بايت-ببايت**.
- `render_frames.py --verify`: PASS (كل الفحوصات + caption sweep).
- `render_frames.py --determinism`: PASS (نفس البايتات عند t=25/40/59).
- ملفات الـ frozen الأربعة (timeline JSON/mix/verify/timeline.js) لم تتغير.
- ملاحظة: `VE2_SCENE_URL` (اختياري) في `render_frames.py` يشغّل الرندر على
  مجلد scene معزول — الافتراضي بلا تغيير.

## متغيرات البيئة (اختيارية — الافتراضات بلا تغيير)

- `VE2_PRODUCT_SPEC` — مسار spec بديل (لـ `gemini_tts_segments.py`؛
  ولـ `ve2_build_audio_phase4.py` استخدم `--spec`)
- `VE2_ROOT` / `VE2_DL` — تشغيل البناء على sandbox معزول للتحقق البايتي
