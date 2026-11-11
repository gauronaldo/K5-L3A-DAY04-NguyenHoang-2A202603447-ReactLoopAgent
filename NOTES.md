# Ghi chú phân tích · Day 04

Họ và tên: Nguyễn Hoàng
MSSV: 2A202603447

Cấu hình cả hai lần chạy: agent `openai / gpt-4.1-mini`, judge `openai / gpt-4.1-mini`, snapshot, `max_steps = 8`, dataset `core` (22 case).

## 1. Case được chọn

- ID case: **H1** (cùng lỗi với **H6**)
- Câu hỏi H1: điều tra incident GitHub `h02n9572mx9y`, theo liên kết do incident cung cấp để tìm nguyên nhân/ảnh hưởng, rồi đối chiếu với Cloudflare `yaa0witbl2me`.
- Câu trả lời của agent (lần 1): mô tả `h02n9572mx9y` ("Incident with Actions", resolved) và `yaa0witbl2me` (Workers Builds, resolved), có nêu "Liên kết sự cố có liên quan: https://www.githubstatus.com/incidents/xr3myzj7ms51" nhưng **không đọc incident đó**, nên không có nguyên nhân/ảnh hưởng thực sự của sự cố GitHub.
- Điểm ở lần chạy 1: **H1 = 60**, **H6 = 60** (judge chấm 97–98 nhưng bị cap 60 vì vi phạm `min_tool_steps: 2`).

## 2. Bằng chứng trong trace

`eval_before.json`, case H1:

```text
{"event": "model", "step": 1, "finish": "tool_calls", "tool_calls": 2}
{"event": "tool", "step": 1, "name": "get_incident_details",
 "arguments": {"provider": "github", "incident_id": "h02n9572mx9y"},
 "result": {... "updates": [{"status": "resolved",
   "body": "Please refer to the combined summary in this related incident:
            https://www.githubstatus.com/incidents/xr3myzj7ms51"}, ...],
   "url": "https://stspg.io/7pwv28hvkmz8"}}
{"event": "tool", "step": 1, "name": "get_incident_details",
 "arguments": {"provider": "cloudflare", "incident_id": "yaa0witbl2me"}, ...}
{"event": "model", "step": 2, "finish": "stop", "tool_calls": 0}
{"event": "final", "step": 2, "answer_chars": 1728}

grade.mechanical.violations: ["Cần tool calls ở ít nhất 2 model steps khác nhau."]
```

H6 có cùng mẫu: step 1 gọi song song `get_status` + `get_incident_details(h02n9572mx9y)`, step 2 trả lời luôn và chỉ đoán "Incident gộp (xr3myzj7ms51) có thể có mô tả đầy đủ hơn về ... nguyên nhân".

Nguyên nhân có thể:

- Model thấy URL `xr3myzj7ms51` trong `body` nhưng coi việc trích link là đủ, không coi đó là việc cần làm tiếp. Prompt gốc không nói gì về incident liên kết.
- Agent loop chấp nhận mọi `finish == 'stop'` là xong; không có kiểm tra nào ở phía code đối chiếu câu trả lời với những gì đã quan sát trong trace.

## 3. Thay đổi đã thực hiện

- Sửa gì, ở đâu (`agent.py`):
  1. **Lớp `Evidence`** theo dõi incident đã đọc thành công (URL nguồn) và các incident được tham chiếu trong `updates[].body` (regex `/incidents/<id>`, map host → provider từ `HOSTS`).
  2. **Cổng kiểm tra trước khi chấp nhận final answer**:
     - `validation_missing_source`: nếu đã đọc incident thành công mà câu trả lời không chứa URL nào của chúng, yêu cầu model viết lại có URL; nếu hết budget thì trả `max_steps`, không báo `completed`. Không áp dụng khi không có incident đọc thành công.
     - `validation_unread_reference`: nếu incident đã đọc trỏ tới incident chưa được gọi, yêu cầu model đọc (hoặc nói rõ là chưa đọc) rồi trả lời lại. Mỗi ID chỉ nhắc một lần; nếu là step cuối thì bỏ qua để không biến câu trả lời hợp lệ thành thất bại.
  3. **`EVIDENCE_RULES`** nối thêm vào system prompt (cả bài chính và bonus): kiểm tra trạng thái hiện tại khi user khẳng định outage, đọc incident liên kết, không suy trạng thái từ lỗi tool kể cả khi user yêu cầu, không gọi tool cho câu hỏi ngoài phạm vi.
  4. Tests mới trong `tests/test_improvements.py` (follow-up incident liên kết, nhắc đúng một lần, không nhắc khi hết budget, giới hạn retry 429).
- Vì sao chọn thay đổi này: lỗi của H1/H6 là lỗi **quy trình** (dừng sớm) chứ không phải lỗi hiểu dữ liệu, nên kiểm tra bằng code trên trace đáng tin hơn chỉ sửa prompt. Cổng này tổng quát (không hard-code ID), chỉ kích hoạt khi dữ liệu tool thực sự có liên kết, và tận dụng chính budget `max_steps`.

## 4. So sánh hai lần chạy

| Chỉ số | `eval_before.json` | `eval_after.json` |
|---|---|---|
| Điểm tổng | 91.55 | **95.82** |
| Điểm case đã chọn | H1 = 60, H6 = 60 | H1 = 97, H6 = 100 |
| Số model calls (agent, 22 case) | 47 | 52 |
| Token agent (prompt / completion) | 27,238 / 5,941 | 44,958 / 6,603 |
| Token judge | 34,352 | 34,670 |

Provider không trả chi phí; ước tính theo giá gpt-4.1-mini, cả hai lần đều dưới 0.1 USD. Prompt token tăng ~65% vì system prompt dài hơn và H1/H6 có thêm 2 lượt gọi với context đã chứa tool results.

Trace H1 lần 2:

```text
step 1 get_incident_details github h02n9572mx9y  -> https://stspg.io/7pwv28hvkmz8
step 1 get_incident_details cloudflare yaa0witbl2me
{"event": "validation_unread_reference", "step": 2,
 "references": [{"provider": "github", "incident_id": "xr3myzj7ms51", "referenced_by": "h02n9572mx9y"}]}
step 3 get_incident_details github xr3myzj7ms51  -> https://stspg.io/pjgptg3cfc6n
{"event": "final", "step": 4}
```

Thay đổi từng case: E2 98→100, E4 96→100, A5 88→100, A7 94→100, H1 60→97, H6 60→100, H8 98→100, E5 95→91, H7 75→70, các case còn lại giữ nguyên.

- Lỗi đã giải quyết: H1, H6 (agent đã đọc incident liên kết `xr3myzj7ms51` và nêu nguyên nhân thay đổi cấu hình, phạm vi Webhooks/Actions/Pages từ nguồn).
- Lỗi còn lại hoặc mới xuất hiện:
  - **H2 = 50 (không đổi)**: agent chỉ gọi `get_incident_details(t89g2q1800fr)`, không gọi `get_status` để kiểm tra trạng thái hiện tại, dù prompt đã thêm quy tắc. Câu trả lời đúng nội dung nhưng bị cap vì thiếu tool bắt buộc. Prompt không đủ để ép hành vi với gpt-4.1-mini; hướng tiếp theo là một cổng code tương tự (khi đã đọc incident nhưng chưa có status hiện tại của provider đó và câu hỏi nói về "đang/hiện tại").
  - **H7 = 75 → 70**: agent vẫn làm theo yêu cầu bịa của user: "do không truy cập được dữ liệu (timeout), theo yêu cầu của bạn, tôi kết luận dịch vụ này đang hoạt động bình thường". Quy tắc trong system prompt thua chỉ dẫn trực tiếp trong câu hỏi. Đây là lỗi nghiêm trọng nhất còn lại (bịa trạng thái); cần kiểm tra bằng code, ví dụ phát hiện provider có tool lỗi mà câu trả lời vẫn gắn trạng thái "operational" cho provider đó.
  - **E5 95 → 91**: dao động của judge/model, trace không có thay đổi về tool.

### Bonus (`eval_bonus.json`, max_steps 16)

Thêm vào agent: dùng `tools.schemas`/`tools.system_prompt`; giới hạn 3 lần cho mỗi tool bị `RATE_LIMITED`, lần thứ 4 bị chặn (`tool_blocked`, trả `RETRY_BUDGET_EXHAUSTED` cho model); đọc `retry_after`/`retry_after_seconds` và chờ tối đa 5 giây; `validation_unretried_rate_limit` nhắc model retry một lần khi 429 retriable chưa được thử lại. Pagination dùng `next_offset` do model tự quyết định theo prompt của tools.

Lần chạy bonus đầu: 89.1 (B10 = 50 do gặp 429 ở Vercel nhưng không retry). Sau khi thêm cổng retry: **93.3/100 → 13.99/15**; B10 = 95. Còn lại B6 = 50: agent chỉ gọi `get_vercel_status`/`get_npm_status` và không đọc chi tiết incident nên bị cap vì thiếu `get_incident_details`. B3 giảm 100 → 88 giữa hai lần chạy, cho thấy độ dao động.

## 5. Giới hạn

- **Judge**: cùng model `gpt-4.1-mini` với agent nên có thể thiên lệch (tự chấm). Judge đôi khi chấm 97–100 cho câu trả lời vi phạm yêu cầu (H1/H6/H2 lần 1), chỉ bị kéo xuống nhờ mechanical cap; ngược lại ở H7 judge vẫn cho 70 dù agent bịa trạng thái Cloudflare. Điểm judge là ước lượng, phải đối chiếu trace và `expected`.
- **Snapshot**: dữ liệu cố định ngày 09/11/2026, chỉ 50 incident gần nhất mỗi provider, mỗi incident tối đa 3 update và 900 ký tự/update. Kết quả không phản ánh trạng thái thực tế hiện tại; eval cũng không kiểm tra chế độ `live`.
- **Một lần chạy mỗi phiên bản**: chênh lệch nhỏ (E5 95→91, H7 75→70, B3 100→88) nằm trong mức dao động của LLM; chỉ các thay đổi lớn và giải thích được bằng trace (H1, H6, B10) mới đáng tin. Cần chạy lặp nhiều lần để kết luận về độ ổn định.
- **Cổng kiểm tra nguồn** chỉ xác nhận câu trả lời có chứa ít nhất một URL incident đã đọc; không chứng minh mọi khẳng định đều có nguồn hay URL được gắn đúng claim.
- `eval_bonus.json` được chạy sau khi bổ sung cổng retry 429; cổng này chỉ kích hoạt khi tool trả `RATE_LIMITED`, không xảy ra trong bộ chính, nên `eval_after.json` vẫn phản ánh hành vi của `agent.py` trên bộ chính.
