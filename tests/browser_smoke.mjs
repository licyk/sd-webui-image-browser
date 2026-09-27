// Optional: PLAYWRIGHT_MODULE may point to an installed playwright-core module.
import assert from "node:assert/strict";
const {chromium} = await import(process.env.PLAYWRIGHT_MODULE || "playwright");
const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHROMIUM_PATH || undefined,
    args: ["--no-sandbox"],
});
const base = process.env.HANAIKADA_TEST_URL || "http://127.0.0.1:17867";
const context = await browser.newContext({viewport: {width: 1440, height: 1050}, locale: "en-US"});
const page = await context.newPage();
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));

try {
    assert.equal((await context.request.get(`${base}/hanaikada/_host/status`)).status(), 401);
    const login = await context.request.post(`${base}/login`, {form: {username: "smoke", password: "smoke"}});
    assert.equal(login.status(), 200);
    await page.goto(base);
    const frame = page.frameLocator(".hanaikada-frame");
    await frame.locator("#app").waitFor();
    // The extension pins All folders on, so Browse opens there with the WebUI's output folders.
    await frame.locator('[aria-current="location"]', {hasText: "All folders"}).waitFor();
    await frame.getByText("txt2img-images").first().waitFor();
    const status = await (await context.request.get(`${base}/hanaikada/_host/status`)).json();
    assert.equal(status.combined_view, true);
    assert.equal(await page.locator(".hanaikada-frame").getAttribute("src"), `${base}/hanaikada/#/browse?root=*`);
    assert.equal(await page.locator(".hanaikada-status").isVisible(), false);

    // Open the txt2img folder inside the frame, then save an image the way the WebUI does.
    const inner = page.frames().find((f) => f.url().startsWith(`${base}/hanaikada/`));
    await inner.evaluate((root) => { location.hash = `#/browse?root=${root}&path=outputs/txt2img-images`; }, status.default_root);
    await frame.locator('.cell[title="00000-42.png"]').waitFor();
    await page.getByRole("button", {name: "Simulate save", exact: true}).click();
    await page.waitForFunction(() => document.querySelector("#smoke-saved textarea")?.value === "00001-7.png");
    // The on_image_saved hook indexes it at once and the socket updates the open folder.
    await frame.locator('.cell[title="00001-7.png"]').waitFor({timeout: 15000});
    await page.screenshot({path: process.env.HANAIKADA_SCREENSHOT || "/tmp/sd-webui-image-browser-smoke.png", fullPage: true});
    assert.deepEqual(errors, []);
    await context.clearCookies();
    await page.waitForFunction(() => document.querySelector(".hanaikada-status")?.textContent.includes("登录已失效"), null, {timeout: 20000});
    assert.equal(await page.locator(".hanaikada-frame").isVisible(), false);
    console.log("PASS: real Gradio login, embedded Hanaikada UI, All folders, saved image shown live, expired session");
} finally {
    await browser.close();
}
