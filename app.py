from flask import Flask, request, render_template, send_file
import asyncio
import os
import nest_asyncio
from playwright.async_api import async_playwright

nest_asyncio.apply()

app = Flask(__name__)

URL = "https://erp.jnvuiums.in/(S(biolzjtwlrcfmzwwzgs5uj5n))/Exam/Pre_Exam/Exam_ForALL_AdmitCard.aspx#"

# Global Browser Instances
playwright_instance = None
browser_instance = None

# Heavy assets ko block karne ke liye list
BLOCK_RESOURCE_TYPES = ["image", "stylesheet", "media", "font", "texttrack"]
BLOCK_RESOURCE_NAMES = ["google-analytics", "analytics", "font-awesome", "jquery"]

async def init_browser():
    """App start hote hi background me browser open karne ke liye"""
    global playwright_instance, browser_instance
    if browser_instance is None:
        playwright_instance = await async_playwright().start()
        browser_instance = await playwright_instance.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-setuid-sandbox",
                "--disable-gpu"
            ]
        )
    return browser_instance

# ---------------- DOWNLOAD ROUTINE (WITH VIDEO RECORDING) ----------------
async def download_jnvu_pdf(form_number):
    pdf_path = f"admit_card_{form_number}.pdf"
    
    browser = await init_browser()
    
    # 🎥 SCREEN RECORDING CONFIGURATION:
    # "videos/" folder me har ek request ki video record hogi.
    # Video ka size default browser viewport jitna set kiya hai.
    context = await browser.new_context(
        accept_downloads=True,
        record_video_dir="videos/",
        record_video_size={"width": 1280, "height": 720}
    )
    
    page = await context.new_page()

    # Network Interception
    async def route_intercept(route):
        req = route.request
        if req.resource_type in BLOCK_RESOURCE_TYPES or any(key in req.url for key in BLOCK_RESOURCE_NAMES):
            await route.abort()
        else:
            await route.continue_()

    await page.route("**/*", route_intercept)

    try:
        await page.goto(URL, wait_until="domcontentloaded", timeout=15000)

        await page.fill("#txtchallanNo", str(form_number))
        submit_btn = page.locator("#btnGetResult")

        # Double Click Logic
        async with page.expect_download(timeout=10000) as download_info:
            await submit_btn.click()
            await asyncio.sleep(0.3)
            await submit_btn.click()

        download = await download_info.value
        await download.save_as(pdf_path)
        
        # Context close hote hi video automatic save ho jayegi
        await context.close()
        
        # Agar aapko video ka path check karna ho toh:
        video_path = await page.video.path()
        print(f"📹 Video recorded and saved at: {video_path}")
        
        return pdf_path

    except Exception as e:
        print(f"Download Failed: {e}")
        await context.close()
        return None

# ---------------- FLASK ROUTES ----------------
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/download", methods=["POST"])
def download():
    form_no = request.form.get("form_no", "").strip()

    if not form_no.isdigit():
        return '<h3>❌ Invalid Form Number</h3><a href="/">Go Back</a>'

    print(f"⚡ Downloading Admit Card Directly: {form_no}")

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    file_path = loop.run_until_complete(download_jnvu_pdf(form_no))

    if file_path and os.path.exists(file_path):
        response = send_file(
            file_path,
            as_attachment=True,
            download_name=f"JNVU_{form_no}.pdf"
        )
        return response

    return '<h3>❌ Admit Card Not Found</h3><a href="/">Try Again</a>'

if __name__ == "__main__":
    asyncio.run(init_browser())
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

