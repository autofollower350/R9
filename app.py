from flask import Flask, request, send_file, render_template
import asyncio
import os
import nest_asyncio
import fitz
import re
from playwright.async_api import async_playwright

nest_asyncio.apply()

app = Flask(__name__)

# --- ब्राउज़र मैनेजमेंट ---

browser_instance = None
playwright_instance = None

# --- PDF विश्लेषण ---

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

        # रोल नंबर

        roll_match = re.search(
            r"Roll no is\s+([\w\d]+)",
            text
        )

        if roll_match:
            info["roll"] = (
                roll_match.group(1).strip()
            )

        # छात्र का नाम

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

        # पिता का नाम

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

        # परीक्षा केंद्र

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

# --- ब्राउज़र ---

async def get_browser():

    global browser_instance
    global playwright_instance

    if browser_instance is None:

        playwright_instance = (
            await async_playwright().start()
        )

        browser_instance = (
            await playwright_instance.chromium.launch(
                headless=True
            )
        )

    return browser_instance

# --- डाउनलोड लॉजिक ---

async def download_jnvu_pdf(form_number):

    pdf_path = (
        f"admit_card_{form_number}.pdf"
    )

    browser = await get_browser()

    context = await browser.new_context(
        accept_downloads=True
    )

    page = await context.new_page()

    # स्पीड के लिए फालतू रिसोर्स ब्लॉक

    await page.route(
        "**/*.{png,jpg,jpeg,gif,css,woff2}",
        lambda route: route.abort()
    )

    url = (
        "https://erp.jnvuiums.in/"
        "(S(biolzjtwlrcfmzwwzgs5uj5n))/"
        "Exam/Pre_Exam/"
        "Exam_ForALL_AdmitCard.aspx#"
    )

    try:

        await page.goto(
            url,
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

# --- HOME PAGE ---

@app.route("/")
def home():

    return render_template(
        "index.html"
    )

# --- DOWNLOAD ROUTE ---

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
        f"Searching for Admit Card: {form_no}"
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

        print("\n" + "=" * 30)

        print("✅ Admit Card Found!")

        print(f"Name: {data['name']}")

        print(f"Father: {data['father']}")

        print(f"Roll No: {data['roll']}")

        print(f"Center: {data['center']}")

        print(
            f"File Saved: {file_path}"
        )

        print("=" * 30 + "\n")

        return send_file(
            file_path,
            as_attachment=True,
            download_name=(
                f"JNVU_{form_no}.pdf"
            )
        )

    return """
    <h3>❌ Admit Card Not Found</h3>
    <a href="/">Try Again</a>
    """

# --- START SERVER ---

if __name__ == "__main__":

    port = int(
        os.environ.get("PORT", 10000)
    )

    app.run(
        host="0.0.0.0",
        port=port
        )
