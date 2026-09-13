# AI REPORT STUDIO 

> Không gian tạo báo cáo tập trung cho công việc quản trị, phân tích dữ liệu và nghiên cứu có dẫn chứng, kết hợp trình soạn thảo A4, nguồn tham khảo và xuất bản DOCX/PDF.

Luồng làm việc chính gồm 7 điểm đến: **Tổng quan, Tạo mới, Dự án, Dữ liệu, Nghiên cứu, Mẫu và Cài đặt**. Báo cáo nằm trong Dự án, thư viện nguồn nằm trong Nghiên cứu và bộ nhận diện nằm trong Cài đặt. Các liên kết cũ `/documents`, `/sources` và `/brand-kit` tự chuyển sang vị trí mới.

---

## 🏛️ Kiến Trúc Hệ Thống (Clean Architecture)

- **Frontend**: Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS 4, shadcn/ui, Tiptap, Zustand, TanStack Query.
- **Backend API**: FastAPI (Python 3.11+ / 3.14), SQLAlchemy 2.0 Async, Pydantic v2.
- **Database**: SQLite (Async aiosqlite cho Dev) / PostgreSQL 16 (AsyncPG cho Production).
- **Core Modules**:
  - `Document Parser`: PyMuPDF (PDF), python-docx (Word XML & placeholder extraction), openpyxl/pandas (Excel).
  - `Research Engine`: Search Provider abstraction (Tavily, Brave, SerpAPI), real web crawler & fact extractor.
  - `Citation Engine`: IEEE, APA 7, Harvard, MLA; Anti-hallucination claim-to-evidence verification mapping.
  - `AI Provider Engine`: Abstraction hỗ trợ Gemini, OpenAI, Anthropic, Ollama.
  - `Export Engine`: High-fidelity DOCX & PDF generation.

Các thử nghiệm tự động hóa báo cáo, cộng tác, chấm xác suất AI, tạo báo cáo từ file âm thanh, Presentation Studio, Codebase Intelligence, Document Designer, OCR bố cục nâng cao và Deep Research V2 đã được rút khỏi runtime để tập trung độ tin cậy cho luồng cốt lõi. Bảng dữ liệu lịch sử vẫn được giữ nguyên để không làm mất bản ghi cũ.

---

## 🚀 Hướng Dẫn Cài Đặt & Chạy

### Chạy nhanh local demo

```bash
# Tạo/cập nhật dữ liệu demo, có thể chạy lại nhiều lần không bị trùng
PYTHONPATH=apps/api ./apps/api/venv/bin/python apps/api/app/seed_sample.py

# Chạy Backend API + Frontend Web cùng lúc
bash scripts/dev.sh
```

- Web Application: [http://localhost:3050](http://localhost:3050)
- API Docs: [http://localhost:8050/docs](http://localhost:8050/docs)

Kiểm tra nhanh sau khi server đã lên:

```bash
bash scripts/smoke-local.sh
bash scripts/smoke-demo-flow.sh
```

### 0. Cấu hình biến môi trường

Không commit file `.env.development`, `.env.production`, `.env.staging` hoặc API key thật lên Git.

```bash
cp .env.example .env.development
```

Sau đó tự điền key thật vào `.env.development` trên máy local hoặc cấu hình qua secret manager khi deploy.

Khi chạy production, bắt buộc đặt:

- `JWT_SECRET`: chuỗi ngẫu nhiên mạnh, không dùng giá trị mẫu.
- `CORS_ORIGINS`: JSON array các domain frontend được phép, ví dụ `["https://app.example.com"]`; không dùng `"*"`.
- `DEBUG=false`.

### 1. Khởi chạy Backend API

```bash
# Di chuyển vào thư mục API
cd apps/api

# Kích hoạt virtual environment
source venv/bin/activate

# Cài đặt dependencies (nếu chưa cài)
pip install -r requirements.txt

# Chạy server API trên cổng 8050
uvicorn app.main:app --reload --port 8050
```
- API Docs: [http://localhost:8050/docs](http://localhost:8050/docs)
- Health Check: [http://localhost:8050/api/v1/health](http://localhost:8050/api/v1/health)

### 2. Khởi chạy Frontend Web

```bash
# Di chuyển vào thư mục Web
cd apps/web

# Cài đặt dependencies (nếu chưa cài)
npm install

# Chạy Next.js development server trên cổng 3050
npm run dev
```
- Web Application: [http://localhost:3050](http://localhost:3050)

### 3. Chạy Test Suite

```bash
# Backend deterministic (không gọi Internet/provider thật)
cd apps/api
venv/bin/python -m pytest -q
cd ../..

# Frontend test, typecheck, lint và production build
npm --prefix apps/web test
npm --prefix apps/web run typecheck
npm --prefix apps/web run lint
npm --prefix apps/web run build
```

GitHub Actions chạy cùng các cổng này cho mọi push và pull request. Test và
build deterministic được đặt trong Linux network namespace không có kết nối
ngoài; PostgreSQL migration dùng database CI cục bộ riêng.

### 4. Kiểm tra an toàn trước khi commit/push

Chạy lệnh này trước mỗi lần commit hoặc push:

```bash
bash scripts/check-secrets.sh
```

Script sẽ chặn các lỗi phổ biến:

- Commit nhầm `.env.*`.
- Commit nhầm database, file upload, file export DOCX/HTML hoặc cache.
- Commit nhầm API key kiểu OpenAI, Gemini, Google OAuth, GitHub token, AWS key.

Quy trình đề xuất:

```bash
git status --short
bash scripts/check-secrets.sh
git add .gitignore .env.example scripts/check-secrets.sh README.md
git commit -m "chore(security): prevent committing secrets and generated files"
```

### 5. Lịch sử lớp màu bảng tính

Người dùng đã đăng nhập có thể xem trước, xác nhận, hủy và hoàn tác lớp màu
trong SCANT với workbook XLSX/XLSM. Lịch sử và đề xuất đang chờ được lưu theo
người dùng, nguồn dữ liệu và SHA-256 của nội dung file. Mở lại cùng file để
khôi phục; file đã thay đổi cần xem trước lại. CSV và phiên khách tiếp tục dùng
thao tác cục bộ. Việc lưu lớp màu không sửa file gốc hoặc Google Sheets.

Trước khi triển khai, sao lưu database bằng công cụ tương ứng với database đang
dùng, rồi cấu hình `DATABASE_URL` và chạy từ thư mục API:

```bash
cd apps/api
venv/bin/python -m app.migrations.runner bootstrap  # chỉ cho lần tiếp nhận schema cũ
venv/bin/alembic upgrade head                       # các lần triển khai tiếp theo
venv/bin/python -m app.migrations.runner check
```

Bootstrap chỉ đóng dấu các schema SCANT đã nhận diện chính xác và từ chối schema
lạ. Chuỗi `0001 -> 0002` đã được kiểm tra trên SQLite và PostgreSQL 16, gồm giữ
dữ liệu cũ, bảng billing tiền phát hành, hạn mức và lịch sử workbook. Quy trình
backup, kiểm tra và khôi phục nằm trong
[hướng dẫn migration](apps/api/MIGRATIONS.md).

Xem tiến độ, kiểm thử và các phần chưa hoàn thành trong
[kế hoạch nâng cấp production](docs/SCANT_PRODUCTION_UPGRADE_PLAN.md).
