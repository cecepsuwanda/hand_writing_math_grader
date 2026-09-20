# Plan Pengembangan: Automated Handwritten Mathematics Grading

## 1. Tujuan

Membangun **aplikasi CLI Python** yang menerima PDF berisi lembar jawaban matematika tulisan tangan mahasiswa, kemudian:

1. Mengubah PDF menjadi gambar per halaman.
2. Menggunakan Vision LLM melalui Ollama untuk mengenali tulisan tangan dan struktur jawaban.
3. Mengelompokkan tulisan menjadi soal dan langkah-langkah penyelesaian.
4. Mengonversi setiap langkah matematika menjadi LaTeX.
5. Menyimpan hasil recognition dan LaTeX per soal.
6. Memeriksa validitas setiap langkah penyelesaian.
7. Menggunakan library matematika seperti SymPy jika pemeriksaan simbolik memungkinkan.
8. Menggunakan LLM untuk reasoning pada langkah yang tidak dapat diverifikasi hanya dengan symbolic computation.
9. Membandingkan penyelesaian mahasiswa dengan soal dan jawaban standar.
10. Memberikan grading berbasis rubric, termasuk partial credit.
11. Menghasilkan laporan yang dapat diaudit dengan menyimpan gambar asli, hasil recognition, LaTeX mahasiswa, jawaban standar, hasil validasi, alasan kesalahan, dan skor.

Bentuk aplikasi utama adalah **Command-Line Interface (CLI)**. Antarmuka web atau REST API bersifat opsional dan hanya boleh ditambahkan setelah engine CLI stabil, tanpa mengubah kontrak inti engine.

## 2. Prinsip Desain

### 2.1 Pisahkan recognition dan grading

Jangan langsung meminta LLM memberikan nilai dari gambar.

Pipeline utama:

```text
PDF
  ↓
Image per page
  ↓
Vision recognition
  ↓
Structured JSON
  ↓
Per-question extraction
  ↓
Student LaTeX
  ↓
Mathematical validation
  ├── SymPy/CAS
  └── LLM reasoning
  ↓
Comparison with standard solution
  ↓
Rubric grading
  ↓
Report
```

### 2.2 Jangan mengubah jawaban mahasiswa ketika recognition

Tahap recognition harus berusaha menyalin apa yang benar-benar ditulis mahasiswa.

LLM tidak boleh:
- memperbaiki persamaan;
- mengoreksi typo;
- menyimpulkan langkah yang tidak tertulis;
- mengganti jawaban dengan jawaban yang dianggap benar.

Jika recognition tidak yakin, simpan confidence/flag dan pertahankan representasi gambar asli.

### 2.3 Semua keputusan grading harus dapat diaudit

Untuk setiap skor simpan:
- soal;
- jawaban standar;
- langkah mahasiswa;
- status setiap langkah;
- hasil SymPy jika ada;
- keputusan LLM;
- alasan;
- skor langkah;
- skor total;
- confidence;
- image/page reference.

### 2.4 Bentuk aplikasi, arsitektur, dan gaya kode

Aplikasi harus memenuhi ketentuan berikut:

1. **CLI Python sebagai entry point utama**
   - Pengguna menjalankan grading melalui perintah terminal (`python -m app.cli ...`).
   - Progress, status, error, dan ringkasan hasil ditampilkan di terminal.
   - Artefak detail (JSON, LaTeX, HTML, gambar) disimpan ke filesystem.

2. **Arsitektur MVC (Model–View–Controller)**
   - **Model**: domain data dan aturan bisnis (recognition, question, validation, grading, report artifacts).
   - **View**: presentasi untuk CLI (progress bar, ringkasan skor, pesan error, path output); bukan logika grading.
   - **Controller**: menerima input CLI, memanggil service/use-case, meneruskan hasil ke View, dan mengatur alur pipeline.
   - Controller tidak mengandung logika matematika atau prompt LLM secara langsung.
   - View tidak mengakses Ollama, SymPy, atau filesystem persistence secara langsung.

3. **Prinsip SOLID**
   - **S**ingle Responsibility: satu kelas/modul punya satu alasan untuk berubah.
   - **O**pen/Closed: perluasan (validator baru, reporter baru) melalui abstraksi/plugin, bukan edit besar pada inti.
   - **L**iskov Substitution: implementasi interface (mis. validator, recognizer) dapat diganti tanpa merusak pemanggil.
   - **I**nterface Segregation: interface sempit (`PdfRenderer`, `VisionRecognizer`, `StepValidator`, `GradeReporter`), bukan god-interface.
   - **D**ependency Inversion: Controller dan service bergantung pada abstraksi; detail Ollama/PyMuPDF/SymPy diinjeksi dari luar.

4. **Clean coding**
   - Nama yang bermakna; fungsi kecil dan fokus; hindari side effect tersembunyi.
   - Tidak ada magic number/string yang tersebar; konfigurasi terpusat.
   - Duplikasi dihindari; komentar hanya untuk “mengapa”, bukan narasi ulang kode.
   - Error handling eksplisit; logging terstruktur; tidak menelan exception.
   - Type hints dan schema validation (Pydantic) untuk kontrak data antar layer.

5. **Paradigma OOP dan Functional Programming secara berdampingan**
   - **OOP**: encapsulation service/client (OllamaClient, PdfRenderer, GradingPipeline), polymorphism melalui interface/ABC, state domain sebagai objek/Pydantic model.
   - **Functional**: pure function untuk transformasi data yang deterministik (equivalence check, skor agregat, mapping step → LaTeX, filter/map pipeline stages) tanpa mengubah input.
   - Prefer immutable data untuk hasil recognition/validation/grading; mutasi hanya di layer persistence atau builder yang eksplisit.
   - Hindari class “utilitas” yang hanya berisi static method; untuk operasi murni gunakan fungsi modul.
   - Composition over inheritance; inheritance hanya jika benar-benar ada hierarki perilaku.

Contoh pemisahan tanggung jawab:

```text
CLI argv
  → Controller (orchestrate)
      → Services / Use-cases (OOP + DI)
          → Pure functions (FP transforms)
          → Adapters (Ollama, PyMuPDF, SymPy, filesystem)
      ← Domain Models (immutable-ish)
  → View (CLI output)
  → Filesystem artifacts (audit trail)
```

---

# 3. Arsitektur Sistem

## 3.1 Pipeline pemrosesan

```text
                    ┌──────────────────┐
                    │ PDF Answer Sheet │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │     PyMuPDF      │
                    │ PDF → page image │
                    └────────┬─────────┘
                             │
                             ▼
                ┌──────────────────────────┐
                │ Ollama Vision Model      │
                │ handwriting recognition  │
                │ math/formula recognition │
                └────────────┬─────────────┘
                             │
                             ▼
                    recognition.json
                             │
                             ▼
                ┌──────────────────────────┐
                │ Question Segmentation    │
                │ + Step Extraction        │
                └────────────┬─────────────┘
                             │
                             ▼
                ┌──────────────────────────┐
                │ LaTeX Representation     │
                └────────────┬─────────────┘
                             │
                  ┌──────────┴───────────┐
                  ▼                      ▼
             ┌─────────┐           ┌─────────┐
             │  SymPy  │           │   LLM   │
             │  CAS    │           │ Reasoner│
             └────┬────┘           └────┬────┘
                  │                     │
                  └──────────┬──────────┘
                             ▼
                   Step Validation
                             │
                             ▼
                   Standard Solution
                             │
                             ▼
                      Rubric Grader
                             │
                             ▼
                    Final Grade Report
```

## 3.2 Lapisan MVC

```text
┌─────────────────────────────────────────────────────────────┐
│ View (CLI)                                                  │
│  - argparse / rich progress                                 │
│  - print summary, errors, output paths                      │
└────────────────────────────┬────────────────────────────────┘
                             │ user commands / display
┌────────────────────────────▼────────────────────────────────┐
│ Controller                                                  │
│  - Parse CLI args                                           │
│  - Orchestrate pipeline stages                              │
│  - Map exceptions → user-facing messages                    │
│  - Tidak berisi logika grading/math/prompt                  │
└────────────────────────────┬────────────────────────────────┘
                             │ use-case calls
┌────────────────────────────▼────────────────────────────────┐
│ Model / Domain + Services                                   │
│  - Entities & schemas (Page, Question, Grade, …)            │
│  - Use-cases (render, recognize, validate, grade, report)   │
│  - Pure functions (equivalence, score aggregate, …)         │
│  - Ports/interfaces (Recognizer, Validator, Renderer, …)    │
└────────────────────────────┬────────────────────────────────┘
                             │ adapters
┌────────────────────────────▼────────────────────────────────┐
│ Infrastructure                                              │
│  - Ollama HTTP client                                       │
│  - PyMuPDF renderer                                         │
│  - SymPy engine                                             │
│  - Filesystem I/O, logging, config                          │
└─────────────────────────────────────────────────────────────┘
```

Aturan ketergantungan: View → Controller → Model/Services → Infrastructure.
Infrastructure tidak boleh bergantung pada Controller atau View.

---

# 4. Teknologi

## Core

- Python 3.x
- CLI entry point (`python -m app.cli` atau console script)
- PyMuPDF (`fitz`)
- Ollama
- Vision-capable VLM available through Ollama
- SymPy
- Pydantic
- JSON
- LaTeX
- `abc` / Protocol untuk abstraksi SOLID
- Type hints (`typing`)

## Optional

- `rich` atau `tqdm` untuk progress CLI
- Jinja2 untuk report generation (HTML)
- SQLite untuk metadata
- pytest untuk testing
- FastAPI / Streamlit hanya setelah CLI engine stabil (bukan target MVP)

Jangan mengunci implementasi pada satu model. Model harus configurable melalui file konfigurasi.

Contoh:

```yaml
ollama:
  base_url: "http://localhost:11434"
  vision_model: "MODEL_VISION"
  reasoning_model: "MODEL_REASONING"
```

---

# 5. Struktur Repository

Gunakan struktur modular berbasis **MVC + clean architecture ringan**:

```text
math-grader/
├── app/
│   ├── __init__.py
│   ├── cli.py                      # entry point CLI
│   ├── config/                     # AppConfig + config.yaml
│   │   ├── __init__.py
│   │   └── config.yaml
│   │
│   ├── controllers/                # Controller layer
│   │   ├── __init__.py
│   │   ├── render_controller.py
│   │   ├── recognize_controller.py
│   │   ├── validate_controller.py
│   │   ├── grade_controller.py
│   │   └── process_controller.py
│   │
│   ├── views/                      # View layer (CLI presentation)
│   │   ├── __init__.py
│   │   ├── progress_view.py
│   │   ├── result_view.py
│   │   └── error_view.py
│   │
│   ├── models/                     # Model: domain schemas / entities
│   │   ├── __init__.py
│   │   ├── recognition.py
│   │   ├── question.py
│   │   ├── validation.py
│   │   └── grading.py
│   │
│   ├── services/                   # Use-cases / application services (OOP)
│   │   ├── __init__.py
│   │   ├── pdf/
│   │   │   ├── __init__.py
│   │   │   └── renderer.py
│   │   ├── vision/
│   │   │   ├── __init__.py
│   │   │   ├── ollama_client.py
│   │   │   └── recognizer.py
│   │   ├── questions/
│   │   │   ├── __init__.py
│   │   │   ├── segmenter.py
│   │   │   └── extractor.py
│   │   ├── latex/
│   │   │   ├── __init__.py
│   │   │   └── builder.py
│   │   ├── math/
│   │   │   ├── __init__.py
│   │   │   ├── parser.py
│   │   │   ├── sympy_validator.py
│   │   │   └── equivalence.py
│   │   └── grading/
│   │       ├── __init__.py
│   │       ├── step_grader.py
│   │       ├── rubric.py
│   │       └── report.py
│   │
│   ├── functions/                  # Pure / functional helpers
│   │   ├── __init__.py
│   │   ├── latex_transforms.py
│   │   ├── score_aggregate.py
│   │   └── confidence.py
│   │
│   ├── interfaces/                 # Ports / abstraksi (SOLID)
│   │   ├── __init__.py
│   │   ├── renderer.py
│   │   ├── recognizer.py
│   │   ├── validator.py
│   │   └── reporter.py
│   │
│   └── prompts/
│       ├── recognition.txt
│       ├── latex.txt
│       ├── validation.txt
│       └── grading.txt
│
├── data/
│   ├── input/
│   │   ├── jawaban/              # PDF jawaban mahasiswa
│   │   └── kunci_jawaban/        # kunci / sumber jawaban standar
│   └── output/
│       ├── pages/
│       ├── recognition/
│       ├── questions/
│       ├── standards/
│       │   └── exam_001/
│       │       ├── rubrics/
│       │       └── solutions/
│       └── report.*          # report.json / summary.csv / report.html
│
├── tests/
├── scripts/
├── requirements.txt
└── README.md
```

Catatan struktur:

- `controllers/` hanya mengorkestrasi; tidak memanggil Ollama/SymPy langsung.
- `views/` hanya memformat output CLI.
- `services/` berisi kelas OOP dengan dependency injection terhadap `interfaces/`.
- `functions/` berisi pure function tanpa I/O.
- `models/` berisi schema/entity, bukan logika infrastruktur.

---

# 6. Data Model

## 6.1 Page

```json
{
  "page_number": 1,
  "image": "pages/page_001.png",
  "width": 1654,
  "height": 2339
}
```

## 6.2 Recognition

```json
{
  "page_number": 1,
  "questions": [
    {
      "question_number": 1,
      "region": {
        "x": 100,
        "y": 200,
        "width": 1200,
        "height": 800
      },
      "steps": [
        {
          "step_number": 1,
          "raw_text": "2x + 5 = 15",
          "latex": "2x + 5 = 15"
        },
        {
          "step_number": 2,
          "raw_text": "2x = 10",
          "latex": "2x = 10"
        },
        {
          "step_number": 3,
          "raw_text": "x = 5",
          "latex": "x = 5"
        }
      ],
      "final_answer": "x = 5"
    }
  ]
}
```

## 6.3 Validation

```json
{
  "question_number": 1,
  "steps": [
    {
      "step_number": 1,
      "status": "valid",
      "method": "sympy"
    },
    {
      "step_number": 2,
      "status": "valid",
      "method": "sympy"
    }
  ]
}
```

## 6.4 Grade

```json
{
  "question_number": 1,
  "maximum_score": 10,
  "score": 10,
  "steps": [
    {
      "step_number": 1,
      "score": 3,
      "status": "correct"
    },
    {
      "step_number": 2,
      "score": 3,
      "status": "correct"
    },
    {
      "step_number": 3,
      "score": 4,
      "status": "correct"
    }
  ]
}
```

---

# 7. Tahap 1 — PDF Rendering

Implementasikan:

```python
render_pdf(pdf_path, output_dir, dpi=200)
```

Requirements:

- satu PNG per halaman;
- nama file deterministik;
- mempertahankan nomor halaman;
- jangan mengubah isi;
- simpan metadata ukuran gambar.

Contoh:

```text
data/output/pages/
├── page_001.png
├── page_002.png
└── page_003.png
```

Tambahkan unit test untuk:
- PDF satu halaman;
- PDF banyak halaman;
- PDF kosong;
- file PDF invalid.

---

# 8. Tahap 2 — Vision Recognition

Gunakan Ollama API.

Buat abstraction:

```python
class VisionRecognizer:
    def recognize_page(self, image_path) -> PageRecognition:
        ...
```

Jangan mengikat kode aplikasi langsung ke model tertentu.

Prompt recognition harus meminta:

1. identifikasi nomor soal;
2. identifikasi batas soal;
3. identifikasi langkah penyelesaian;
4. identifikasi final answer;
5. transkripsi tulisan;
6. transkripsi formula ke LaTeX;
7. confidence;
8. region/bounding box jika model mampu memberikannya.

Instruksi penting:

```text
Transcribe the student's work exactly as written.
Do not solve the problem.
Do not correct mathematical errors.
Do not invent missing steps.
If a symbol is uncertain, mark it as uncertain.
```

Output wajib JSON.

---

# 9. Tahap 3 — Question Segmentation

Satu soal dapat:
- berada pada satu halaman;
- berlanjut ke halaman berikutnya;
- memiliki beberapa bagian;
- memiliki coretan yang bukan bagian jawaban.

Buat:

```python
segment_questions(pages) -> list[Question]
```

Gunakan nomor soal jika tersedia.

Jika nomor soal tidak jelas, gunakan LLM untuk melakukan structural segmentation.

Setiap `Question` harus memiliki:

```text
question_id
page_references
image_regions
student_steps
student_final_answer
```

---

# 10. Tahap 4 — LaTeX Conversion

Pisahkan recognition dari formatting.

Buat:

```python
build_student_latex(question) -> str
```

Contoh:

```latex
\begin{aligned}
2x+5 &= 15\\
2x &= 10\\
x &= 5
\end{aligned}
```

Simpan:

```text
data/output/questions/question_001/student.tex
```

Jangan menghapus `raw_text`.

Tujuannya adalah agar LaTeX dapat diperbaiki tanpa kehilangan hasil recognition awal.

---

# 11. Tahap 5 — Standard Answer

Jawaban standar harus dimasukkan oleh dosen atau dibuat sebelumnya.

Struktur:

```text
data/output/standards/
└── exam_001/
    ├── questions/
    │   ├── question_001.tex
    │   └── question_002.tex
    └── solutions/
        ├── question_001.tex
        └── question_002.tex
```

Selain LaTeX, simpan rubric:

```json
{
  "question": 1,
  "maximum_score": 10,
  "criteria": [
    {
      "id": "setup",
      "points": 2
    },
    {
      "id": "transformation",
      "points": 4
    },
    {
      "id": "calculation",
      "points": 2
    },
    {
      "id": "final_answer",
      "points": 2
    }
  ]
}
```

Rubric tidak harus mengikuti struktur jawaban standar secara persis.

---

# 12. Tahap 6 — Mathematical Validation

Gunakan beberapa level validation.

## Level 1 — Syntax

Periksa apakah LaTeX dapat diparse.

## Level 2 — Symbolic

Gunakan SymPy jika ekspresi dapat dikonversi.

Contoh:

```text
2x + 5 = 15
```

menjadi representasi SymPy.

## Level 3 — Step Equivalence

Bandingkan:

```text
previous_step
next_step
```

dan tentukan apakah transformasi ekuivalen.

Contoh:

```text
2x + 5 = 15
2x = 10
```

valid.

Sedangkan:

```text
2x + 5 = 15
2x = 20
```

tidak valid.

## Level 4 — LLM Reasoning

Jika SymPy tidak mampu memutuskan, kirim ke reasoning LLM.

Output harus structured:

```json
{
  "status": "valid|invalid|uncertain",
  "reason": "...",
  "confidence": 0.0
}
```

Jangan memaksa LLM memilih `valid` atau `invalid` jika evidence tidak cukup.

---

# 13. Tahap 7 — Comparison Against Standard

Jangan membandingkan string LaTeX secara langsung.

Contoh berikut dapat memiliki arti sama:

```latex
x = 5
```

dan:

```latex
5 = x
```

Gunakan mathematical equivalence jika memungkinkan.

Perbandingan harus mempertimbangkan:

1. equivalent expression;
2. equivalent equation;
3. algebraic transformation;
4. equivalent final answer;
5. alternate valid method.

Jawaban mahasiswa tidak boleh dianggap salah hanya karena berbeda bentuk dari jawaban standar.

---

# 14. Tahap 8 — Grading

Grading harus berbasis rubric.

Contoh:

```text
Question 1 = 10 points

Step 1     2 points
Step 2     3 points
Step 3     3 points
Final      2 points
```

Jika mahasiswa melakukan kesalahan pada satu langkah tetapi langkah berikutnya konsisten dengan kesalahan tersebut, sistem harus dapat membedakan:

```text
conceptual error
calculation error
transcription error
carry-forward error
```

Jangan otomatis mengurangi seluruh nilai hanya karena final answer salah.

---

# 15. LLM Grading Prompt

LLM menerima:

```text
PROBLEM:
...

STANDARD SOLUTION:
...

STUDENT SOLUTION:
...

STEP VALIDATION:
...

RUBRIC:
...
```

Instruksi:

```text
Evaluate the student's mathematical work using the supplied rubric.

Do not grade based solely on whether the final answer matches.

Evaluate each step.

Distinguish:
- conceptual errors
- arithmetic errors
- notation/transcription uncertainty
- invalid transformations
- valid alternative methods

Award partial credit when justified.

Do not invent student work that is not present.

Return JSON only.
```

Output:

```json
{
  "score": 7,
  "maximum_score": 10,
  "step_results": [
    {
      "step": 1,
      "status": "correct",
      "score": 2
    },
    {
      "step": 2,
      "status": "incorrect",
      "score": 0,
      "reason": "..."
    }
  ],
  "feedback": "...",
  "confidence": 0.91
}
```

---

# 16. Confidence dan Human Review

Tambahkan status:

```text
AUTO_ACCEPT
REVIEW_REQUIRED
LOW_CONFIDENCE
```

Contoh:

```text
OCR confidence < threshold
        ↓
REVIEW_REQUIRED

SymPy = valid
LLM = invalid
        ↓
REVIEW_REQUIRED

OCR jelas
SymPy valid
LLM valid
confidence tinggi
        ↓
AUTO_ACCEPT
```

Tujuannya bukan membuat sistem selalu mengambil keputusan sendiri, tetapi membuat kasus yang meragukan mudah diperiksa dosen.

---

# 17. Output

Setiap ujian menghasilkan:

```text
data/output/exam_001/
├── student_001/
│   ├── pages/
│   ├── questions/
│   │   ├── question_001/
│   │   │   ├── source.png
│   │   │   ├── recognition.json
│   │   │   ├── student.tex
│   │   │   ├── validation.json
│   │   │   └── grading.json
│   │   └── question_002/
│   ├── grading.json
│   └── report.html
└── summary.csv
```

`summary.csv`:

```text
student_id,q1,q2,q3,q4,total,status
student_001,8,10,6,9,33,AUTO_ACCEPT
```

---

# 18. Presentasi CLI (View)

Karena aplikasi utama adalah CLI, “UI” tahap awal adalah presentasi terminal, bukan Streamlit.

Minimal:

```text
$ python -m app.cli process

PDF tersedia di data/input/jawaban:
  1. smoke_inequality.pdf
  2. tugas 1 matsi_Fathi Rizky.pdf

Pilih nomor (atau nama file), lalu Enter.
Pilihan: 1
Memproses: data/input/jawaban/smoke_inequality.pdf

Membersihkan data/output (kecuali standards/)...
  - removed pages
  - removed recognition
  - removed questions

[ Select models from app/config/config.yaml ]
Vision model:    MODEL_VISION
Reasoning model: MODEL_REASONING

Progress:
PDF rendering       ██████████ 100%
Recognition          ████████░░  80%
Question extraction  ██████░░░░  60%
Validation           ████░░░░░░  40%
Grading              ██░░░░░░░░  20%

Results
-----------------------------------------
Question 1    8/10
Question 2    10/10
Question 3    6/10
-----------------------------------------
Total         24/30

Artifacts written to: data/output/exam_001/student_001/
```

Semua format output (progress, summary, error) hidup di `app/views/`. Controller hanya menyediakan data siap tampil.

Streamlit/Gradio **bukan** bagian MVP. Jika ditambahkan nanti, mereka menjadi View alternatif yang memanggil Controller/service yang sama.

---

# 19. API Layer (Opsional, pasca-MVP)

Setelah engine CLI stabil, FastAPI boleh ditambahkan sebagai adapter/controller HTTP:

```text
POST /api/exams
POST /api/submissions
POST /api/process/{submission_id}
GET  /api/submissions/{id}
GET  /api/questions/{id}
GET  /api/results/{id}
```

Engine grading **tidak boleh** bergantung pada FastAPI. Service layer yang sama dipakai CLI dan API.

---

# 20. CLI

CLI adalah **satu-satunya antarmuka wajib** untuk MVP. Implementasikan sejak awal:

```bash
python -m app.cli render data/input/jawaban/smoke_inequality.pdf
python -m app.cli recognize smoke_inequality.pdf
python -m app.cli extract smoke_inequality.pdf
python -m app.cli validate data/output/questions
python -m app.cli grade data/output/questions
python -m app.cli process
python -m app.cli process smoke_inequality.pdf
```

Perintah utama:

```bash
python -m app.cli process \
    --standard data/output/standards/exam_001 \
    --output data/output
```

PDF jawaban diletakkan di `data/input/jawaban/`; kunci di `data/input/kunci_jawaban/`.

- `python -m app.cli process` menampilkan menu PDF di folder jawaban (pilih nomor atau nama file).
- Nama file singkat (mis. `smoke_inequality.pdf`) di-resolve otomatis ke folder jawaban.
- Di awal `process`, `data/output/` dikosongkan kecuali `standards/` (rubric/solusi tetap).
Pemetaan MVC untuk CLI:

```text
app/cli.py                  → bootstrap + argparse
app/controllers/*.py        → orchestrate use-case per perintah
app/views/*.py              → cetak progress / hasil / error
app/services/**             → business logic (OOP + DI)
app/functions/**            → pure transforms (FP)
app/models/**               → domain data
app/interfaces/**           → abstraksi SOLID
```

Setiap subcommand CLI harus tipis: parse args → panggil satu controller → tampilkan hasil via view → exit code yang jelas (`0` sukses, non-zero gagal).

---

# 21. Tahapan Implementasi

## Phase 1 — PDF

Implement:
- PDF loading;
- page rendering;
- metadata;
- tests.

Acceptance criterion:

```text
data/input/jawaban/*.pdf
→ data/output/pages/page_001.png
→ data/output/pages/page_002.png
→ ...
```

## Phase 2 — Ollama Vision

Implement:
- Ollama client;
- image input;
- JSON output;
- retry;
- timeout;
- logging.

Acceptance criterion:

```text
page image
→ structured recognition JSON
```

## Phase 3 — Question Extraction

Implement:
- question detection;
- multi-page questions;
- step extraction;
- final answer extraction.

Acceptance criterion:

```text
page images
→ Question objects
```

## Phase 4 — LaTeX

Implement:
- formula recognition;
- LaTeX builder;
- per-question `.tex`.

Acceptance criterion:

```text
Question
→ student.tex
```

## Phase 5 — SymPy

Implement:
- expression parser;
- equation parser;
- equivalence checker;
- step validator.

Acceptance criterion:

Known mathematical transformations produce expected validation results.

## Phase 6 — LLM Validator

Implement:
- validation prompt;
- structured response;
- uncertain state;
- confidence.

Acceptance criterion:

LLM does not silently convert uncertainty into a definitive result.

## Phase 7 — Grading

Implement:
- rubric;
- step scoring;
- partial credit;
- final score;
- feedback.

Acceptance criterion:

A predefined test set produces expected grading ranges.

## Phase 8 — Report

Implement:
- JSON;
- CSV;
- HTML;
- optional PDF.

## Phase 9 — CLI polish (bukan web UI)

Setelah pipeline backend bekerja:

- lengkapi subcommand CLI;
- progress dan ringkasan hasil di terminal;
- exit code dan pesan error yang jelas;
- pastikan View/Controller/Service terpisah sesuai MVC.

Web UI atau FastAPI hanya jika dibutuhkan setelah MVP CLI selesai.

---

# 22. Testing Dataset

Buat dataset kecil terlebih dahulu.

Minimal:

```text
testdata/
├── correct/
├── wrong_calculation/
├── wrong_concept/
├── alternative_solution/
├── partially_correct/
├── messy_handwriting/
├── crossed_out_steps/
├── multi_page/
└── ambiguous_symbols/
```

Untuk setiap test case simpan:

```text
problem
standard_solution
student_image
expected_step_status
expected_score_range
```

Jangan menguji hanya dengan jawaban yang benar.

---

# 23. Important Mathematical Cases

Katalog domain resmi adalah silabus di [`topik.md`](topik.md). Sistem dikembangkan mengikuti urutan bab tersebut (jangan loncat bab sebelum yang sebelumnya cukup stabil).

Ringkasan bab:

```text
1  Sistem Bilangan Real dan Pertidaksamaan   (MVP: 1.5 Pertidaksamaan)
2  Pertidaksamaan Nilai Mutlak
3  Fungsi
4  Limit
5  Kekontinuan
6  Turunan Fungsi
7  Integral
8  Fungsi Transenden
9  Matriks dan Operasinya
10 Invers dan Determinan
11 Vektor di Bidang dan Ruang
```

Urutan implementasi domain:

```text
MVP:  1.5 Pertidaksamaan
Next: 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11
```

Detail status per bab dan hint SymPy vs LLM: `docs/math-topics.md`.

---

# 24. Model Strategy

Pisahkan model berdasarkan tugas:

```text
Vision model
    ↓
handwriting + mathematical notation recognition

Reasoning model
    ↓
mathematical validation + grading
```

Model dapat sama, tetapi arsitektur harus memungkinkan model berbeda.

Konfigurasi:

```yaml
models:
  vision: "..."
  reasoning: "..."
```

Jangan hard-code nama model.

---

# 25. Ollama Client

Buat satu abstraction:

```python
class OllamaClient:

    def generate(self, prompt, model):
        ...

    def generate_with_image(self, prompt, image_path, model):
        ...
```

Semua module lain menggunakan abstraction tersebut.

Jangan menyebarkan HTTP call Ollama ke seluruh project.

---

# 26. Prompt Management

Prompt disimpan sebagai file:

```text
app/prompts/
├── recognition.txt
├── latex.txt
├── validation.txt
└── grading.txt
```

Prompt harus versionable.

Contoh:

```text
PROMPT_VERSION = "recognition-v1"
```

Simpan prompt version di hasil grading sehingga hasil dapat direproduksi.

---

# 27. Logging

Log:

```text
timestamp
submission_id
page
model
prompt_version
processing_time
token information jika tersedia
recognition status
validation status
grading status
errors
```

Jangan menyimpan credential Ollama/API di source code.

---

# 28. Error Handling

Tangani:

- PDF corrupt;
- halaman tidak dapat dirender;
- Ollama tidak berjalan;
- model tidak tersedia;
- timeout;
- JSON invalid;
- LaTeX invalid;
- SymPy parsing failure;
- LLM memberikan output bukan JSON;
- recognition confidence rendah.

Jika salah satu tahap gagal, jangan kehilangan hasil tahap sebelumnya.

---

# 29. Reproducibility

Setiap submission harus menyimpan:

```json
{
  "application_version": "...",
  "vision_model": "...",
  "reasoning_model": "...",
  "recognition_prompt_version": "...",
  "validation_prompt_version": "...",
  "grading_prompt_version": "...",
  "timestamp": "..."
}
```

Dengan demikian hasil grading dapat ditelusuri.

---

# 30. Security

Jangan memasukkan:
- password;
- API keys;
- credentials;

ke source code atau repository.

Gunakan environment variables jika diperlukan.

Untuk data mahasiswa, minimalkan data yang dikirim keluar dari komputer. Jika menggunakan Ollama lokal, gambar dan jawaban dapat diproses secara lokal sesuai konfigurasi deployment.

---

# 31. Development Rule untuk AI Coding Agent

AI coding agent harus bekerja secara bertahap.

Sebelum membuat kode:

1. Inspect seluruh repository.
2. Buat/inspeksi architecture plan.
3. Identifikasi dependency.
4. Implement satu phase.
5. Jalankan test.
6. Perbaiki error.
7. Jangan mengubah API/module yang sudah stabil tanpa alasan.
8. Jangan mengarang API library.
9. Periksa dokumentasi library ketika menggunakan fitur yang belum diverifikasi.
10. Jangan menganggap hasil LLM selalu benar.
11. Semua output LLM harus divalidasi terhadap schema.
12. Semua mathematical claims yang dapat diperiksa secara symbolic harus diprioritaskan ke symbolic verification.
13. Gunakan LLM untuk reasoning yang memang tidak dapat ditangani deterministic checker.
14. Pertahankan original image dan raw recognition.
15. Jangan menghapus data intermediate.
16. Hormati arsitektur MVC: jangan campur logika grading di View atau CLI parser.
17. Hormati SOLID: bergantung pada abstraksi (`interfaces/`), injeksikan dependency, jangan hard-code Ollama/SymPy di Controller.
18. Terapkan clean coding: fungsi kecil, nama jelas, type hints, hindari side effect tersembunyi.
19. Gunakan OOP untuk service/client ber-state dan FP untuk transformasi murni; jangan memaksa semua logika menjadi class.
20. Entry point wajib tetap CLI; jangan mengalihkan MVP ke web UI.

---

# 32. Definition of Done

MVP dianggap selesai jika:

- [ ] Aplikasi dapat dijalankan sepenuhnya melalui CLI Python.
- [ ] Struktur kode mengikuti MVC (controllers / views / models / services).
- [ ] Abstraksi mengikuti SOLID (interfaces + dependency injection).
- [ ] Transformasi deterministik diimplementasikan sebagai pure function bila memungkinkan.
- [ ] PDF dapat diubah menjadi PNG per halaman.
- [ ] PNG dapat dikirim ke Vision model melalui Ollama.
- [ ] Recognition menghasilkan JSON valid.
- [ ] Soal dapat dipisahkan.
- [ ] Langkah penyelesaian dapat dipisahkan.
- [ ] Formula dapat direpresentasikan sebagai LaTeX.
- [ ] Student solution disimpan per soal.
- [ ] Standard solution dapat dimasukkan.
- [ ] SymPy dapat memvalidasi sebagian transformasi.
- [ ] LLM dapat menangani kasus yang tidak dapat diverifikasi SymPy.
- [ ] Sistem dapat membandingkan student solution dengan standard solution.
- [ ] Rubric grading menghasilkan partial credit.
- [ ] Hasil grading tersimpan dalam JSON.
- [ ] Report dapat dibuat.
- [ ] Kasus uncertain dapat ditandai untuk human review.
- [ ] Semua intermediate artifacts dapat diaudit.
- [ ] Test suite dasar berjalan.

---

# 33. Target MVP

Jangan langsung mendukung semua bab di `topik.md`.

Target MVP:

```text
CLI Python (MVC)
 ↓
PDF
 ↓
1–5 halaman
 ↓
tulisan tangan matematika
 ↓
topik 1.5 — pertidaksamaan
(bentuk umum + himpunan penyelesaian)
 ↓
langkah per langkah
 ↓
LaTeX
 ↓
SymPy verification
 ↓
LLM fallback
 ↓
rubric
 ↓
score + feedback (CLI summary + artifacts)
```

Setelah pipeline ini stabil, perluas mengikuti `topik.md`:
- 2 nilai mutlak / pertidaksamaan nilai mutlak;
- 3 fungsi;
- 4 limit;
- 5 kekontinuan;
- 6 turunan;
- 7 integral;
- 8 fungsi transenden;
- 9 matriks;
- 10 determinan dan invers;
- 11 vektor.

---

# 34. Referensi Implementasi

Repository yang dapat dijadikan referensi arsitektur/komponen:

- Math-grading: https://github.com/anishstoppo55/Math-grading
- VLM-Math: https://github.com/shreemitra/VLM-Math
- GradeMate: https://github.com/luisfilipeap/GradeMate
- Autograding handwritten mathematical worksheets: https://github.com/divyaprabha123/Autograding-handwritten-mathematical-worksheets
- ExamGrader: https://github.com/CCU-Bioinformatics-Lab/ExamGrader
- EvalAI: https://github.com/EvalAiProject/evalai
- PaddleOCR formula recognition documentation: https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/pipeline_usage/formula_recognition.en.md

Referensi tersebut digunakan sebagai sumber ide dan pembanding implementasi, bukan sebagai bukti bahwa seluruh komponennya harus digunakan.

---

# 35. Instruksi Utama untuk AI yang Membangun Aplikasi

AI coding agent harus mengimplementasikan aplikasi ini dengan prinsip berikut:

```text
FIRST:
Understand architecture and repository.
Enforce: CLI-first, MVC, SOLID, clean coding, OOP + FP.

THEN:
Scaffold MVC folders (controllers, views, models, services, interfaces, functions).

THEN:
Implement PDF rendering.

THEN:
Implement Ollama vision recognition.

THEN:
Implement structured question/step extraction.

THEN:
Implement LaTeX representation.

THEN:
Implement mathematical validation.

THEN:
Implement standard-solution comparison.

THEN:
Implement rubric grading.

THEN:
Implement reporting.

FINALLY:
Polish CLI presentation (View layer).
Optional: API/web adapters that reuse the same services.

At every stage:
- write tests;
- run tests;
- preserve previous functionality;
- validate external library APIs;
- do not invent functionality;
- do not silently correct student work;
- preserve original evidence;
- expose uncertainty;
- keep grading auditable;
- keep Controllers thin;
- keep Views free of business logic;
- inject dependencies through interfaces;
- prefer pure functions for deterministic transforms.
```

## Expected final workflow

```text
student.pdf
     │
     ▼
CLI (View + Controller)
     │
     ▼
page images
     │
     ▼
Vision recognition
     │
     ▼
structured questions
     │
     ▼
student LaTeX
     │
     ├──────────────┐
     ▼              ▼
SymPy            LLM
validation       reasoning
     │              │
     └──────┬───────┘
            ▼
      validated steps
            │
            ▼
     standard solution
            │
            ▼
        rubric grader
            │
            ▼
      score + feedback
            │
            ▼
   JSON / CSV / HTML + CLI summary
```
