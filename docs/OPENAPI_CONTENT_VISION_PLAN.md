# OpenAPI Content & Vision Integration Plan

Tai lieu nay ghi lai bo API co the dung ve sau cho:
- viet bai viet bang model text chat
- doc anh / OCR / phan tich anh
- tao anh bang model image chuyen dung

Endpoint dich vu:

```text
https://openapi.vinhyenit.com/v1
```

Mac dinh model text uu tien:

```text
gpt-5.4
```

Luu y:
- Khong commit API key that vao repo.
- Luon dung env var hoac secret manager.

## 1. Cau hinh de xuat

Them env cho backend:

```env
OPENAPI_PROXY_BASE=https://openapi.vinhyenit.com/v1
OPENAPI_PROXY_API_KEY=sk-cliproxy-default-key-123
OPENAPI_PROXY_TEXT_MODEL=gpt-5.4
OPENAPI_PROXY_IMAGE_MODEL=imagen-4.0-fast-generate-001
```

Neu can dung endpoint khac cho image model:

```env
OPENAPI_PROXY_IMAGE_PREDICT_BASE=https://openapi.vinhyenit.com/v1beta/models
```

## 2. Kha nang su dung

### 2.1 Viet bai / viet noi dung

Co the dung `POST /v1/chat/completions` voi model `gpt-5.4` cho:
- viet bai Facebook
- viet bai blog
- viet outline content
- tao CTA
- tao hashtag
- viet caption

Request mau:

```bash
curl https://openapi.vinhyenit.com/v1/chat/completions \
  -H "Authorization: Bearer ${OPENAPI_PROXY_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-5.4",
    "messages": [
      {
        "role": "system",
        "content": "Bạn là content writer tiếng Việt, viết rõ ràng, đúng trọng tâm, giọng văn chuyên nghiệp."
      },
      {
        "role": "user",
        "content": "Hãy viết một bài Facebook khoảng 180 chữ giới thiệu dịch vụ thiết kế landing page cho doanh nghiệp nhỏ. Có tiêu đề ngắn, nội dung chính và lời kêu gọi hành động."
      }
    ],
    "temperature": 0.7
  }'
```

### 2.2 Doc anh / OCR / mo ta anh

Co the dung `POST /v1/chat/completions` voi model `gpt-5.4` theo format `image_url`.

Use case:
- doc noi dung anh de viet caption
- OCR text trong anh
- phan tich anh marketing / landing page / banner
- goi y caption, hook, CTA dua tren anh

Request mau voi URL cong khai:

```bash
curl https://openapi.vinhyenit.com/v1/chat/completions \
  -H "Authorization: Bearer ${OPENAPI_PROXY_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-5.4",
    "messages": [
      {
        "role": "user",
        "content": [
          {
            "type": "text",
            "text": "Hãy mô tả chi tiết bức ảnh này bằng tiếng Việt, sau đó liệt kê 5 điểm đáng chú ý."
          },
          {
            "type": "image_url",
            "image_url": {
              "url": "https://images.unsplash.com/photo-1506744038136-46273834b3fb"
            }
          }
        ]
      }
    ]
  }'
```

Request mau OCR voi base64:

```bash
IMG_BASE64=$(base64 < /path/to/image.jpg | tr -d '\n')

curl https://openapi.vinhyenit.com/v1/chat/completions \
  -H "Authorization: Bearer ${OPENAPI_PROXY_API_KEY}" \
  -H "Content-Type: application/json" \
  -d "{
    \"model\": \"gpt-5.4\",
    \"messages\": [
      {
        \"role\": \"user\",
        \"content\": [
          {
            \"type\": \"text\",
            \"text\": \"Hãy OCR nội dung trong ảnh này, sau đó tóm tắt ý chính bằng tiếng Việt.\"
          },
          {
            \"type\": \"image_url\",
            \"image_url\": {
              \"url\": \"data:image/jpeg;base64,$IMG_BASE64\"
            }
          }
        ]
      }
    ]
  }"
```

### 2.3 Tao anh

Khong dung `gpt-5.4` de tao anh.

Model anh de xuat:
- `imagen-4.0-fast-generate-001`
- `imagen-4.0-generate-001`
- `imagen-4.0-ultra-generate-001`
- `gemini-2.5-flash-image`

Request mau:

```bash
curl https://openapi.vinhyenit.com/v1beta/models/imagen-4.0-fast-generate-001:predict \
  -H "Authorization: Bearer ${OPENAPI_PROXY_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "contents": [
      {
        "parts": [
          {
            "text": "A modern Vietnamese coffee shop interior, cinematic lighting, realistic style"
          }
        ]
      }
    ],
    "aspectRatio": "1:1",
    "sampleCount": 1
  }'
```

Ky vong response:
- co du lieu anh trong base64, thuong o `inlineData.data`

## 3. Huong tich hop de xuat vao du an

Nen tach thanh 2 service rieng:

```text
backend/services/content_generation_proxy.py
backend/services/vision_proxy.py
```

Hoac 1 service chung:

```text
backend/services/openapi_proxy.py
```

Ham de xuat:
- `generate_marketing_copy(...)`
- `generate_facebook_post(...)`
- `analyze_image_url(...)`
- `ocr_image_base64(...)`
- `generate_image_from_prompt(...)`

## 4. Use case trong du an nay

### 4.1 Post automation

Dung cho:
- viet draft bai viet chat luong cao
- viet caption
- viet CTA
- viet outline / hook / version khac nhau

### 4.2 Image-aware content

Dung cho:
- doc anh san pham / banner / poster
- OCR text tren anh
- tao caption tu anh
- goi y y tuong bai viet dua tren anh dau vao

### 4.3 Image generation

Dung cho:
- sinh anh bai post tu prompt
- tao anh minh hoa cho content plan
- tao visual phu hop tung page/template

## 5. Thu tu uu tien khuyen nghi

Nen lam theo thu tu:
1. Text generation qua `gpt-5.4`
2. Vision / OCR qua `gpt-5.4`
3. Image generation qua model anh rieng

Ly do:
- text va vision de tich hop hon
- image generation can them parser/output/storage/publish logic

## 6. Kiem tra model truoc khi dung

Nen goi:

```bash
curl https://openapi.vinhyenit.com/v1/models \
  -H "Authorization: Bearer ${OPENAPI_PROXY_API_KEY}"
```

De verify:
- `gpt-5.4` co san cho text/vision
- model anh co san cho image generation

## 7. Task de xuat cho phase sau

- [ ] Them config env cho OpenAPI proxy.
- [ ] Them service proxy cho text/vision/image.
- [ ] Them helper viet bai bang `gpt-5.4`.
- [ ] Them helper OCR / mo ta anh.
- [ ] Them helper tao anh bang model image rieng.
- [ ] Them test endpoint noi bo de debug API.
- [ ] Noi text generation vao post automation.
- [ ] Noi vision vao workflow phan tich anh / goi y caption.
- [ ] Noi image generation vao workflow tao bai co anh.

## 8. Rui ro can tranh

- [ ] Commit nham API key that vao repo.
- [ ] Gia dinh `gpt-5.4` ho tro image generation.
- [ ] Khong check `/v1/models` truoc khi su dung model moi.
- [ ] Khong normalize response base64/image payload lam vo workflow sau do.
- [ ] Dung vision/OCR trong luong nhay cam ma khong co timeout/fallback.
