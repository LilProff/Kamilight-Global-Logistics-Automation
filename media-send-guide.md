# Media Send Guide — WhatsApp Broadcast

## The Problem

When admin sends an image/video/document/audio in Telegram, n8n receives a `file_id`.
WhatsApp cannot download from Telegram directly.
We need to: download from Telegram → upload to WhatsApp → send with the WhatsApp media_id.

---

## The 3-Node Pattern (Use for every media type)

Implement this chain in n8n for EACH media type (photo, video, document, audio):

### Node A — Get File Path from Telegram

```
Type: HTTP Request
Method: GET
URL: https://api.telegram.org/botYOUR_BOT_TOKEN/getFile?file_id={{ $json.fileId }}
```

Response contains:
```json
{ "result": { "file_path": "photos/file_123.jpg" } }
```

---

### Node B — Download Binary from Telegram

```
Type: HTTP Request
Method: GET
URL: https://api.telegram.org/file/botYOUR_BOT_TOKEN/{{ $json.result.file_path }}
Response Format: file (binary)
```

This gives you the raw binary data of the image/video/document.

---

### Node C — Upload Binary to WhatsApp Media API

```
Type: HTTP Request
Method: POST
URL: https://graph.facebook.com/v18.0/YOUR_PHONE_NUMBER_ID/media
Content-Type: multipart/form-data
Fields:
  - messaging_product: whatsapp
  - type: image/jpeg   (or video/mp4, application/pdf, audio/ogg, etc.)
  - file: [binary from Node B]
Credentials: WhatsApp Cloud API (HTTP Header Auth)
```

Response:
```json
{ "id": "123456789012345" }
```

This `id` is your **WhatsApp Media ID**. Save it.

---

### Node D — Send Message with Media ID

```json
{
  "messaging_product": "whatsapp",
  "recipient_type": "individual",
  "to": "{{ $json.phone }}",
  "type": "image",
  "image": {
    "id": "{{ $('Node C').first().json.id }}",
    "caption": "{{ $json.mediaCaption }}"
  }
}
```

---

## MIME Types by Content Type

| Telegram Type | WhatsApp `type` field | MIME Type |
|---|---|---|
| photo | image | image/jpeg |
| video | video | video/mp4 |
| document (PDF) | document | application/pdf |
| document (Word) | document | application/vnd.openxmlformats-officedocument.wordprocessingml.document |
| audio/voice | audio | audio/ogg; codecs=opus |

---

## Optimization: Upload Once, Send to All

For broadcast to many contacts, **do not upload the file inside the loop**.

**Wrong order:**
```
Loop contacts → [upload media → send message] × N contacts
```

**Correct order:**
```
Upload media ONCE → get media_id → Loop contacts → [send with media_id] × N contacts
```

In n8n: place the 3-node upload pattern BEFORE the Split in Batches / loop node.
Pass the `media_id` through the loop as a fixed value.

This saves time and avoids re-uploading the same file hundreds of times.

---

## WhatsApp Media Limits

| Type | Max Size |
|------|----------|
| Image | 5 MB |
| Video | 16 MB |
| Document | 100 MB |
| Audio | 16 MB |

---

## Supported Image Formats

JPEG, PNG, WEBP. JPEGs work best for flyers.

---

## Caption Support

| Type | Caption Supported? |
|------|-------------------|
| image | ✅ Yes |
| video | ✅ Yes |
| document | ✅ Yes |
| audio | ❌ No |
| text | N/A |
