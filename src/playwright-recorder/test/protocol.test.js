import assert from "node:assert/strict";
import { test } from "node:test";
import { MAX_MESSAGE_BYTES, ProtocolError, parseClientMessage, validateTargetUrl } from "../protocol.js";
test("accepts supported messages and canonicalizes HTTP URLs", () => {
    assert.deepEqual(parseClientMessage('{"type":"session.start","url":"https://example.com/path"}'), {
        type: "session.start",
        url: "https://example.com/path",
    });
    assert.deepEqual(parseClientMessage(JSON.stringify({
        type: "input.pointer",
        phase: "down",
        x: 1280,
        y: 720,
        button: "left",
        clickCount: 1,
    })), { type: "input.pointer", phase: "down", x: 1280, y: 720, button: "left", clickCount: 1 });
    assert.deepEqual(parseClientMessage('{"type":"input.text","text":"ação 🚀"}'), {
        type: "input.text",
        text: "ação 🚀",
    });
    assert.deepEqual(parseClientMessage('{"type":"input.select","selectId":7,"index":2}'), {
        type: "input.select",
        selectId: 7,
        index: 2,
    });
    assert.deepEqual(parseClientMessage('{"type":"input.select","selectId":7,"index":null}'), {
        type: "input.select",
        selectId: 7,
        index: null,
    });
    assert.deepEqual(parseClientMessage('{"type":"input.hover.clear"}'), { type: "input.hover.clear" });
    assert.deepEqual(parseClientMessage('{"type":"script.run","steps":"await page.reload();"}'), {
        type: "script.run",
        steps: "await page.reload();",
    });
});
test("rejects malformed URLs, schemes, JSON, unknown types, limits, and invalid numbers", () => {
    for (const url of ["not a url", "file:///tmp/a", "data:text/plain,x", "javascript:alert(1)"])
        assert.throws(() => validateTargetUrl(url), (error) => hasCode(error, "INVALID_URL"));
    const invalidMessages = [
        "{",
        "[]",
        '{"type":"unknown"}',
        '{"type":"input.pointer","phase":"move","x":-1,"y":0}',
        '{"type":"input.pointer","phase":"down","x":1,"y":1,"clickCount":0}',
        '{"type":"input.wheel","deltaX":0,"deltaY":10001}',
        '{"type":"input.key","phase":"down","key":"a","modifiers":["Control","Control"]}',
        '{"type":"input.select","selectId":0,"index":1}',
        '{"type":"input.select","selectId":1,"index":200}',
        '{"type":"script.run","steps":"   "}',
    ];
    for (const message of invalidMessages)
        assert.throws(() => parseClientMessage(message), (error) => hasCode(error, "INVALID_MESSAGE"));
    assert.throws(() => parseClientMessage(Buffer.alloc(MAX_MESSAGE_BYTES + 1, 32)), (error) => hasCode(error, "INVALID_MESSAGE"));
});
function hasCode(error, code) {
    return error instanceof ProtocolError && error.code === code;
}
