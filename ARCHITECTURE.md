# L3A Architecture Record

## 1. System overview

Mô tả luồng từ `inputs/<case_id>.json` đến MCP calls, specialist agents, verifier, output và trace:

```text
Input JSON (Case, Claims)
       │
       ▼
  Coordinator ─────────── (task_assigned) ──────────┐
       │                                            │
       ├────────────────┬────────────────┐          │
       ▼                ▼                ▼          ▼
   Order Agent    Payment Agent   Shipment Agent  Policy Agent
   (get_order,    (get_payments,  (get_shipment)  (get_policy)
    get_items,     get_timeline,
    get_sellers)   get_refund)
       │                │                │          │
 (tool_result_    (tool_result_    (tool_result_  (tool_result_
   consumed)        consumed)        consumed)      consumed, policy_decided)
       │                │                │          │
       └──────── (handoff to coordinator) ──────────┘
                        │
                        ▼
                   Coordinator (Synthesize & Map Evidence)
                        │
                  (handoff)
                        ▼
                    Verifier (verification_completed)
                        │
                        ▼
                Output JSON & Trace
```

## 2. Agent ownership

| Actor | Input | Trách nhiệm | Output/handoff | Tool được gọi |
| --- | --- | --- | --- | --- |
| **Coordinator** | `inputs/<case_id>.json` | Phân công nhiệm vụ, tổng hợp kết quả từ các specialist, liên kết evidence vào claim và chuyển giao verifier | Handoff sang Specialists / Verifier | Không gọi tool trực tiếp |
| **Order Agent** | `order_id` | Thu thập dữ liệu đơn hàng, sản phẩm, và thông tin người bán | `ORDER_EVIDENCE_PROVIDED` | `get_order`, `get_order_items`, `get_sellers` |
| **Payment Agent** | `order_id` | Xác minh timeline thanh toán, lịch sử giao dịch và đối soát refund | `PAYMENT_EVIDENCE_PROVIDED` | `get_order_payments`, `get_payment_timeline`, `get_refund_timeline` |
| **Shipment Agent** | `order_id` | Kiểm tra thời gian giao hàng, hạn giao cam kết, trạng thái vận chuyển và bên gây trễ | `SHIPMENT_EVIDENCE_PROVIDED` | `get_shipment_summary` |
| **Policy Agent** | `policy_version`, primary issue | Tra cứu điều khoản chính sách giải quyết khiếu nại (bồi hoàn, trách nhiệm) | `POLICY_RECOMMENDATION_PROVIDED` | `get_policy` |
| **Verifier** | Aggregated result dictionary | Kiểm tra tính nhất quán giữa các trường, kiểm tra JSON Schema V2 và các bất biến nghiệp vụ | `VERIFICATION_PASSED` | Không gọi tool |

## 3. A2A protocol

- **Message envelope**: Các sự kiện trao đổi và phối hợp giữa các agent được định dạng theo JSON Schema `day09-trace-event-v1`.
- **Correlation**: Mỗi event đều được gán `case_id` chính xác nhằm tránh việc trộn lẫn dữ liệu giữa các case.
- **Handoff condition**: Khi mỗi specialist agent hoàn thành thu thập dữ liệu và tiêu thụ kết quả (`tool_result_consumed`), agent phát hành sự kiện `handoff` trả về cho `coordinator`.
- **Trace transparency**: Chỉ trace các sự kiện vòng đời quan sát được (`case_received`, `task_assigned`, `tool_result_consumed`, `handoff`, `policy_decided`, `verification_completed`, `case_finalized`), không lưu prompt bí mật hay chain-of-thought nội bộ.

## 4. Evidence lifecycle

1. **Validation**: Mọi phản hồi từ MCP server được validate thông qua schema `day09-mcp-evidence-v1`.
2. **Collection & Provenance**: Lưu trữ `evidence_ref` gốc từ gateway; tuyệt đối không tạo mã giả hoặc tự sinh `evidence_ref`.
3. **Trace emission**: Mỗi lần kết quả tool được sử dụng, emit `tool_result_consumed` với `actor`, `tool_name` và danh sách `evidence_refs`.
4. **Linkage**: Đưa các `evidence_refs` tương ứng vào từng đánh giá `claim_assessments` và danh sách tổng thể `evidence_refs` của output.
5. **Isolation**: Mỗi phiên chạy và mỗi case duy trì danh sách evidence độc lập, không tái sử dụng xuyên case.

## 5. Failure policy

| Failure | Retry? | Fallback | Trace event/code |
| --- | --- | --- | --- |
| **MCP timeout** | Có (tối đa 2 lần với backoff) | Ghi nhận lỗi và chuyển case_status sang `needs_investigation` | `MCP_CALL_TIMEOUT` |
| **Not found** | Không retry nếu 404 hợp lệ | Đặt verdict là `unsupported` hoặc `insufficient_evidence` | `ENTITY_NOT_FOUND` |
| **Source conflict** | Không | Ghi nhận vào mảng `data_conflicts` theo schema chuẩn | `DATA_CONFLICT_LOGGED` |
| **Invalid specialist result** | Có (1 lần) | Fallback về trạng thái `needs_investigation` an toàn | `FALLBACK_TRIGGERED` |

## 6. Verification invariants

Trước khi xuất file kết quả cuối cùng, Verifier đảm bảo các bất biến sau:
1. **Schema Compliance**: Tuân thủ 100% JSON Schema `day09-l3a-output-v2`.
2. **Entity Scope**: Các entity IDs (`order_ids`, `item_ids`, `seller_ids`, `payment_references`) phải thuộc về chính case đó.
3. **Evidence Ownership**: Toàn bộ `evidence_refs` trong output phải xuất hiện trong trace thông qua `tool_result_consumed`.
4. **Money Totals Consistency**: `recommended_refund_brl` trong `financial_resolution` phải bằng đúng tổng `amount_brl` trong `refund_lines`.
5. **Responsibility & Action Consistency**: Bên chịu trách nhiệm (`responsible_parties`) và hành động (`resolution_actions`) phải khớp với quy định trong policy.
6. **Unique Items**: Không có trùng lặp trong `resolution_actions` và `evidence_refs`.

## 7. Reproducibility

- **Runtime**: Python >= 3.11
- **Dependencies**: `httpx2>=2,<3`, `mcp>=2,<3`, `jsonschema>=4.25,<5`, `python-dotenv>=1.1,<2`
- **Execution**: Thực thi thông qua CLI chuẩn `day09 run`, kiểm tra qua `day09 validate`, đóng gói qua `day09 package --output dist/submission.zip`.
