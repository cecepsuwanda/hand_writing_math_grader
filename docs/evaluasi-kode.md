# Evaluasi Kode `app/` (Handwriting Math Grader)

Dokumen ini memuat hasil audit dan evaluasi menyeluruh terhadap seluruh kode sumber di direktori [`app/`](file:///c:/Matakuliah/hand_writing_math_grader/app).

> **Status (2 Okt 2026): semua temuan di bagian 2 sudah diperbaiki.** `python -m pyflakes app` bersih, dan `python -m mypy app --ignore-missing-imports` melaporkan `Success: no issues found`. Mypy juga sempat melaporkan error ke-9 yang tidak tercantum di bawah, yaitu stub `yaml` yang hilang di `app/config/__init__.py`; ini diatasi dengan menambah `types-PyYAML` ke `requirements.txt`.
>
> Review lanjutan juga menemukan dan memperbaiki tiga masalah perilaku yang tidak terdeteksi alat statis:
> - Path override (`--output`, `--pages-dir`, `--recognition-dir`, `--questions-dir`) di luar folder run tidak lagi dikosongkan. Kalau folder itu sudah berisi file, run ditolak dengan `UnsafeOutputDirError`.
> - `recognition/` dan `questions/` lama baru diganti setelah pengenalan tulisan berhasil (job *Transkripsi lalu review* / *Transkripsi + nilai langsung*).
> - `config.yaml` atau env Ollama yang tidak valid kini memunculkan `ConfigInvalidError` (exit 1), bukan exit 2.
>
> Audit penilaian (bagian 5) menemukan tujuh bug yang membuat nilai salah; semuanya sudah diperbaiki.
>
> **Catatan (8 Okt 2026):** CLI (`app/cli.py`, `app/commands/`, `app/views/`, `MenuController`) sudah dihapus dan diganti web UI (`app/web/`). Rujukan ke file-file itu dan ke "ringkasan CLI" di bawah bersifat historis; ringkasan skor kini tampil di halaman hasil (`/runs/<run>/results`).
>
> Test suite kini 726 tes, semua lulus (6 Okt 2026).

---

## 1. Ringkasan Eksekutif

| Indikator | Hasil | Catatan |
|---|---|---|
| **Test Suite** | **726 Passed (100%)** | Berjalan dalam ~22 detik tanpa kegagalan fungsional. |
| **Arsitektur & Pola Desain** | **Sangat Baik** | MVC, SOLID, Clean Code, dan pemisahan OOP + Functional Programming terpenuhi dengan konsisten. |
| **Penanganan Error** | **Sangat Baik** | Domain exceptions di [`app/exceptions.py`](file:///c:/Matakuliah/hand_writing_math_grader/app/exceptions.py), pemetaan exit code (1 = domain, 2 = unexpected), penanganan stream terminal Windows aman dari encoding crash. |
| **Audit Kualitas Statis** | **Perlu Perbaikan Minor** | Ditemukan **2 peringatan sintaks f-string** dan **8 poin inkompatibilitas tipe data (Mypy)** di 9 file. |

---

## 2. Temuan yang Perlu Diperbaiki

Meskipun seluruh pengujian fungsional lulus, analisis statis menggunakan **Pyflakes** dan **Mypy** menemukan beberapa inkonsistensi tipe dan sintaks yang berpotensi menimbulkan bug saat refactoring atau pemeliharaan berkala:

### A. Peringatan Sintaks F-String Tanpa Placeholder (Pyflakes)

Terdapat ekspresi regex yang menggunakan awalan `rf"..."` padahal tidak memiliki ekspresi interpolasi `{}`:

1. **[`app/functions/interval_normalize.py:61-63`](file:///c:/Matakuliah/hand_writing_math_grader/app/functions/interval_normalize.py#L61-L63)**
   ```python
   # Saat ini:
   _INTERVAL_PIECE_RE = re.compile(
       rf"(?P<left>[\[(])\s*(?P<a>[^,]+?)\s*,\s*(?P<b>[^)\]]+?)\s*(?P<right>[\])])"
   )
   ```
   *Rekomendasi:* Ganti awalan `rf` menjadi raw string biasa `r"..."`.

2. **[`app/functions/number_line.py:30-32`](file:///c:/Matakuliah/hand_writing_math_grader/app/functions/number_line.py#L30-L32)**
   ```python
   # Saat ini:
   _INTERVAL_PIECE_RE = re.compile(
       rf"(?P<left>[\[(])\s*(?P<a>[^,]+?)\s*,\s*(?P<b>[^)\]]+?)\s*(?P<right>[\])])"
   )
   ```
   *Rekomendasi:* Ganti awalan `rf` menjadi raw string biasa `r"..."`.

---

### B. Inkompatibilitas Tipe & Peringatan Mypy

#### 1. Mismatch Return Type Signature
* **Lokasi:** [`app/services/grading/standard_comparer.py:273-306`](file:///c:/Matakuliah/hand_writing_math_grader/app/services/grading/standard_comparer.py#L273-L306)
* **Masalah:** Fungsi `compare_milestones` dideklarasikan mengembalikan `dict[str, tuple[ValidationStatus, str]]`, namun pada implementasinya mengembalikan dictionary berisi tuple 3 elemen `(ValidationStatus, str, float | None)` (nilai fraksi skor milestone).
* **Solusi:**
  ```python
  def compare_milestones(
      self,
      question: Question,
  ) -> dict[str, tuple[ValidationStatus, str, float | None]]:
  ```

#### 2. Shadowing Variabel dan Penugasan Tipe Inkompatibel
* **Lokasi:** [`app/functions/score_aggregate.py:160-245`](file:///c:/Matakuliah/hand_writing_math_grader/app/functions/score_aggregate.py#L160-L245)
* **Masalah:**
  * Di baris 168, variabel `fraction` terinferensi sebagai `float`. Di baris 206, `fraction: float | None = None` dideklarasikan ulang di scope fungsi yang sama.
  * Di baris 162, `consistency_fraction` terinferensi sebagai `float`. Di baris 237, di-assign nilai `None` tanpa anotasi tipe opsional.
* **Solusi:**
  * Berikan anotasi tipe eksplisit pada awal pemakaian: `consistency_fraction: float | None = None`.
  * Gunakan nama variabel terpisah untuk level part, misalnya `part_fraction: float | None = None`.

#### 3. Konflik Variabel Loop di Scope Fungsi
* **Lokasi:** [`app/functions/question_merge.py:140-188`](file:///c:/Matakuliah/hand_writing_math_grader/app/functions/question_merge.py#L140-L188)
* **Masalah:**
  * Di baris 140: `for step in sorted(recognized.steps)` (`step` bertipe `RecognizedStep`).
  * Di baris 175 dan 186: variabel `step` dipakai ulang untuk `for step in reversed(student_steps)` (`step` bertipe `StudentStep`).
  * Mypy mendeteksi penugasan tipe `StudentStep` ke variabel yang telah terikat sebagai `RecognizedStep`.
* **Solusi:** Ganti nama variabel pada iterasi kedua dan ketiga, misalnya:
  ```python
  for s_step in reversed(student_steps):
  ...
  for index, s_step in enumerate(student_steps, start=1):
  ```

#### 4. Penanganan Argumen `int()` pada Nilai Nullable
* **Lokasi:** [`app/functions/regions_artifact.py:129`](file:///c:/Matakuliah/hand_writing_math_grader/app/functions/regions_artifact.py#L129)
* **Masalah:** `order=int(item.get("order") if item.get("order") is not None else index)` menyebabkan type checker mendeteksi kemungkinan argumen bernilai tidak kompatibel (`Any | int | None`).
* **Solusi:**
  ```python
  order_raw = item.get("order")
  order = int(order_raw) if order_raw is not None else index
  ```

#### 5. Iterasi Objek PyMuPDF Document
* **Lokasi:** [`app/services/pdf/renderer.py:64`](file:///c:/Matakuliah/hand_writing_math_grader/app/services/pdf/renderer.py#L64)
* **Masalah:** `for index, page in enumerate(document):` menghasilkan error tipe karena stubs PyMuPDF tidak mengekspos iterator generik secara lengkap.
* **Solusi:** Gunakan indeks halaman yang didukung resmi oleh PyMuPDF:
  ```python
  for index in range(document.page_count):
      page = document[index]
  ```

#### 6. Penyempitan Tipe Relational SymPy
* **Lokasi:** [`app/services/math/equivalence.py:95 & 143-146`](file:///c:/Matakuliah/hand_writing_math_grader/app/services/math/equivalence.py#L95-L148)
* **Masalah:** `_REL_MIRROR: dict[type, type]` menyebabkan Mypy memperlakukan nilai cermin sebagai `type` umum, sehingga setelah `isinstance(current, mirror)`, tipe `current` menyempit menjadi `object` dan kehilangan atribut `.lhs` dan `.rhs`.
* **Solusi:** Anotasikan kamus secara spesifik:
  ```python
  _REL_MIRROR: dict[type[Relational], type[Relational]] = { ... }
  ```

#### 7. Outdated Ignore Comment pada Step Coercion
* **Lokasi:** [`app/services/vision/recognizer.py:72`](file:///c:/Matakuliah/hand_writing_math_grader/app/services/vision/recognizer.py#L72)
* **Masalah:** `number = int(value)  # type: ignore[arg-type]` memicu peringatan karena error kode Mypy terbaru adalah `call-overload`.
* **Solusi:** Hilangkan `# type: ignore` dan gunakan pengecekan runtime yang aman:
  ```python
  if isinstance(value, (int, str, float)):
      try:
          number = int(value)
      except ValueError:
          return fallback
  else:
      return fallback
  ```

#### 8. Kontrak Parameter `prompt_choice`
* **Lokasi:** [`app/functions/paths.py:61-109`](file:///c:/Matakuliah/hand_writing_math_grader/app/functions/paths.py#L61-L109) dan [`app/commands/flows.py:136, 151, 166`](file:///c:/Matakuliah/hand_writing_math_grader/app/commands/flows.py#L136)
* **Masalah:** `prompt_choice` di [`app/views/prompt_view.py`](file:///c:/Matakuliah/hand_writing_math_grader/app/views/prompt_view.py) mengharapkan parameter parser berkarakteristik:
  `parse: Callable[[Sequence[Item], str], T]`.
  Namun `parse_path_choice`, `parse_pdf_choice`, `parse_kunci_choice`, dan `parse_run_choice` di `paths.py` dianotasikan hanya menerima `list[Path]`. Sesuai aturan kontravariansi fungsi di Python, fungsi yang hanya menerima list tidak bisa disubstitusikan ke tempat yang mengekspektasikan sequence umum.
* **Solusi:** Ubah anotasi parameter pada fungsi-fungsi tersebut di `paths.py` menjadi `Sequence[Path]`.

---

## 3. Evaluasi Kepatuhan Arsitektur

### MVC (Model - View - Controller)
* **View:** Seluruh interaksi pengguna terkonsolidasi di [`app/views/`](file:///c:/Matakuliah/hand_writing_math_grader/app/views). Tidak ada view yang melakukan kalkulasi matematika atau memanggil service langsung.
* **Controller:** Berfungsi murni sebagai orkestrator use-case. Exception domain ditangkap dan diteruskan ke view atau mapped ke kode keluar.
* **Model & Domain Services:** Terisolasi dengan baik. Model Pydantic menjamin integritas data artefak sebelum dan sesudah tahap pemrosesan.

### SOLID & Clean Architecture
* **Single Responsibility (S):** Setiap fungsi di [`app/functions/`](file:///c:/Matakuliah/hand_writing_math_grader/app/functions) berukuran kecil dan berfokus pada satu operasi deterministik.
* **Open/Closed (O):** Penambahan bab/topik matematika baru dilakukan melalui Topic Pack di [`app/topics/`](file:///c:/Matakuliah/hand_writing_math_grader/app/topics) tanpa perlu memodifikasi inti pipeline evaluasi.
* **Liskov Substitution (L) & Interface Segregation (I):** Interface sempit dan jelas didefinisikan di [`app/interfaces/`](file:///c:/Matakuliah/hand_writing_math_grader/app/interfaces) (`PdfRenderer`, `VisionRecognizer`, `StepValidator`, `LlmClient`, dll.).
* **Dependency Inversion (D):** Seluruh ketergantungan dikomposisikan melalui Dependency Injection terpusat di [`app/services/pipeline_factory.py`](file:///c:/Matakuliah/hand_writing_math_grader/app/services/pipeline_factory.py).

### Robustness & Platform Compatibility
* **Encoding Console Windows:** Penggunaan `configure_console_streams(errors="replace")` mencegah crash terminal akibat karakter unicode / border box pada sistem non-UTF-8.
* **Subprocess Isolation:** Hanya satu titik subprocess dalam seluruh aplikasi, yaitu pada kompilasi PDF LaTeX di [`app/services/latex/pdflatex_compiler.py`](file:///c:/Matakuliah/hand_writing_math_grader/app/services/latex/pdflatex_compiler.py), dengan timeout dan penanganan pembersihan file log/junk yang sangat rapi.

---

## 4. Kesimpulan

Secara fungsional dan arsitektural, sistem ini berada dalam kondisi **sangat prima** (seluruh 726 pengujian otomatis lulus). Perbaikan yang diidentifikasi di atas murni bersifat **peningkatan kualitas statis (static type hygiene)** dan **standarisasi sintaks** agar kode 100% bebas dari peringatan linter dan type checker.

---

## 5. Bug yang Mempengaruhi Penilaian (sudah diperbaiki)

| Bug | Dampak sebelum perbaikan | Perbaikan |
|---|---|---|
| Salin soal / berhenti di tengah | Jawaban yang hanya menyalin soal mendapat sekitar 6/10 AUTO_ACCEPT, karena langkah 1 VALID asal ter-parse dan jawaban akhir hanya dibandingkan himpunan penyelesaiannya. | `is_solved_form` di `equivalence.py`. `StandardFinalComparer.compare` memberi UNCERTAIN bila jawaban akhir belum berbentuk selesai atau mengulang soal. `compare_first_step` memberi UNCERTAIN bila langkah 1 tidak setara dengan soal; `aggregate_question_grade(step_overrides=...)` hanya bisa menurunkan VALID menjadi UNCERTAIN. Hasilnya REVIEW_REQUIRED. |
| Soal tidak dijawab | Soal tanpa `grading.json` hilang dari nilai maksimum (20/30 dilaporkan 20/20). | `ReportController` menerima `exam_schema` + `RubricLoader`; `aggregate_exam_report(expected_maximums=...)` menambah baris skor 0, `missing=True`, REVIEW_REQUIRED. Ditampilkan "TIDAK DIJAWAB" di HTML, LaTeX, dan ringkasan CLI. |
| Simbol selalu `x` | Soal dengan variabel `t`/`y` semua langkahnya VALID, jawaban interval INVALID. | `infer_main_symbol` (variabel tertulis terbanyak, seri memilih `x`) dan `rebind_default_symbol` (interval polos yang di-normalize dengan `x`) dipakai validator dan comparer per soal. |
| Implikasi menjadi "and" | `x^2<4 ⇒ x<2` dinilai VALID. | Symbolic menyimpan implikasi sebagai ` => ` (`normalize_math_text(keep_implication=True)`, prompt `crop-math-v10`). Validator memeriksa tiap klausa berantai (`split_implication_clauses`); status terburuk dipakai. |
| Split schema salah memindahkan langkah | `2x-1<5` (stem soal lain) cocok dengan langkah `2x-1<5x+2`; jawaban akhir dan gambar disalin ke semua bagian. | Kecocokan substring stem harus berbatas. Jawaban akhir hasil recognition hanya ke bagian yang memuatnya; `figure_refs` hanya ke bagian yang `expects_figure` (jika ambigu, ke nomor asal). |
| LaTeX terhapus saat rebuild | `_strip_prose` menghapus `\leq`, `\geq`, `\infty`, `\cup`; `\leqslant` menjadi `<=slant`. | Perintah LaTeX (diawali `\`) dipertahankan; regex relasi memakai batas huruf dan memetakan `\leqslant`/`\geqslant`. |
| Jawaban akhir campur crop | Teks jawaban akhir dari satu crop, simbolik dari crop lain. | `question_merge` mengambil keduanya berpasangan dari crop yang sama. |

Artefak `recognition/`/`question.json` lama yang sudah berisi implikasi bergabung `and` perlu di-recognize ulang agar mendapat format ` => `.

### Perbaikan lanjutan (tahap 1 + 2)

| Bug | Dampak sebelum perbaikan | Perbaikan |
|---|---|---|
| Confidence LLM diabaikan | Putusan LLM dengan confidence 0.3 dipakai sama seperti putusan yakin; langkah VALID/INVALID tanpa review. | `HybridStepValidator(min_confidence=...)` dari `grading.llm_min_confidence` (default 0.7). VALID/INVALID di bawah ambang atau tanpa confidence menjadi UNCERTAIN, untuk langkah dan jawaban akhir. |
| Poin algebra dobel | Pool algebra dibagi ke semua langkah, termasuk langkah titik kritis, tanda, gambar, dan HP yang sudah dinilai di bagian rubric lain. | `TopicPack.role_rubric_parts`; `aggregate_question_grade(step_roles=..., role_rubric_parts=...)` memberi max 0 untuk langkah yang role-nya dinilai di bagian rubric yang ada. Rubric lama tanpa bagian tersebut tidak berubah. |
| Gambar VALID asal ada | Gambar apa pun mendapat poin penuh bila kunci tidak punya garis bilangan atau comparer tidak dipakai. | `compare_figure` dan cabang tanpa comparer di `StepGrader` memberi UNCERTAIN ("figure present; no key number line to compare"). |
| Rubric hilang menghentikan grade | Satu file rubric hilang membuat seluruh tahap grade gagal; `grading.json` lama tetap terbaca di report. | `GradeController` melewati soal itu dengan peringatan, menghapus `grading.json` lamanya, dan mencatat `GradeResult.skipped`. `ReportController(default_rubric=pack.rubric_from_parts)` memberi nilai maksimum cadangan; `QuestionReportRow.missing_label` membedakan "TIDAK DINILAI" dari "TIDAK DIJAWAB" di HTML, LaTeX, dan CLI. |
| Titik kritis digabung | `x = 0 or x = 1` tidak cocok dengan atom kunci `x = 0`, `x = 1`; titik ekstra yang salah tidak mengurangi nilai. | `_point_set_match`: bila semua atom milestone berupa titik berhingga, kunci dan jawaban dibandingkan sebagai himpunan; fraksi = titik cocok / (titik kunci + titik ekstra), VALID hanya bila sama persis. |
| Atom tak terputuskan | Atom kunci yang tidak bisa diputuskan dihitung seperti salah, tanpa review. | `_milestone_match` memberi UNCERTAIN dengan `fraction = (matched + 0.5·undecided) / total`. |
| `validation.json` usang | `question.json` yang diedit setelah `validate` tetap dinilai dengan validasi lama. | `question_fingerprint` disimpan di `validation.json`; `StepGrader` melempar `ValidationStaleError` bila berbeda. File lama tanpa fingerprint tetap diterima. |
| Total rubric tidak dicek | Rubric 9/10 diterima dan skor maksimum tidak tercapai. | Validator di model `Rubric`; `RubricLoader` melempar `RubricInvalidError` (subkelas `RubricNotFoundError`, jadi ikut dilewati dengan peringatan). |

### Perbaikan lanjutan (tahap 3)

| Bug | Dampak sebelum perbaikan | Perbaikan |
|---|---|---|
| Escape JSON memakan LaTeX | `\boxed{...}`, `\tfrac`, `\neg`, `\tau`, `\rfloor` dibaca sebagai escape JSON (`\b`, `\t`, `\n`, `\r`); symbolic rusak dan langkah jatuh ke UNCERTAIN. | `repair_json_escapes`: daftar `_LATEX_JSON_COLLISIONS` diperluas, dan perintah multi-huruf yang langsung diikuti `{` selalu dianggap LaTeX. |
| Bentuk faktor gagal di-parse | `(x-1)(x+2) < 0` ditolak sebagai "interval"; `(x-1)(x) = 0` terbaca sebagai definisi fungsi. | Hanya tuple berkoma yang ditolak; faktor bersebelahan menjadi perkalian. `_FUNC_ASSIGN_RE` hanya menerima gabungan fungsi `(f+g)(x)`. |
| Langkah HP menjadi gambar | "HP = (1, ∞) (lihat garis bilangan)" diberi role `figure`, sehingga langkah HP tidak dinilai di bagian HP. | `coalesce_step_role`: figure pasti (`kind="figure"` / `NUMBER_LINE(`) > HP kuat > kata kunci gambar, kecuali bila role model `hp` atau isinya interval murni. |
| Uji tanda menerima pernyataan apa pun | `2 > 1` pada langkah `sign_chart` dinilai VALID karena benar secara numerik. | `numeric_eval_matches_reference`: sisi yang ditulis harus sama dengan ekspresi reference di salah satu angka yang ditulis siswa (`parse_relation_sides` membaca sisi tanpa evaluasi). Benar tapi tidak terkait menjadi UNCERTAIN, lalu dinilai LLM dengan `Check kind: numeric_eval`. |
| Nomor sementara bertabrakan | Crop tanpa nomor diberi `max(nomor terbaca)+1`; bila siswa melewati soal 3, crop itu dinilai dengan kunci soal 3. | `merge_page_recognitions`/`collect_latex_documents(reserved_numbers=...)` memakai nomor kunci; nomor sementara dimulai setelah nomor kunci terbesar. `ReportController` memberi peringatan untuk folder di luar kunci dan tidak menambahkannya ke nilai maksimum. |
| Label crop gagal diam-diam | Balasan vision yang tidak terbaca diperlakukan sama dengan "tidak ada label"; crop ikut soal sebelumnya tanpa pemberitahuan. | `QuestionLabeler.detect -> list[int] \| None`; `QuestionCropsReport.unreadable_crops` dan peringatan "label tidak terbaca (ikut soal sebelumnya)". |

### Perbaikan lanjutan (tahap 4)

| Bug | Dampak sebelum perbaikan | Perbaikan |
|---|---|---|
| Crop tanpa nomor yang menyalin stem tidak dinilai | Siswa melewati nomor 3 lalu menulis jawaban soal 3 tanpa nomor; crop mendapat nomor sementara dan keluar dari penilaian. | `assign_provisional_by_stem` (dipanggil `QuestionExtractor` sebelum split): soal sementara yang langkah pertamanya cocok dengan stem soal N diberi nomor N bila N belum terbaca dan belum diambil crop sementara lain. Status tetap `provisional`, dan extractor mencatat peringatan. |
| Fallback titik kritis menghukum aljabar | Tanpa langkah ber-role `critical_points`, persamaan aljabar seperti `x = 3` dihitung sebagai titik ekstra dan mengurangi nilai bagian titik kritis. | `_point_set_match`: titik ekstra hanya dihitung dari langkah ber-role; pada fallback fraksi = titik cocok / titik kunci, dengan alasan bertanda "(untagged steps)". |
| Poin algebra dobel tanpa langkah aljabar | Bila semua langkah dinilai di bagian rubric, pool algebra tetap dibagi ke langkah yang sama. | `allocate_step_max_scores` memindahkan pool ke bagian `algebra`; `aggregate_question_grade` menilainya UNCERTAIN (setengah poin, REVIEW_REQUIRED). |

### Perbaikan lanjutan (tahap 5)

| Bug | Dampak sebelum perbaikan | Perbaikan |
|---|---|---|
| Desimal ≠ pecahan | Di SymPy 1.13+, `Float(0.5) != Rational(1, 2)`, sehingga `x < 0.5` dinilai berbeda dari `x < 1/2`, baik di langkah, jawaban akhir, maupun ujung garis bilangan. | Transformasi `rationalize` di `parse_expr` (`parser.py` dan `number_line.py`). `rewrite_decimal_commas` mengubah koma desimal (`0{,}5`, dan `0,5` di luar kurung) menjadi titik. |
| Akar berindeks | `x_1 = 1 or x_2 = -2` membaca `x_1` dan `x_2` sebagai simbol lain, sehingga titik kritis tidak pernah cocok. | Capability `indexed_roots` (hanya di pack 1.5 dan 2) mengubah `x_1`, `x_{1}`, dan `x₁` menjadi `x`. `x1` tanpa garis bawah tidak diubah. |
| Uji tanda berbentuk implikasi | `x = 0 => f(0) < 0` dianggap ekuivalensi, sehingga substitusi titik dinilai INVALID. | `_validate_chained_step`: pada `numeric_eval`, rantai dari premis ke klaim tertutup (tanpa simbol bebas) tidak dicek sebagai ekuivalensi. |
| Role tidak kanonik | Role `"HP"` atau `" Critical_Points "` hasil edit tangan atau model ditolak, atau tidak cocok saat menilai per bagian. | `OptionalStepRole` (`BeforeValidator`) di `RecognizedStep` dan `StudentStep` mengubah role ke huruf kecil dan membuang spasi. |
| Notasi Unicode dan bahasa Indonesia | `≤ ≥ ≠ ∞ − × ·`, `\text{...}`, `\quad`, serta kata `atau`/`dan` gagal di-parse. | Penggantian tambahan di `_LATEX_REPLACEMENTS` (`math_normalize.py`). |
| Rantai dengan `=` | `f(-5) = 15/7 > 0` ditolak parser karena `_COMPOUND_RE` hanya mengenal `<`/`>`. | `_try_parse_chain`: rantai dengan tiga sisi atau lebih yang memuat `=` dibaca sebagai `And` dari relasi berpasangan. |
| HP himpunan | `HP = \emptyset`, `x \in \mathbb{R}`, `HP = R`, dan `\{x \mid x < 3\}` tidak terbaca. | Token `EmptySet`/`Reals` dan `rewrite_set_builder` di `interval_normalize.py`; parser memetakannya ke `S.EmptySet`/`S.Reals`, dan `expression_as_set` menerimanya sebagai himpunan solusi. |
| `y = ...` selalu fungsi | `y = 2 or y = 3` gagal di-parse; `y = 3` dibaca sebagai fungsi konstan, bukan akar; `f(0) = -1/2 < 0` gagal. | `_try_parse_assignment`: assignment hanya menjadi ekspresi bila RHS berupa ekspresi dan, untuk `y`, memuat simbol selain `y`. Selain itu dibaca sebagai relasi; `f(0)` menjadi nilai tak diketahui (`_opaque_assignment_lhs`), bukan `f*0`, sehingga uji tanda ini menjadi UNCERTAIN, bukan INVALID. |
