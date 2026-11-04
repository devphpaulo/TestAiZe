import assert from "node:assert/strict";
import { test } from "node:test";
import { request } from "node:http";
import { createServer } from "../server.js";
test("embedded worker allows only its configured parent and keeps health browser-free", async () => {
    const recorder = createServer({ parentOrigin: "http://127.0.0.1:51234" });
    const port = await recorder.listen(0);
    try {
        const response = await fetch(`http://127.0.0.1:${port}/?embedded=1`);
        assert.equal(response.status, 200);
        assert.match(response.headers.get("content-security-policy"), /frame-ancestors 'self' http:\/\/127\.0\.0\.1:51234/);
        assert.deepEqual(await (await fetch(`http://127.0.0.1:${port}/health`)).json(), { status: "ok" });
        const hostileStatus = await new Promise((resolve) => {
            const connection = request({ hostname: "127.0.0.1", port, path: "/", headers: { Host: "example.test" } }, (response) => {
                response.resume();
                resolve(response.statusCode);
            });
            connection.end();
        });
        assert.equal(hostileStatus, 403);
    }
    finally {
        await recorder.close();
    }
});
test("parent origin rejects remote hosts, paths and CSP injection", () => {
    for (const parentOrigin of ["https://example.com", "http://127.0.0.1:42/path", "http://localhost:42; evil", "file:///tmp"]) {
        assert.throws(() => createServer({ parentOrigin }));
    }
});
