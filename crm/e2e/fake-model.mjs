// A stand-in for the Anthropic API, used only by the end-to-end test. Same request/response shape, scripted answers:
//   - a message about price/quote/ship  -> logs a quote request (tool call), then says a colleague will confirm
//   - a message that gives details      -> saves them on the customer record (tool call), then answers
//   - anything else                     -> a plain friendly reply
// Listens on :8787.  node fake-model.mjs
import http from "node:http";

const text = (t) => ({ type: "text", text: t });
const tool = (name, input) => ({ type: "tool_use", id: "tu_" + name, name, input });
const reply = (res, content, stop) => {
  res.writeHead(200, { "content-type": "application/json" });
  res.end(JSON.stringify({ content, stop_reason: stop, usage: { input_tokens: 120, output_tokens: 30 } }));
};

http.createServer((req, res) => {
  let raw = "";
  req.on("data", (c) => (raw += c));
  req.on("end", () => {
    if (req.method !== "POST" || !req.url.startsWith("/v1/messages")) { res.writeHead(404).end(); return; }
    const body = JSON.parse(raw || "{}");
    const last = body.messages[body.messages.length - 1];
    const wantsDraft = !body.tools; // campaign draft calls carry no tools
    if (wantsDraft) return reply(res, [text("Hi {first_name}, shipping from China this month? Reply and we will help you book.")], "end_turn");
    if (Array.isArray(last.content) && last.content[0]?.type === "tool_result") {
      return reply(res, [text("Thank you! A colleague will confirm the exact details shortly.")], "end_turn");
    }
    const said = String(last.content).toLowerCase();
    if (/price|quote|how much|cost/.test(said)) {
      return reply(res, [tool("request_quote", { route: "China to Lagos", goods: "phones", size: "2 cartons", mode: "air" })], "tool_use");
    }
    if (/i am|i'm|my name/.test(said)) {
      return reply(res, [tool("update_customer", { city: "Ikeja", goods: "fabrics", preferred_mode: "sea" })], "tool_use");
    }
    if (/human|person|agent/.test(said)) {
      return reply(res, [tool("request_human", { reason: "Customer asked to speak to a person" })], "tool_use");
    }
    return reply(res, [text("Hello! I'm KGL's assistant. How can I help with your shipping today?")], "end_turn");
  });
}).listen(8787, () => console.log("fake model on :8787"));
