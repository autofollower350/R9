from flask import Flask, request, send_file
from playwright.async_api import async_playwright
import asyncio
import os
import fitz
import re

app = Flask(__name__)

browser_instance = None
playwright_instance = None

# ---------------- PDF INFO ----------------

def extract_student_info(pdf_path):

    info = {
        "name": "Not Found",
        "father": "Not Found",
        "roll": "Not Found",
        "center": "Not Found"
    }

    try:

        doc = fitz.open(pdf_path)

        text = ""

        for page in doc:
            text += page.get_text()

        roll_match = re.search(
            r"Roll no is\s+([\w\d]+)",
            text
        )

        if roll_match:
            info["roll"] = roll_match.group(1)

        name_match = re.search(
            r"NAME OF CANDIDATE\s*:\s*(.*)",
            text
        )

        if name_match:
            info["name"] = name_match.group(1).split('\n')[0]

        father_match = re.search(
            r"FATHER'S NAME\s*:\s*(.*)",
            text
        )

        if father_match:
            info["father"] = father_match.group(1).split('\n')[0]

        center_match = re.search(
            r"Exam Centre is\s*(.*?)(?=Print Date|To,|The Centre|NAME OF EXAMINATION)",
            text,
            re.DOTALL
        )

        if center_match:
            info["center"] = " ".join(
                center_match.group(1).split()
            )

        doc.close()

    except Exception as e:
        print(e)

    return info

# ---------------- BROWSER ----------------

async def get_browser():

    global browser_instance
    global playwright_instance

    if browser_instance is None:

        playwright_instance = await async_playwright().start()

        browser_instance = await playwright_instance.chromium.launch(
            headless=True,

            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-setuid-sandbox"
            ]
        )

    return browser_instance

# ---------------- HOME ----------------

@app.route("/")
def home():

    return """
    <!DOCTYPE html>
    <html>

    <head>
        <title>JNVU Portal</title>

        <style>

            body{
                font-family:Arial;
                background:#f2f2f2;
                text-align:center;
                padding-top:100px;
            }

            .box{

                width:350px;
                margin:auto;

                background:white;

                padding:20px;

                border-radius:10px;

                box-shadow:0 0 10px rgba(0,0,0,.1);
            }

            input{

                width:90%;
                padding:12px;

                margin-top:10px;
            }

            button{

                width:95%;
                padding:12px;

                margin-top:15px;

                background:red;

                color:white;

                border:none;

                cursor:pointer;
            }

        </style>
    </head>

    <body>

        <div class="box">

            <h2>🚀 JNVU Admit Card</h2>

            <form action="/download" method="POST">

                <input
                    type="text"
                    name="form_no"
                    placeholder="Enter Form Number"
                    required
                >

                <button type="submit">
                    Download PDF
                </button>

            </form>

        </div>

    </body>
    </html>
    """

# ---------------- DOWNLOAD ----------------

@app.route("/download", methods=["POST"])
def download():

    form_number = request.form.get("form_no")

    if not form_number.isdigit():
        return "Invalid Form Number"

    pdf_path = f"admit_{form_number}.pdf"

    asyncio.run(
        process_download(form_number, pdf_path)
    )

    if not os.path.exists(pdf_path):
        return "Admit Card Not Found"

    return send_file(
        pdf_path,
        as_attachment=True,
        download_name=f"JNVU_{form_number}.pdf"
    )

# ---------------- PLAYWRIGHT ----------------

async def process_download(form_number, pdf_path):

    browser = await get_browser()

    context = await browser.new_context(
        accept_downloads=True
    )

    page = await context.new_page()

    await page.route(
        "**/*.{png,jpg,jpeg,gif,css,woff2}",
        lambda route: route.abort()
    )

    url = "https://erp.jnvuiums.in/(S(biolzjtwlrcfmzwwzgs5uj5n))/Exam/Pre_Exam/Exam_ForALL_AdmitCard.aspx#"

    try:

        await page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=15000
        )

        await page.fill(
            "#txtchallanNo",
            str(form_number)
        )

        submit_btn = page.locator("#btnGetResult")

        async with page.expect_download(
            timeout=15000
        ) as download_info:

            await submit_btn.click()

            await submit_btn.click()

        download = await download_info.value

        await download.save_as(pdf_path)

        await context.close()

    except Exception as e:

        print(e)

        await context.close()

# ---------------- START ----------------

if __name__ == "__main__":

    port = int(os.environ.get("PORT", 10000))

    app.run(
        host="0.0.0.0",
        port=port
          )
