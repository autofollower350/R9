from flask import Flask, request, render_template, send_file
import asyncio
import os
import nest_asyncio
import fitz
import re
from playwright.async_api import async_playwright

nest_asyncio.apply()

app = Flask(__name__)

URL = "https://erp.jnvuiums.in/(S(biolzjtwlrcfmzwwzgs5uj5n))/Exam/Pre_Exam/Exam_ForALL_AdmitCard.aspx#"

# Global Browser Instances (Isse har request par naya browser nahi khulega, speed bohot badhegi)
playwright_instance = None
browser_instance = None

# ---------------- SPEED OPTIMIZATION CONFIG ----------------
# Faltu ke heavy assets ko block karne ke liye list
BLOCK_RESOURCE_TYPES = ["image", "stylesheet", "media", "font", "texttrack"]
BLOCK_RESOURCE_NAMES = ["google-analytics", "analytics", "font-awesome", "jquery"]

async def init_browser():
    """App start hote hi browser ko background me ek baar launch karne ke liye"""
    global playwright_instance, browser_instance
    if browser_instance is None:
        playwright_instance = await async_playwright().start()
        browser_instance = await playwright_instance.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-setuid-sandbox",
                "--disable-gpu"  # Speed ke liye GPU hardware acceleration disable kiya
            ]
        )
    return browser_instance

# ---------------- PDF INFO EXTRACTION ----------------
def extract_student_info(pdf_path):
    info = {"name": "Not Found", "father": "Not Found", "roll": "Not Found", "center": "Not Found"}
    try:
        doc = fitz.open(pdf_path)
        text = "".join([page.get_text() for page in doc])
        
        roll_match = re.search(r"Roll no is\s+([\w\d]+)", text)
        if roll_match: info["roll"] = roll_match.group(1).strip()

        name_match = re.search(r"NAME OF CANDIDATE\s*:\s*(.*)", text)
        if name_match: info["name"] = name_match.group(1).split('\n')[0].strip()

        father_match = re.search(r"FATHER'S NAME\s*:\s*(.*)", text)
        if father_match: info["father"] = father_match.group(1).split('\n')[0].strip()

        center_pattern = r"Exam Centre is\s*(.*?)(?=Print Date|To,|The Centre|NAME OF EXAMINATION)"
        center_match = re.search(center_pattern, text, re.DOTALL)
        if center_match:
            info["center"] = " ".join(center_match.group(1).split())
        else:
            alt_match = re.search(r"CENTER OF EXAMINATION\s*:\s*(.*?)(?=\nSR NO|\nPrint Date)", text, re.DOTALL)
            if alt_match: info["center"] = " ".join(alt_match.group(1).split())

        doc.close()
        return info
    except Exception as e:
        print(f"Extraction Error: {e}")
        return info

# ---------------- DOWNLOAD ROUTINE ----------------
async def download_jnvu_pdf(form_number):
    pdf_path = f"admit_card_{form_number}.pdf"
    
    # Pehle se bana hua background browser reuse karein (Saves 5-8 seconds)
    browser = await init_browser()
    context = await browser.new_context(accept_downloads=True)
    page = await context.new_page()

    # Network Request Interception (Page fast load hone ke liye faltu scripts block)
    async def route_intercept(route):
        req = route.request
        if req.resource_type in BLOCK_RESOURCE_TYPES or any(key in req.url for key in BLOCK_RESOURCE_NAMES):
            await route.abort()
        else:
            await route.continue_()

    await page.route("**/*", route_intercept)

    try:
        # domcontentloaded use kiya jo full load se bohot fast hai
        await page.goto(URL, wait_until="domcontentloaded", timeout=15000)

        await page.fill("#txtchallanNo", str(form_number))
        submit_btn = page.locator("#btnGetResult")

        # Aapka Double Click Logic (JNVU Server ke liye retained)
        async with page.expect_download(timeout=10000) as download_info:
            await submit_btn.click()
            await asyncio.sleep(0.3)  # Delay thoda kam kiya (0.5 se 0.3) taaki fast ho
            await submit_btn.click()

        download = await download_info.value
        await download.save_as(pdf_path)
        await context.close()
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

    print(f"⚡ Searching Admit Card (Double Click Mode): {form_no}")

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    file_path = loop.run_until_complete(download_jnvu_pdf(form_no))

    if file_path and os.path.exists(file_path):
        data = extract_student_info(file_path)
        return render_template(
            "result.html",
            name=data["name"],
            father=data["father"],
            roll=data["roll"],
            center=data["center"],
            form_no=form_no
        )

    return '<h3>❌ Admit Card Not Found</h3><a href="/">Try Again</a>'

@app.route("/pdf/<form_no>")
def pdf_download(form_no):
    file_path = f"admit_card_{form_no}.pdf"
    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True, download_name=f"JNVU_{form_no}.pdf")
    return "PDF Not Found"

if __name__ == "__main__":
    # Server start hote hi background me browser launch ho jayega, user ka wait nahi karega
    asyncio.run(init_browser())
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

