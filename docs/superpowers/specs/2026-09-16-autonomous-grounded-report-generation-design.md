# Thiết kế tạo báo cáo tự động có nghiên cứu web, ảnh và tài liệu tham khảo

**Ngày:** 2026-09-16  
**Trạng thái:** Đã thống nhất hướng sản phẩm, chờ duyệt đặc tả trước khi lập kế hoạch triển khai

## 1. Mục tiêu

Nâng cấp chế độ tạo báo cáo tự động để người dùng chỉ cần cung cấp đề tài, yêu cầu chi tiết và file mẫu DOCX nếu có. Hệ thống tự đọc mẫu, lập kế hoạch nghiên cứu, tìm thông tin thật trên web, chọn ảnh phù hợp, viết báo cáo có trích dẫn, tạo danh mục tài liệu tham khảo và xuất tài liệu theo đúng bố cục.

Kết quả phải đáp ứng bốn điều kiện:

1. Nội dung tuân thủ cấu trúc và quy chuẩn của file mẫu nếu người dùng tải mẫu lên.
2. Mỗi nhận định quan trọng dựa trên dữ kiện bên ngoài phải truy ngược được tới nguồn thật.
3. Ảnh web được tải về thư viện dự án, chèn vào đúng mục và lưu đầy đủ thông tin nguồn.
4. Danh mục tài liệu tham khảo chỉ chứa nguồn đã được sử dụng trong báo cáo.

## 2. Các quyết định sản phẩm đã thống nhất

- Luồng chạy tự động hoàn toàn; người dùng kiểm tra sau khi báo cáo được tạo.
- Có file mẫu thì ưu tiên tuyệt đối cấu trúc, định dạng và quy chuẩn trích dẫn của mẫu.
- Nếu mẫu thiếu kết luận, tài liệu tham khảo hoặc phần bắt buộc khác, hệ thống bổ sung phần đó theo cùng phong cách của mẫu.
- Không có mẫu thì hệ thống chọn quy chuẩn theo loại báo cáo:
  - APA 7 cho báo cáo học thuật/nghiên cứu.
  - IEEE cho tài liệu kỹ thuật.
  - Trích dẫn đánh số cho báo cáo doanh nghiệp và đề xuất.
- Nguồn chính thức, học thuật, tiêu chuẩn và tổ chức uy tín được ưu tiên. Báo chí, blog và trang thương mại chỉ được dùng khi thiếu nguồn tốt hơn hoặc khi chính đối tượng nghiên cứu là sản phẩm/tổ chức đó.
- Ảnh có thể lấy từ mọi trang web công khai. Mỗi ảnh phải lưu URL trang nguồn, URL ảnh, tên nguồn, tác giả nếu có và giấy phép nếu nhà cung cấp công bố.
- AI tự quyết định mật độ ảnh theo nội dung; ảnh chỉ được chèn khi làm rõ một khái niệm, đối tượng, quy trình hoặc kết quả quan trọng.

## 3. Phạm vi

### Trong phạm vi

- Chế độ tạo báo cáo tự động ở trang tạo dự án.
- Đọc và phân tích file mẫu DOCX.
- Lập kế hoạch nghiên cứu theo từng mục.
- Tìm kiếm web, xếp hạng nguồn và lưu bằng chứng.
- Viết nội dung có trích dẫn nội tuyến.
- Tìm, tải, lưu và chèn ảnh web.
- Sinh danh mục tài liệu tham khảo từ nguồn thực tế đã trích dẫn.
- Hiển thị tiến trình, kết quả nghiên cứu, nguồn và ảnh trong Studio.
- Giữ ảnh và nguồn khi xuất DOCX/PDF/HTML.

### Ngoài phạm vi giai đoạn này

- Mua ảnh trả phí hoặc vượt qua paywall.
- Tự đăng ký tài khoản trên các kho dữ liệu bên ngoài.
- Dịch nguyên văn tài liệu có bản quyền với dung lượng lớn.
- Bảo đảm quyền tái sử dụng pháp lý cho mọi ảnh công khai. Hệ thống lưu nguồn và giấy phép tìm được để người dùng kiểm tra.

## 4. Trải nghiệm người dùng

### 4.1 Đầu vào

Trang tạo báo cáo giữ luồng hiện tại và làm rõ bốn nhóm đầu vào:

1. **Đề tài:** bắt buộc, mô tả đối tượng cần nghiên cứu.
2. **Yêu cầu chi tiết:** phạm vi, số trang, độc giả, câu hỏi cần trả lời và các ràng buộc.
3. **File mẫu DOCX:** tùy chọn, được xem là quy chuẩn về cấu trúc và trình bày.
4. **Tài liệu/dữ liệu riêng:** tùy chọn, được ưu tiên hơn nguồn web cho dữ kiện nội bộ.

Nút chính là **Tạo báo cáo tự động**. Trước khi chạy, giao diện hiển thị tóm tắt: mẫu đang dùng, chuẩn trích dẫn dự kiến, nguồn web được bật và ảnh web được bật.

### 4.2 Tiến trình

Màn hình tiến trình hiển thị các giai đoạn thật thay vì thông báo chung:

1. Đọc đề tài và yêu cầu.
2. Phân tích file mẫu.
3. Lập dàn ý và kế hoạch nghiên cứu.
4. Tìm và kiểm chứng nguồn.
5. Viết nội dung theo từng mục.
6. Tìm và chèn ảnh.
7. Tạo trích dẫn và tài liệu tham khảo.
8. Kiểm tra tính nhất quán và dựng file.

Mỗi giai đoạn có trạng thái chờ, đang chạy, hoàn thành hoặc cảnh báo. Cảnh báo không chặn toàn bộ báo cáo nếu chỉ một ảnh hoặc một nguồn phụ thất bại.

### 4.3 Kết quả

Khi hoàn thành, người dùng được đưa vào Studio với:

- Nội dung theo từng mục của mẫu.
- Trích dẫn nội tuyến có thể mở nguồn.
- Ảnh đã chèn kèm chú thích nguồn.
- Tab **Nguồn & tài liệu tham khảo** hiển thị nguồn đã dùng, độ tin cậy, các mục đang trích dẫn nguồn đó và trạng thái URL.
- Tab **Thư viện ảnh** chứa bản ảnh đã tải về cùng metadata nguồn.
- Cảnh báo rõ cho phần không đủ bằng chứng, thay vì viết khẳng định không có nguồn.

## 5. Kiến trúc

Luồng mới mở rộng `AgenticReportOrchestrator` hiện có thành pipeline theo trạng thái. Mỗi giai đoạn có đầu vào, đầu ra và dữ liệu kiểm chứng riêng để có thể chạy lại an toàn.

```text
Request Intake
  -> Template Profile
  -> Research Plan
  -> Source Discovery and Validation
  -> Claim-Source Ledger
  -> Grounded Section Drafting
  -> Image Discovery and Import
  -> Citation and Bibliography Assembly
  -> Integrity Gate
  -> Export and Studio Review
```

### 5.1 Bộ phân tích mẫu

Bộ đọc DOCX hiện có được mở rộng để tạo `TemplateProfile` gồm:

- Cây heading và thứ tự các phần.
- Các phần bắt buộc và vị trí của chúng.
- Quy tắc font, cỡ chữ, lề, đánh số, header/footer và bảng.
- Kiểu trích dẫn nhận diện được từ trích dẫn nội tuyến và danh mục tham khảo mẫu.
- Vị trí dành cho ảnh, bảng và chú thích.
- Các đoạn hướng dẫn trình bày trong mẫu.

Nội dung mẫu không được dùng như dữ kiện nghiên cứu. Placeholder, số liệu minh họa và nội dung mẫu phải bị loại khỏi factual context.

Nếu mẫu không có phần bắt buộc, `TemplateProfile` tạo các điểm chèn bổ sung theo phong cách gần nhất trong mẫu.

### 5.2 Bộ lập kế hoạch nghiên cứu

`ResearchPlan` chia đề tài thành câu hỏi theo từng mục. Mỗi câu hỏi có:

- Mục báo cáo đích.
- Loại dữ kiện cần tìm.
- Từ khóa tiếng Việt và tiếng Anh.
- Loại nguồn ưu tiên.
- Mức độ mới cần thiết của thông tin.
- Yêu cầu ảnh minh họa nếu có.

Thông tin thay đổi theo thời gian như luật, giá, thị phần, chức danh, thông số sản phẩm và thống kê phải được đánh dấu cần nguồn mới. Kiến thức nền ổn định có thể dùng tài liệu học thuật hoặc tiêu chuẩn gốc.

### 5.3 Tìm kiếm và đánh giá nguồn

`SourceDiscoveryService` sử dụng công cụ nghiên cứu hiện có và chuẩn hóa mọi kết quả về một hợp đồng chung:

```text
SourceCandidate
- canonical_url
- title
- author_or_organization
- publisher
- published_at
- accessed_at
- source_type
- language
- excerpt
- retrieval_status
- trust_score
- relevance_score
- freshness_score
```

Nguồn được xếp hạng theo thứ tự ưu tiên:

1. Văn bản pháp luật, cơ quan nhà nước, tiêu chuẩn và tài liệu chính thức.
2. Nghiên cứu gốc, tạp chí học thuật, trường đại học và tổ chức chuyên môn.
3. Báo chí uy tín và báo cáo ngành có tác giả/nhà xuất bản rõ ràng.
4. Trang chính thức của doanh nghiệp hoặc sản phẩm cho dữ kiện về chính đối tượng đó.
5. Blog và trang tổng hợp khi không có nguồn tốt hơn.

Nguồn bị loại khi URL không truy cập được, tiêu đề không khớp nội dung, ngày/tác giả bị bịa, nội dung không hỗ trợ luận điểm hoặc nhiều trang chỉ sao chép cùng một nguồn gốc.

### 5.4 Sổ liên kết luận điểm và nguồn

Trước khi viết, pipeline tạo `ClaimSourceLedger`. Mỗi mục chứa:

```text
ClaimEvidence
- claim_id
- section_id
- planned_claim
- source_ids
- supporting_excerpts
- confidence
- citation_required
- verification_status
```

Writing Engine chỉ được phát biểu một nhận định cụ thể khi ledger cung cấp bằng chứng phù hợp. Các đoạn phân tích hoặc khuyến nghị do AI suy luận phải được ghi là phân tích dựa trên các nguồn liên quan, không giả thành dữ kiện từ nguồn.

Khi hai nguồn mâu thuẫn, báo cáo nêu rõ khác biệt và thời điểm của từng nguồn. Không được âm thầm chọn con số thuận tiện hơn.

### 5.5 Viết báo cáo có căn cứ

Mỗi mục được tạo từ bốn lớp ngữ cảnh:

1. Yêu cầu của người dùng.
2. `TemplateProfile` và mục tiêu độ dài.
3. Dữ liệu/tài liệu riêng đã tải lên.
4. Các `ClaimEvidence` được duyệt tự động cho đúng mục đó.

Writing Engine trả về nội dung có marker trích dẫn ổn định theo `source_id`, không tự viết chuỗi tài liệu tham khảo. Bộ dựng trích dẫn chịu trách nhiệm chuyển marker sang APA, IEEE hoặc kiểu của mẫu.

Phần tài liệu tham khảo không được soạn tự do bằng mô hình. Nó được dựng có tính quyết định từ metadata của những `source_id` thực sự xuất hiện trong nội dung.

### 5.6 Ảnh web

`ImagePlanningService` quyết định mục nào cần ảnh dựa trên nội dung và loại báo cáo. Mỗi yêu cầu ảnh có truy vấn, mục đích minh họa, chú thích dự kiến và vị trí chèn.

Luồng ảnh tái sử dụng `ImageService` hiện có:

1. Tìm ứng viên qua Openverse và các trang công khai được hỗ trợ.
2. Đánh giá độ liên quan giữa ảnh, truy vấn và mục báo cáo.
3. Loại ảnh quá nhỏ, lỗi tải, trùng checksum hoặc không phải định dạng ảnh hợp lệ.
4. Tải ảnh về kho dự án; không hotlink ảnh từ xa trong tài liệu.
5. Lưu URL ảnh, URL trang nguồn, tên miền, tiêu đề, tác giả và giấy phép nếu có.
6. Chèn node ảnh vào `content_json` của đúng mục, kèm alt text và chú thích nguồn.

Nếu không có ảnh đủ liên quan, mục đó không có ảnh. Pipeline không chèn ảnh chỉ để đạt số lượng.

### 5.7 Trích dẫn và tài liệu tham khảo

`CitationStyleResolver` chọn kiểu theo thứ tự:

1. Kiểu nhận diện từ mẫu.
2. Kiểu người dùng ghi rõ trong yêu cầu.
3. Kiểu mặc định theo loại báo cáo.

`BibliographyBuilder` nhận danh sách nguồn đã trích dẫn và tạo:

- Trích dẫn nội tuyến.
- Danh mục tài liệu tham khảo không trùng lặp.
- Liên kết từ trích dẫn tới nguồn trong Studio.
- Metadata xuất DOCX/PDF/HTML.

Nguồn thiếu tác giả hoặc ngày được định dạng theo quy tắc chính thức của chuẩn tương ứng; hệ thống không tự tạo tác giả hoặc ngày.

### 5.8 Cổng kiểm tra cuối

`ReportIntegrityGate` chạy trước khi đánh dấu hoàn thành:

- Mọi citation marker đều trỏ tới nguồn tồn tại.
- Mọi nguồn trong danh mục được trích dẫn ít nhất một lần.
- Không có URL giả hoặc URL placeholder.
- Các nhận định có số liệu, ngày, luật hoặc so sánh quan trọng có nguồn.
- Không có ảnh hotlink; mọi ảnh có asset nội bộ và URL nguồn.
- Heading và phần bắt buộc phù hợp `TemplateProfile`.
- Không còn marker nội bộ như `[[IMAGE:...]]` hoặc citation token chưa dựng.

Lỗi nghiêm trọng làm job chuyển sang `needs_attention` thay vì báo hoàn thành giả. Lỗi ảnh đơn lẻ hoặc metadata phụ tạo cảnh báo và cho phép hoàn thành.

## 6. Dữ liệu và trạng thái job

Job tự động cần lưu checkpoint sau mỗi giai đoạn để tiếp tục khi tiến trình bị gián đoạn. `metadata_json` của job/report lưu phiên bản schema cho:

- `template_profile`
- `research_plan`
- `source_candidates`
- `claim_source_ledger`
- `image_plan`
- `citation_style`
- `integrity_result`

Các nguồn đã chọn tiếp tục dùng model `Source`; ảnh dùng `ImageAsset`; nội dung dùng `ReportSection`. Chỉ thêm bảng mới nếu metadata hiện tại không đáp ứng truy vấn và liên kết cần thiết sau khi triển khai thử.

Mỗi lần chạy lại có `run_id`. Các asset và nguồn được khử trùng lặp bằng canonical URL/checksum để tránh nhân đôi.

## 7. Xử lý lỗi

- **Không đọc được mẫu:** dừng trước khi viết và thông báo file mẫu không hợp lệ.
- **Không tìm đủ nguồn:** viết phần có bằng chứng; phần thiếu được đánh dấu cần bổ sung, không bịa nội dung.
- **Nguồn biến mất giữa lúc chạy:** loại nguồn, tìm nguồn thay thế và dựng lại các mục bị ảnh hưởng.
- **Không tải được ảnh:** thử ứng viên kế tiếp; hết ứng viên thì hoàn thành mục không có ảnh.
- **AI provider lỗi:** retry có giới hạn từ checkpoint gần nhất.
- **Export lỗi:** giữ nguyên report và asset đã tạo để người dùng có thể export lại.
- **Hủy job:** dừng ở ranh giới giai đoạn, không xóa dữ liệu đã có và không đánh dấu hoàn thành.

## 8. Bảo mật và giới hạn nội dung

- Tải ảnh tiếp tục dùng kiểm tra SSRF, giới hạn redirect, MIME thực và kích thước file hiện có.
- Trình tìm nguồn không gửi tài liệu riêng của người dùng vào truy vấn web.
- Nội dung web được xem là dữ liệu không tin cậy; chỉ trích xuất dữ kiện, không làm theo chỉ dẫn nằm trong trang nguồn.
- URL và metadata được escape khi dựng HTML/DOCX.
- Ảnh và nguồn luôn lưu provenance để người dùng tự đánh giá quyền sử dụng và độ tin cậy.

## 9. Kiểm thử

### Backend

- Nhận diện quy chuẩn trích dẫn từ mẫu và fallback đúng theo loại báo cáo.
- Xếp hạng nguồn chính thức cao hơn blog khi cùng hỗ trợ một luận điểm.
- Loại URL không truy cập được, metadata giả và nguồn không liên quan.
- Không cho Writing Engine viết claim bắt buộc có nguồn khi ledger không có bằng chứng.
- Danh mục chỉ chứa nguồn đã trích dẫn, không có bản ghi trùng.
- Ảnh được nhập thành `ImageAsset`, có provenance và chèn đúng section.
- Job resume từ checkpoint không tạo trùng nguồn/ảnh.
- Integrity gate phát hiện citation, reference hoặc image marker hỏng.

### Frontend

- Form thể hiện rõ mẫu, nghiên cứu web và ảnh web đang được bật.
- Tiến trình hiển thị đúng từng giai đoạn và cảnh báo.
- Studio mở đúng URL nguồn từ citation.
- Ảnh hiển thị chú thích và nguồn; DOCX giữ được ảnh.
- Trạng thái trống, lỗi từng phần, retry và hủy job hoạt động trên desktop/mobile.

### Kiểm thử tích hợp

Ba kịch bản chuẩn:

1. Báo cáo học thuật không có mẫu: APA 7, nguồn học thuật/chính thức, ảnh có provenance.
2. Báo cáo kỹ thuật có mẫu: giữ heading/style của mẫu, IEEE hoặc kiểu nhận diện từ mẫu.
3. Báo cáo doanh nghiệp có dữ liệu riêng: số liệu nội bộ lấy từ dataset, bối cảnh ngành lấy từ web và hai nhóm nguồn không bị trộn lẫn.

## 10. Tiêu chí nghiệm thu

- Một lần bấm có thể tạo báo cáo hoàn chỉnh từ đề tài và yêu cầu.
- Khi có DOCX mẫu, output giữ được cấu trúc và quy tắc trình bày chính của mẫu.
- Mỗi trích dẫn mở được nguồn thật hoặc được đánh dấu lỗi trước khi hoàn thành.
- Không có tài liệu tham khảo do AI tự bịa.
- Danh mục tài liệu tham khảo khớp với trích dẫn nội tuyến.
- Ảnh được lưu trong dự án, hiển thị trong Studio và tồn tại trong file xuất.
- Mọi ảnh có URL trang nguồn; metadata tác giả/giấy phép được lưu khi nhà cung cấp có dữ liệu.
- Báo cáo không chèn ảnh không liên quan chỉ để đủ số lượng.
- Người dùng có thể xem cảnh báo và chạy lại từ giai đoạn lỗi mà không tạo dự án mới.

## 11. Thứ tự triển khai

1. Chuẩn hóa hợp đồng `TemplateProfile`, nguồn và ledger.
2. Bổ sung research plan, xếp hạng nguồn và checkpoint job.
3. Grounded drafting với citation marker ổn định.
4. Bibliography builder và integrity gate.
5. Image planning, tự động nhập/chèn ảnh và provenance.
6. UI tiến trình, nguồn, ảnh và cảnh báo.
7. Kiểm thử tích hợp và bật dần cho chế độ tạo tự động.
