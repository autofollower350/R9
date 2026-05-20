from flask import Flask, request, render_template, send_file
import asyncio
import os
import nest_asyncio
import fitz
import re

from playwright.async_api import async_playwright

nest_asyncio.apply()

app = Flask(__name__)

# ---------------- GLOBAL ----------------

browser_instance = None
playwright_instance = None

URL = "https://erp.jnvuiums.in/(S(biolzjtwlrcfmzwwzgs5uj5n))/Exam/Pre_Exam/Exam_ForALL_AdmitCard.aspx#"

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

        # Roll Number

        roll_match = re.search(
            r"Roll no is\s+([\w\d]+)",
            text
        )

        if roll_match:
            info["roll"] = (
                roll_match.group(1).strip()
            )

        # Student Name

        name_match = re.search(
            r"NAME OF CANDIDATE\s*:\s*(.*)",
            text
        )

        if name_match:

            info["name"] = (
                name_match.group(1)
                .split('\n')[0]
                .strip()
            )

        # Father Name

        father_match = re.search(
            r"FATHER'S NAME\s*:\s*(.*)",
            text
        )

        if father_match:

            info["father"] = (
                father_match.group(1)
                .split('\n')[0]
                .strip()
            )

        # Center

        center_pattern = (
            r"Exam Centre is\s*(.*?)"
            r"(?=Print Date|To,|The Centre|NAME OF EXAMINATION)"
        )

        center_match = re.search(
            center_pattern,
            text,
            re.DOTALL
        )

        if center_match:

            center_raw = (
                center_match.group(1)
                .strip()
            )

            info["center"] = " ".join(
                center_raw.split()
            )

        else:

            alt_match = re.search(
                r"CENTER OF EXAMINATION\s*:\s*(.*?)"
                r"(?=\nSR NO|\nPrint Date)",
                text,
                re.DOTALL
            )

            if alt_match:

                info["center"] = " ".join(
                    alt_match.group(1).split()
                )

        doc.close()

        return info

    except Exception as e:

        print(f"Extraction Error: {e}")

        return info

# ---------------- BROWSER ----------------

async def get_browser():

    global browser_instance
    global playwright_instance

    if browser_instance is None:

        playwright_instance = (
            await async_playwright().start()
        )

        browser_instance = (
            await playwright_instance.chromium.launch(
                headless=True,

                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-setuid-sandbox"
                ]
            )
        )

    return browser_instance

# ---------------- DOWNLOAD ----------------

async def download_jnvu_pdf(form_number):

    pdf_path = (
        f"admit_card_{form_number}.pdf"
    )

    browser = await get_browser()

    context = await browser.new_context(
        accept_downloads=True
    )

    page = await context.new_page()

    # Speed Optimization

    await page.route(
        "**/*.{png,jpg,jpeg,gif,css,woff2}",
        lambda route: route.abort()
    )

    try:

        await page.goto(
            URL,
            wait_until="commit",
            timeout=20000
        )

        await page.fill(
            "#txtchallanNo",
            str(form_number)
        )

        submit_btn = page.locator(
            "#btnGetResult"
        )

        async with page.expect_download(
            timeout=10000
        ) as download_info:

            # Double Click

            await submit_btn.click()

            await asyncio.sleep(0.5)

            await submit_btn.click()

        download = await download_info.value

        await download.save_as(pdf_path)

        await context.close()

        return pdf_path

    except Exception as e:

        print(f"Download Failed: {e}")

        await context.close()

        return None

# ---------------- HOME ----------------

@app.route("/")
def home():

    return render_template(
        "index.html"
    )

# ---------------- DOWNLOAD ROUTE ----------------

@app.route("/download", methods=["POST"])
def download():

    form_no = (
        request.form.get(
            "form_no",
            ""
        ).strip()
    )

    if not form_no.isdigit():

        return """
        <h3>❌ Invalid Form Number</h3>
        <a href="/">Go Back</a>
        """

    print(
        f"Searching Admit Card: {form_no}"
    )

    file_path = asyncio.run(
        download_jnvu_pdf(form_no)
    )

    if (
        file_path and
        os.path.exists(file_path)
    ):

        data = extract_student_info(
            file_path
        )

        return render_template(
            "result.html",
            name=data["name"],
            father=data["father"],
            roll=data["roll"],
            center=data["center"],
            form_no=form_no
        )

    return """
    <h3>❌ Admit Card Not Found</h3>
    <a href="/">Try Again</a>
    """

# ---------------- PDF DOWNLOAD ----------------

@app.route("/pdf/<form_no>")
def pdf_download(form_no):

    file_path = (
        f"admit_card_{form_no}.pdf"
    )

    if os.path.exists(file_path):

        return send_file(
            file_path,
            as_attachment=True,
            download_name=(
                f"JNVU_{form_no}.pdf"
            )
        )

    return "PDF Not Found"

# ---------------- START ----------------

if __name__ == "__main__":

    port = int(
        os.environ.get("PORT", 10000)
    )

    app.run(
        host="0.0.0.0",
        port=port
        )
